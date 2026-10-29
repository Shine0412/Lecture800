import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from capture_service import CaptureManager, engine_arguments
from lecture_agent import create_app


class FakeProcess:
    def __init__(self):
        self.pid = 4321
        self.returncode = None

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.returncode = 0


class CaptureManagerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="lecture800-capture-test-")
        self.data_dir = Path(self.temporary.name)
        self.session = self.data_dir / "session.dpapi"
        self.managers = []
        self.process = FakeProcess()
        self.target = patch("capture_service.target_process_running", return_value=True).start()
        patch("capture_service.existing_certificate", return_value=False).start()
        patch("capture_service.stop_process_tree").start()
        patch("capture_service.subprocess.run", return_value=SimpleNamespace(returncode=0)).start()
        self.popen = patch("capture_service.subprocess.Popen", return_value=self.process).start()

    def tearDown(self):
        for manager in self.managers:
            manager.close()
        patch.stopall()
        self.temporary.cleanup()

    def manager(self, verify=None):
        manager = CaptureManager(
            self.data_dir,
            self.session,
            verify or (lambda: ({"lectures": [{"id": "one"}]}, {"applications": []})),
        )
        self.managers.append(manager)
        return manager

    def wait_for(self, manager, state):
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            if manager.snapshot()["state"] == state:
                return manager.snapshot()
            time.sleep(0.03)
        self.fail(f"未进入状态 {state}：{manager.snapshot()}")

    def start_fake(self, manager):
        result = manager.start(authorized=True)
        self.assertEqual(result["state"], "starting")
        self.assertFalse(result["systemProxyModified"])
        return self.process, self.popen

    def reach_waiting(self, manager):
        process, popen = self.start_fake(manager)
        manager.ca_dir.mkdir(parents=True, exist_ok=True)
        manager.cert_file.write_bytes(b"test-certificate")
        manager.status_file.write_text(json.dumps({"status": "ready"}), encoding="utf-8")
        self.wait_for(manager, "waiting")
        return process, popen

    def test_local_engine_does_not_ignore_connections_at_ip_stage(self):
        arguments = engine_arguments(self.data_dir, self.data_dir / "capture_addon.py")
        self.assertIn("local:WeChatAppEx.exe", arguments)
        self.assertNotIn("--ignore-hosts", arguments)
        self.assertNotIn("--allow-hosts", arguments)
        self.assertIn("flow_detail=0", arguments)

    def test_request_without_credentials_shows_diagnostic_and_keeps_waiting(self):
        manager = self.manager()
        self.reach_waiting(manager)
        manager.status_file.write_text(json.dumps({
            "status": "seen", "path": "/chair/h5/api/chair/pageChair.do",
        }), encoding="utf-8")
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline and "已收到请求" not in manager.snapshot()["detail"]:
            time.sleep(0.03)
        result = manager.snapshot()
        self.assertEqual(result["state"], "waiting")
        self.assertEqual(result["stage"], "session")
        self.assertTrue(result["active"])
        self.assertTrue(result["requestSeen"])
        self.assertGreaterEqual(result["remainingSeconds"], 0)
        self.assertIn("/chair/h5/api/chair/pageChair.do", result["detail"])
        self.assertIn("正在等待携带登录信息的接口", result["detail"])

    def test_authorization_and_wechat_are_required(self):
        manager = self.manager()
        with self.assertRaisesRegex(ValueError, "明确授权"):
            manager.start()
        self.target.assert_not_called()
        self.target.return_value = False
        with self.assertRaisesRegex(ValueError, "微信小程序进程"):
            manager.start(authorized=True)
        self.assertFalse(manager.snapshot()["active"])

    def test_success_verifies_and_cleans_temporary_capture(self):
        manager = self.manager()
        process, popen = self.reach_waiting(manager)
        self.session.write_bytes(b"new-session")
        manager.status_file.write_text(json.dumps({"status": "captured"}), encoding="utf-8")
        result = self.wait_for(manager, "success")
        self.assertEqual(result["verification"]["lectureCount"], 1)
        self.assertTrue(result["verification"]["temporaryCertificateRemoved"])
        self.assertFalse(result["verification"]["enrollmentSubmitted"])
        self.assertEqual(self.session.read_bytes(), b"new-session")
        self.assertFalse(manager.ca_dir.exists())
        self.assertFalse(result["certificateInstalled"])
        self.assertIn("--capture-engine", popen.call_args.args[0][-1])

    def test_cancel_stops_without_changing_existing_session(self):
        self.session.write_bytes(b"original-session")
        manager = self.manager()
        self.start_fake(manager)
        result = manager.cancel()
        self.assertEqual(result["state"], "cancelled")
        self.assertFalse(result["active"])
        self.assertEqual(self.session.read_bytes(), b"original-session")
        self.assertFalse(result["systemProxyModified"])

    def test_failed_verification_restores_original_session(self):
        self.session.write_bytes(b"original-session")
        manager = self.manager(verify=lambda: (_ for _ in ()).throw(RuntimeError("模拟接口失效")))
        self.reach_waiting(manager)
        self.session.write_bytes(b"invalid-new-session")
        manager.status_file.write_text(json.dumps({"status": "captured"}), encoding="utf-8")
        result = self.wait_for(manager, "error")
        self.assertIn("模拟接口失效", result["detail"])
        self.assertEqual(self.session.read_bytes(), b"original-session")
        self.assertFalse(manager.ca_dir.exists())

    def test_api_rejects_unauthenticated_capture_start(self):
        client = create_app().test_client()
        status = client.get("/api/capture")
        self.assertEqual(status.status_code, 200)
        self.assertFalse(status.get_json()["systemProxyModified"])
        response = client.post("/api/capture/start", json={})
        self.assertEqual(response.status_code, 400)
        self.assertIn("明确授权", response.get_json()["message"])


if __name__ == "__main__":
    unittest.main()
