"""Retain only the school H5 session; diagnostics never contain credential values."""
import json
import os
from http.cookies import SimpleCookie
from datetime import datetime, timezone
from pathlib import Path

from h5_client import SessionStore

TARGET_HOST = "app.nudt.edu.cn"
DATA_DIR = Path(os.environ["LECTURE800_DATA_DIR"])
STORE = SessionStore(DATA_DIR / "session.dpapi")
STATUS_FILE = DATA_DIR / "capture-status.json"
ALLOWED_HEADERS = {
    "satoken", "sa-token", "token", "x-token", "access-token",
    "authorization", "chair-personnel-token",
}


def write_status(status, detail="", **diagnostics):
    STATUS_FILE.write_text(json.dumps({
        "status": status,
        "detail": detail,
        "time": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        **diagnostics,
    }, ensure_ascii=False), encoding="utf-8")


def running():
    write_status("ready", "捕获引擎已就绪，可以重新进入讲座平台")


def tls_clienthello(data):
    """Pass through non-target TLS only after its SNI hostname is known."""
    server_name = getattr(data.client_hello, "sni", None)
    if server_name and server_name.lower() != TARGET_HOST:
        data.ignore_connection = True


def retain_session(flow):
    request = flow.request
    if request.pretty_host.lower() != TARGET_HOST or not request.path.startswith("/chair/h5/"):
        return
    path = request.path.split("?", 1)[0]
    cookies = dict(request.cookies)
    if flow.response:
        for header in flow.response.headers.get_all("set-cookie"):
            parsed = SimpleCookie()
            parsed.load(header)
            cookies.update({name: morsel.value for name, morsel in parsed.items()})
    headers = {name: value for name, value in request.headers.items() if name.lower() in ALLOWED_HEADERS}
    diagnostics = {
        "path": path,
        "cookieNames": sorted(cookies),
        "headerNames": sorted(name.lower() for name in headers),
    }
    if not cookies and not headers:
        write_status("seen", "已看到讲座接口请求，但未发现登录 Cookie／Token", **diagnostics)
        return
    STORE.save(cookies, headers)
    write_status("captured", "目标域名会话已加密保存", **diagnostics)


def request(flow):
    retain_session(flow)


def response(flow):
    retain_session(flow)
