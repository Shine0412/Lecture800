"""In-app, user-authorized, process-scoped session capture for Lecture800."""
from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

TARGET_PROCESS = "WeChatAppEx.exe"
TARGET_HOST = "app.nudt.edu.cn"
ACTIVE_STATES = {"starting", "waiting", "verifying"}
CAPTURE_TIMEOUT_SECONDS = 600
SILENT_RUN_KWARGS = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def resource_dir():
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def existing_certificate():
    return subprocess.run(
        ["certutil", "-user", "-store", "Root", "mitmproxy"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        **SILENT_RUN_KWARGS,
    ).returncode == 0


def target_process_running():
    result = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {TARGET_PROCESS}", "/FO", "CSV", "/NH"],
        capture_output=True, text=True, check=False, **SILENT_RUN_KWARGS,
    )
    return result.returncode == 0 and TARGET_PROCESS.lower() in result.stdout.lower()


def stop_process_tree(process):
    if not process or process.poll() is not None:
        return
    subprocess.run(
        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        **SILENT_RUN_KWARGS,
    )
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        pass


class CaptureManager:
    def __init__(self, data_dir, session_file, verify_callback):
        self.data_dir = Path(data_dir)
        self.session_file = Path(session_file)
        self.verify_callback = verify_callback
        self.ca_dir = self.data_dir / "capture-ca"
        self.cert_file = self.ca_dir / "mitmproxy-ca-cert.cer"
        self.status_file = self.data_dir / "capture-status.json"
        self.log_file = self.data_dir / "capture-engine.log"
        self._lock = threading.RLock()
        self._process = None
        self._engine_log = None
        self._certificate_installed = False
        self._session_backup = None
        self._captured = False
        self._deadline = None
        self._started_monotonic = None
        self._final_elapsed = None
        self._stage = "idle"
        self._request_seen = False
        self._request_path = None
        self._state = "idle"
        self._detail = "尚未开始本机会话配置"
        self._updated_at = now_iso()
        self._verification = None

    def snapshot(self):
        with self._lock:
            active = self._state in ACTIVE_STATES
            elapsed = self._final_elapsed or 0
            if active and self._started_monotonic is not None:
                elapsed = max(0, int(time.monotonic() - self._started_monotonic))
            remaining = max(0, int(self._deadline - time.monotonic())) if active and self._deadline else 0
            return {
                "state": self._state,
                "stage": self._stage,
                "detail": self._detail,
                "active": active,
                "canStart": not active,
                "updatedAt": self._updated_at,
                "elapsedSeconds": elapsed,
                "remainingSeconds": remaining,
                "requestSeen": self._request_seen,
                "requestPath": self._request_path,
                "targetProcess": TARGET_PROCESS,
                "processScoped": True,
                "systemProxyModified": False,
                "certificateInstalled": self._certificate_installed,
                "isAdministrator": bool(ctypes.windll.shell32.IsUserAnAdmin()) if os.name == "nt" else False,
                "verification": self._verification,
            }

    def _set_state(self, state, detail, stage=None):
        if state in {"success", "error", "cancelled"} and self._started_monotonic is not None:
            self._final_elapsed = max(0, int(time.monotonic() - self._started_monotonic))
        self._state = state
        self._detail = detail
        if stage is not None:
            self._stage = stage
        self._updated_at = now_iso()

    def start(self, authorized=False):
        if not authorized:
            raise ValueError("必须明确授权本机、进程级会话捕获")
        with self._lock:
            if self._state in ACTIVE_STATES:
                raise ValueError("会话配置正在进行，请勿重复启动")
            if not target_process_running():
                raise ValueError("未找到微信小程序进程，请先登录并打开目标讲座页面")
            if existing_certificate():
                raise ValueError("当前用户已存在 mitmproxy 证书，为避免覆盖已有配置，已停止")
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self.status_file.unlink(missing_ok=True)
            self._session_backup = self.session_file.read_bytes() if self.session_file.exists() else None
            self._captured = False
            self._verification = None
            self._request_seen = False
            self._request_path = None
            self._final_elapsed = None
            self._started_monotonic = time.monotonic()
            self._deadline = self._started_monotonic + CAPTURE_TIMEOUT_SECONDS
            self._set_state("starting", "正在启动微信小程序专用捕获引擎；请暂时不要操作微信", stage="engine")
            try:
                self._engine_log = self.log_file.open("w", encoding="utf-8")
                if getattr(sys, "frozen", False):
                    command = [sys.executable, "--capture-engine"]
                else:
                    command = [sys.executable, str(Path(__file__).resolve()), "--capture-engine"]
                creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                self._process = subprocess.Popen(
                    command,
                    cwd=str(resource_dir()),
                    env={**os.environ, "LECTURE800_DATA_DIR": str(self.data_dir)},
                    stdout=self._engine_log,
                    stderr=subprocess.STDOUT,
                    creationflags=creationflags,
                )
            except Exception:
                self._fail_locked("捕获引擎未能启动，请确认程序目录可写")
                raise ValueError(self._detail)
            threading.Thread(target=self._monitor, daemon=True, name="Lecture800Capture").start()
            return self.snapshot()

    def cancel(self):
        with self._lock:
            if self._state not in ACTIVE_STATES:
                return self.snapshot()
            cleaned = self._cleanup_locked()
            self._restore_session_locked()
            detail = "已取消会话配置，未修改系统代理"
            if not cleaned:
                detail += "；临时证书清理失败，请检查当前用户证书存储"
            self._set_state("cancelled", detail)
            return self.snapshot()

    def close(self):
        with self._lock:
            self._cleanup_locked()

    def _restore_session_locked(self):
        if not self._captured:
            return
        if self._session_backup is None:
            self.session_file.unlink(missing_ok=True)
        else:
            temporary = self.session_file.with_suffix(".restore.tmp")
            temporary.write_bytes(self._session_backup)
            os.replace(temporary, self.session_file)
        self._captured = False

    def _cleanup_locked(self):
        process = self._process
        self._process = None
        stop_process_tree(process)
        if self._engine_log:
            self._engine_log.close()
            self._engine_log = None
        if self._certificate_installed:
            subprocess.run(
                ["certutil", "-user", "-delstore", "Root", "mitmproxy"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
                **SILENT_RUN_KWARGS,
            )
        certificate_removed = not self._certificate_installed or not existing_certificate()
        self._certificate_installed = False
        shutil.rmtree(self.ca_dir, ignore_errors=True)
        return certificate_removed

    def _fail_locked(self, detail):
        cleaned = self._cleanup_locked()
        self._restore_session_locked()
        if not cleaned:
            detail += "；临时证书清理失败，请检查当前用户证书存储"
        self._set_state("error", detail)

    def _capture_status(self):
        try:
            return json.loads(self.status_file.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError, OSError):
            return {}

    def _monitor(self):
        while True:
            time.sleep(0.2)
            with self._lock:
                if self._state not in ACTIVE_STATES or not self._process:
                    return
                if self._process.poll() is not None:
                    self._fail_locked("捕获引擎意外退出；请重新尝试，若仍失败请以管理员身份运行 EXE")
                    return
                if time.monotonic() > self._deadline:
                    self._fail_locked("10 分钟内未捕获到会话；请停止后完全关闭小程序，再重新配置")
                    return
                if self._state == "starting" and self.cert_file.exists() and not self._certificate_installed:
                    self._set_state("starting", "引擎已启动，正在安装本次专用临时证书", stage="certificate")
                    result = subprocess.run(
                        ["certutil", "-user", "-addstore", "Root", str(self.cert_file)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
                        **SILENT_RUN_KWARGS,
                    )
                    if result.returncode != 0:
                        self._fail_locked("临时证书未能安装；请以管理员身份运行 EXE 后重试")
                        return
                    self._certificate_installed = True
                    self._set_state("starting", "临时证书已安装，正在确认捕获引擎已就绪", stage="selftest")
                status = self._capture_status()
                phase = status.get("status")
                if phase == "ready" and self._state == "starting":
                    self._set_state("waiting", "捕获已就绪：请重新进入“研究生学术讲座”，或切换一次“我的”", stage="wechat")
                elif phase == "seen" and self._state in {"starting", "waiting"}:
                    path = status.get("path") or "目标接口"
                    if not self._request_seen or self._request_path != path:
                        self._request_seen = True
                        self._request_path = path
                        self._set_state("waiting", f"已收到请求 {path}，正在等待携带登录信息的接口", stage="session")
                elif phase == "captured" and self.session_file.exists():
                    self._captured = True
                    self._set_state("verifying", "登录会话已加密保存，正在停止捕获并移除临时证书", stage="cleanup")
                    cleaned = self._cleanup_locked()
                    self._set_state("verifying", "临时捕获已清理，正在通过 HTTPS 只读验证讲座与我的信息", stage="verify")
                    try:
                        lectures, mine = self.verify_callback()
                        if not cleaned:
                            raise RuntimeError("临时证书未能移除，请检查当前用户证书存储")
                        self._verification = {
                            "lectureCount": len(lectures.get("lectures", [])),
                            "applicationCount": len(mine.get("applications", [])),
                            "directHttpsVerified": True,
                            "temporaryCertificateRemoved": True,
                            "systemProxyModified": False,
                            "enrollmentSubmitted": False,
                        }
                        self._set_state("success", "配置完成：HTTPS 接口验证通过，临时证书与捕获进程已清理", stage="done")
                        return
                    except Exception as error:
                        self._restore_session_locked()
                        self._set_state("error", f"会话验证失败：{error}", stage="verify")
                        return


def engine_self_test():
    """Validate packaged engine imports without opening a proxy or installing a CA."""
    from mitmproxy.tools.main import mitmdump  # noqa: F401
    from mitmproxy_rs.local import LocalRedirector

    data_dir = Path(os.environ["LECTURE800_DATA_DIR"])
    data_dir.mkdir(parents=True, exist_ok=True)
    result = {
        "engineImports": True,
        "addonPresent": (resource_dir() / "capture_addon.py").is_file(),
        "processTarget": LocalRedirector.describe_spec(TARGET_PROCESS),
        "captureStarted": False,
        "certificateInstalled": False,
        "systemProxyModified": False,
    }
    if not result["addonPresent"]:
        raise RuntimeError("内置捕获脚本缺失")
    (data_dir / "capture-self-test.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8",
    )


def engine_arguments(data_dir, addon):
    """Build local capture arguments without IP-stage host filtering.

    In transparent mode, ignore_hosts/allow_hosts also see the destination IP
    before TLS SNI is available. A negative domain regex therefore ignores the
    whole connection before the school hostname can be observed. Non-target
    TLS connections are passed through later by capture_addon.tls_clienthello.
    """
    return [
        "--mode", f"local:{TARGET_PROCESS}",
        "--set", f"confdir={Path(data_dir) / 'capture-ca'}",
        "--set", "flow_detail=0",
        "--set", "termlog_verbosity=info",
        "-s", str(addon),
    ]


def engine_main():
    """Run the embedded mitmdump engine in a child process."""
    data_dir = Path(os.environ["LECTURE800_DATA_DIR"])
    data_dir.mkdir(parents=True, exist_ok=True)
    from mitmproxy.tools.main import mitmdump

    mitmdump(engine_arguments(data_dir, resource_dir() / "capture_addon.py"))


if __name__ == "__main__":
    engine_main()
