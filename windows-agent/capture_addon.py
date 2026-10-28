"""mitmproxy addon: retain only the school H5 session, never request/response bodies."""
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
ALLOWED_HEADERS = {"satoken", "token", "x-token", "access-token"}


def write_status(status, detail=""):
    STATUS_FILE.write_text(json.dumps({
        "status": status,
        "detail": detail,
        "time": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    }, ensure_ascii=False), encoding="utf-8")


def retain_session(flow):
    request = flow.request
    if request.pretty_host.lower() != TARGET_HOST or not request.path.startswith("/chair/h5/"):
        return
    cookies = dict(request.cookies)
    if flow.response:
        for header in flow.response.headers.get_all("set-cookie"):
            parsed = SimpleCookie()
            parsed.load(header)
            cookies.update({name: morsel.value for name, morsel in parsed.items()})
    headers = {name: value for name, value in request.headers.items() if name.lower() in ALLOWED_HEADERS}
    if not cookies and not headers:
        return
    STORE.save(cookies, headers)
    write_status("captured", "目标域名会话已加密保存")


def request(flow):
    retain_session(flow)


def response(flow):
    retain_session(flow)
