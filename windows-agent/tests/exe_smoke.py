import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

import requests

root = Path(__file__).resolve().parents[2]
script_dir = root / "windows-agent"
exe = root / "dist-desktop" / "Lecture800.exe"
base = "http://127.0.0.1:8770"

with tempfile.TemporaryDirectory(prefix="lecture800-exe-test-") as data_dir:
    environment = {**os.environ, "LECTURE800_DATA_DIR": data_dir}
    if os.environ.get("LECTURE_TEST_DEV") == "1":
        base_command = [str(script_dir / ".venv" / "Scripts" / "python.exe"), str(script_dir / "desktop_app.py")]
    else:
        base_command = [str(exe)]
    self_test = subprocess.run(base_command + ["--capture-self-test"], cwd=str(exe.parent), env=environment, capture_output=True, timeout=40)
    assert self_test.returncode == 0, self_test.stderr.decode(errors="replace")
    engine_report = json.loads((Path(data_dir) / "capture-self-test.json").read_text(encoding="utf-8"))
    assert engine_report["engineImports"] is True
    assert engine_report["addonPresent"] is True
    assert engine_report["captureStarted"] is False
    assert engine_report["certificateInstalled"] is False
    assert engine_report["systemProxyModified"] is False
    process = subprocess.Popen(base_command + ["--api-only", "--port", "8770"], cwd=str(exe.parent), env=environment)
    try:
        deadline = time.time() + 40
        while True:
            if process.poll() is not None:
                raise RuntimeError(f"程序提前退出：{process.returncode}")
            try:
                verification_response = requests.get(f"{base}/api/verify", timeout=8)
                verification_response.raise_for_status()
                verification = verification_response.json()
                break
            except Exception:
                if time.time() > deadline:
                    raise
                time.sleep(0.5)

        assert verification["connected"] is False
        assert verification["session"]["saved"] is False
        assert verification["checks"][0]["ok"] is False
        lectures_response = requests.get(f"{base}/api/lectures", timeout=15)
        assert lectures_response.status_code == 503
        lectures = lectures_response.json()
        assert lectures["connected"] is False and lectures["lectures"] == []

        capture_response = requests.get(f"{base}/api/capture", timeout=8)
        capture_response.raise_for_status()
        capture = capture_response.json()
        assert capture["state"] == "idle"
        assert capture["processScoped"] is True
        assert capture["systemProxyModified"] is False
        capture_unauthorized = requests.post(f"{base}/api/capture/start", json={}, timeout=8)
        assert capture_unauthorized.status_code == 400
        assert "明确授权" in capture_unauthorized.json()["message"]

        settings_response = requests.get(f"{base}/api/settings", timeout=8)
        settings_response.raise_for_status()
        original = settings_response.json()["autoEnabled"]
        original_rules = settings_response.json()["locationRules"]
        changed = requests.put(f"{base}/api/settings", json={"autoEnabled": not original}, timeout=8)
        changed.raise_for_status()
        assert changed.json()["autoEnabled"] is (not original)
        restored = requests.put(f"{base}/api/settings", json={"autoEnabled": original}, timeout=8)
        restored.raise_for_status()
        assert restored.json()["autoEnabled"] is original
        changed_rules = {**original_rules, "thirdSite": not original_rules["thirdSite"]}
        rules_response = requests.put(f"{base}/api/settings", json={"locationRules": changed_rules}, timeout=8)
        rules_response.raise_for_status()
        assert rules_response.json()["locationRules"]["thirdSite"] is changed_rules["thirdSite"]
        assert rules_response.json()["autoEnabled"] is original
        persisted_rules = requests.get(f"{base}/api/settings", timeout=8).json()["locationRules"]
        assert persisted_rules == changed_rules
        restored_rules = requests.put(f"{base}/api/settings", json={"locationRules": original_rules}, timeout=8)
        restored_rules.raise_for_status()
        assert restored_rules.json()["locationRules"] == original_rules

        confirmation_response = requests.post(f"{base}/api/enroll", json={"lectureId": "test"}, timeout=8)
        assert confirmation_response.status_code == 400
        assert confirmation_response.json()["error"] == "CONFIRM_REQUIRED"
        enrollment_response = requests.post(f"{base}/api/enroll", json={"lectureId": "test", "confirm": True}, timeout=8)
        assert enrollment_response.status_code == 502
        assert enrollment_response.json()["error"] == "SESSION_MISSING"
        assert enrollment_response.json()["verified"] is False
        batch_confirmation = requests.post(f"{base}/api/enroll/all", json={}, timeout=8)
        assert batch_confirmation.status_code == 400
        assert batch_confirmation.json()["error"] == "CONFIRM_REQUIRED"
        batch_response = requests.post(f"{base}/api/enroll/all", json={"confirm": True}, timeout=8)
        assert batch_response.status_code == 502
        assert batch_response.json()["error"] == "SESSION_MISSING"
        assert batch_response.json()["verified"] is False
        withdraw_confirmation = requests.post(f"{base}/api/withdraw", json={"lectureId": "test", "applyId": "apply-test"}, timeout=8)
        assert withdraw_confirmation.status_code == 400
        assert withdraw_confirmation.json()["error"] == "CONFIRM_REQUIRED"
        withdraw_response = requests.post(f"{base}/api/withdraw", json={"lectureId": "test", "applyId": "apply-test", "confirm": True}, timeout=8)
        assert withdraw_response.status_code == 502
        assert withdraw_response.json()["error"] == "SESSION_MISSING"
        assert withdraw_response.json()["verified"] is False

        html_response = requests.get(f"{base}/", timeout=8)
        html_response.raise_for_status()
        assert "Lecture800" in html_response.text
        report = {
            "result": "passed",
            "exe": str(exe),
            "sizeBytes": exe.stat().st_size,
            "unauthenticatedSessionRejected": True,
            "settingsToggle": "passed",
            "locationRulesPersisted": True,
            "captureApiReady": True,
            "captureEngineSelfTest": "passed-without-starting-capture",
            "captureAuthorizationRequired": True,
            "confirmationRequired": True,
            "unverifiedEnrollmentRejected": True,
            "immediateBatchConfirmationRequired": True,
            "unverifiedImmediateBatchRejected": True,
            "withdrawConfirmationRequired": True,
            "unverifiedWithdrawRejected": True,
            "frontend": "ok",
        }
        (root / "app" / "artifacts" / "exe-api-results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
