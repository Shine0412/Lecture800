import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


class CaptureAddonTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="lecture800-addon-test-")
        self.environment = patch.dict(os.environ, {"LECTURE800_DATA_DIR": self.temporary.name})
        self.environment.start()
        import capture_addon
        self.addon = importlib.reload(capture_addon)

    def tearDown(self):
        self.environment.stop()
        self.temporary.cleanup()

    @staticmethod
    def flow(cookies=None, headers=None):
        request = SimpleNamespace(
            pretty_host="app.nudt.edu.cn",
            path="/chair/h5/api/chair/pageChair.do?current=1",
            cookies=cookies or {},
            headers=headers or {},
        )
        return SimpleNamespace(request=request, response=None)

    def test_ready_and_seen_diagnostics_do_not_create_session(self):
        self.addon.running()
        status = json.loads(self.addon.STATUS_FILE.read_text(encoding="utf-8"))
        self.assertEqual(status["status"], "ready")
        self.addon.retain_session(self.flow())
        status = json.loads(self.addon.STATUS_FILE.read_text(encoding="utf-8"))
        self.assertEqual(status["status"], "seen")
        self.assertEqual(status["path"], "/chair/h5/api/chair/pageChair.do")
        self.assertFalse((Path(self.temporary.name) / "session.dpapi").exists())

    def test_non_target_tls_is_ignored_only_after_sni_is_available(self):
        target = SimpleNamespace(
            client_hello=SimpleNamespace(sni="app.nudt.edu.cn"),
            ignore_connection=False,
        )
        other = SimpleNamespace(
            client_hello=SimpleNamespace(sni="example.com"),
            ignore_connection=False,
        )
        unknown = SimpleNamespace(
            client_hello=SimpleNamespace(sni=None),
            ignore_connection=False,
        )
        self.addon.tls_clienthello(target)
        self.addon.tls_clienthello(other)
        self.addon.tls_clienthello(unknown)
        self.assertFalse(target.ignore_connection)
        self.assertTrue(other.ignore_connection)
        self.assertFalse(unknown.ignore_connection)

    def test_capture_encrypts_cookie_and_never_logs_its_value(self):
        secret = "test-only-credential-never-log"
        self.addon.retain_session(self.flow(cookies={"chair-personnel-token": secret}))
        status_text = self.addon.STATUS_FILE.read_text(encoding="utf-8")
        status = json.loads(status_text)
        self.assertEqual(status["status"], "captured")
        self.assertEqual(status["cookieNames"], ["chair-personnel-token"])
        self.assertNotIn(secret, status_text)
        self.assertEqual(self.addon.STORE.load()["cookies"]["chair-personnel-token"], secret)


if __name__ == "__main__":
    unittest.main()
