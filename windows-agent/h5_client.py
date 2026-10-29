from __future__ import annotations

import base64
import ctypes
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import requests

API_ORIGIN = "https://app.nudt.edu.cn"
API_BASE = f"{API_ORIGIN}/chair/h5/api"
SUCCESS_CODE = "00000"
AUTH_CODES = {"A0230", "U12001"}
PAGE_SIZE = 10
# All concurrently created clients share one lock for the same on-disk session.
_SESSION_STORE_LOCK = threading.RLock()


def utc_now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class ApiError(RuntimeError):
    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


class SessionStore:
    """Keep captured credentials encrypted with the current Windows user's DPAPI."""

    def __init__(self, path):
        self.path = Path(path)
        self._lock = _SESSION_STORE_LOCK

    def has_session(self):
        return self.path.is_file()

    def save(self, cookies, headers=None):
        with self._lock:
            payload = {
                "version": 1,
                "cookies": dict(cookies),
                "headers": dict(headers or {}),
                "updatedAt": utc_now_iso(),
            }
            encrypted = _crypt_protect(json.dumps(payload).encode("utf-8"))
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(base64.b64encode(encrypted).decode("ascii"), encoding="ascii")
            os.replace(temporary, self.path)

    def load(self):
        with self._lock:
            if not self.path.is_file():
                raise ApiError("尚未建立已验证的登录会话，请先完成本机会话捕获", "SESSION_MISSING")
            try:
                encrypted = base64.b64decode(self.path.read_text(encoding="ascii"), validate=True)
                payload = json.loads(_crypt_unprotect(encrypted).decode("utf-8"))
            except Exception as error:
                raise ApiError("本机会话无法解密，请在原 Windows 用户下重新捕获", "SESSION_INVALID") from error
            if not payload.get("cookies") and not payload.get("headers", {}).get("satoken"):
                raise ApiError("已保存的会话没有 Cookie 或 satoken，请重新捕获", "SESSION_INVALID")
            return payload

    def clear(self):
        with self._lock:
            self.path.unlink(missing_ok=True)

    def status(self):
        if not self.has_session():
            return {"saved": False, "updatedAt": None}
        try:
            payload = self.load()
            return {"saved": True, "updatedAt": payload.get("updatedAt")}
        except ApiError:
            return {"saved": True, "updatedAt": None, "error": "无法解密当前会话"}


class _DataBlob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_byte))]


def _blob(value):
    buffer = ctypes.create_string_buffer(value)
    return _DataBlob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer


def _crypt_protect(value):
    if os.name != "nt":
        raise ApiError("会话加密仅支持 Windows", "DPAPI_UNAVAILABLE")
    source, source_buffer = _blob(value)
    target = _DataBlob()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(source), "Lecture800", None, None, None, 0, ctypes.byref(target)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        ctypes.windll.kernel32.LocalFree(target.data)


def _crypt_unprotect(value):
    source, source_buffer = _blob(value)
    target = _DataBlob()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 0, ctypes.byref(target)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        ctypes.windll.kernel32.LocalFree(target.data)


def epoch_to_iso(value):
    try:
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        return datetime.fromtimestamp(timestamp, timezone.utc).astimezone().isoformat(timespec="seconds")
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def numeric(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def chair_type_name(value):
    if numeric(value) == 0:
        return "800"
    if numeric(value) == 1:
        return "视野"
    return str(value) if value is not None else "未知"


def normalize_lecture(item, before_time_millis=0):
    chair_id = str(item.get("chairId") or "")
    apply_status = numeric(item.get("applyStatus"))
    current_time = numeric(item.get("currentTime"))
    apply_begin = numeric(item.get("applyBeginTime"))
    chair_begin = numeric(item.get("chairBeginTime"))
    remaining = numeric(item.get("leaveNum"))
    before_time = numeric(before_time_millis) or 0
    if apply_status == 1:
        status = "enrolled"
    elif current_time is not None and chair_begin is not None and current_time >= chair_begin - before_time:
        status = "ended"
    elif apply_begin is None or current_time is None or current_time < apply_begin:
        status = "upcoming"
    elif remaining == 0:
        status = "full"
    elif remaining is not None and remaining > 0:
        status = "open"
    else:
        status = "unknown"
    label = item.get("label")
    if isinstance(label, dict):
        category = label.get("dictName") or label.get("name") or "未分类"
    else:
        category = str(label) if label else "未分类"
    return {
        "id": chair_id,
        "title": item.get("chairName") or "未命名讲座",
        "level": chair_type_name(item.get("chairType")),
        "category": category,
        "speaker": item.get("teacherName") or "主讲人待确认",
        "teacherJob": item.get("teacherJob") or "",
        "startAt": epoch_to_iso(item.get("chairBeginTime")),
        "endAt": epoch_to_iso(item.get("chairEndTime")),
        "location": item.get("chairSite") or "地点待确认",
        "capacity": numeric(item.get("applyTopNum")),
        "remaining": remaining,
        "enrolledCount": numeric(item.get("applyNum")),
        "enrollmentOpenAt": epoch_to_iso(apply_begin),
        "status": status,
        "registration": "enrolled" if apply_status == 1 else None,
        "applyId": item.get("applyId"),
        "description": item.get("chairIntro") or "该讲座暂无详细介绍。",
    }


class H5Client:
    def __init__(self, store, session_factory=requests.Session):
        self.store = store
        self.session_factory = session_factory
        self._local = threading.local()

    def _get_session(self):
        saved = self.store.load()
        signature = json.dumps(saved, ensure_ascii=False, sort_keys=True)
        cached = getattr(self._local, "cached", None)
        if cached and cached["signature"] == signature:
            return cached["session"]
        if cached:
            close = getattr(cached["session"], "close", None)
            if close:
                close()
        session = self.session_factory()
        session.cookies.update(saved["cookies"])
        session.headers.update({
            "Accept": "application/json, text/plain, */*",
            "Referer": f"{API_ORIGIN}/chair/h5/",
            "Origin": API_ORIGIN,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Lecture800/1.0",
        })
        for name, value in saved.get("headers", {}).items():
            if name.lower() not in {"cookie", "content-length", "host", "proxy-authorization"}:
                session.headers[name] = value
        self._local.cached = {"signature": signature, "session": session}
        return session

    def _discard_session(self, session):
        cached = getattr(self._local, "cached", None)
        if cached and cached["session"] is session:
            self._local.cached = None
        close = getattr(session, "close", None)
        if close:
            close()

    def request(self, method, path, *, params=None, data=None):
        method = method.upper()
        attempts = 2 if method == "GET" else 1
        for attempt in range(attempts):
            session = self._get_session()
            try:
                response = session.request(
                    method, f"{API_BASE}/{path.lstrip('/')}", params=params, data=data,
                    timeout=(5, 15) if method == "GET" else (8, 20),
                )
            except (requests.ConnectionError, requests.Timeout):
                self._discard_session(session)
                if attempt + 1 < attempts:
                    time.sleep(0.35)
                    continue
                raise
            if method == "GET" and response.status_code in {502, 503, 504} and attempt + 1 < attempts:
                time.sleep(0.35)
                continue
            break
        try:
            payload = response.json()
        except ValueError as error:
            raise ApiError(f"服务器返回了非 JSON 响应（HTTP {response.status_code}）", "INVALID_RESPONSE") from error
        code = str(payload.get("code", ""))
        if code in AUTH_CODES:
            raise ApiError("登录会话已失效，请重新捕获本人已登录会话", code)
        if response.status_code != 200 or code != SUCCESS_CODE:
            raise ApiError(str(payload.get("msg") or f"接口请求失败（HTTP {response.status_code}）"), code or str(response.status_code))
        if response.cookies.get_dict():
            saved = self.store.load()
            cookies = {**saved["cookies"], **response.cookies.get_dict()}
            self.store.save(cookies, saved.get("headers"))
        return payload.get("data")

    def before_time_millis(self):
        return self.request("GET", "/common/getBeforeTimeMillis.do") or 0

    def _all_records(self, path, params=None):
        records = []
        for current in range(1, 101):
            data = self.request("GET", path, params={"size": PAGE_SIZE, "current": current, **(params or {})}) or {}
            page = data.get("records") or []
            if not isinstance(page, list):
                raise ApiError("分页接口的 records 字段格式异常", "INVALID_RESPONSE")
            records.extend(page)
            if len(page) < PAGE_SIZE:
                return records
        raise ApiError("目录超过 100 页，为避免持续请求已停止", "PAGE_LIMIT")

    def lectures(self):
        # The catalogue is newest-first and includes years of history. Read only
        # the first page used by the live dashboard instead of crawling history.
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="Lecture800Read") as pool:
            page_future = pool.submit(
                self.request, "GET", "/chair/pageChair.do",
                params={"size": 50, "current": 1, "chairType": 0},
            )
            before_future = pool.submit(self.before_time_millis)
            page = page_future.result() or {}
            before = before_future.result()
        records = page.get("records") or []
        return [normalize_lecture(item, before) for item in records if item.get("chairId") is not None]

    def detail(self, chair_id):
        return self.request("GET", "/chair/getChairDetail.do", params={"chairId": str(chair_id)}) or {}

    def mine(self):
        group_types = {"pending": 1, "pendingEvaluation": 6, "evaluated": 7}
        with ThreadPoolExecutor(max_workers=7, thread_name_prefix="Lecture800Mine") as pool:
            user_future = pool.submit(self.request, "GET", "/user/getUserInfo.do")
            status_future = pool.submit(self.request, "GET", "/user/getRegisrationByUserId.do")
            applications_future = pool.submit(self._all_records, "/chair/pageUserChair.do")
            before_future = pool.submit(self.before_time_millis)
            group_futures = {
                key: pool.submit(self._all_records, "/chair/pageUserChair.do", {"type": value})
                for key, value in group_types.items()
            }
            user = user_future.result() or {}
            status = status_future.result() or {}
            applications = applications_future.result()
            before = numeric(before_future.result()) or 0
            group_records = {key: future.result() for key, future in group_futures.items()}
        metrics = [
            ("我的报名数", "myAppNum"), ("待参与数", "waitToParticipateNum"),
            ("已完成考勤数", "effectiveAttendanceNum"), ("已完成评价数", "completedEvaluationNum"),
        ]
        join_status = {
            str(item.get("chairId")): key
            for key, records in group_records.items() for item in records if item.get("chairId") is not None
        }

        def normalize_many(records):
            normalized = []
            for item in records:
                if item.get("chairId") is None:
                    continue
                lecture = normalize_lecture(item)
                lecture["registration"] = "enrolled"
                lecture["joinStatus"] = join_status.get(str(item.get("chairId")))
                sign_arrive = numeric(item.get("signArrive"))
                end_millis = numeric(item.get("chairEndTime"))
                begin_millis = numeric(item.get("chairBeginTime"))
                current_millis = numeric(item.get("currentTime")) or int(datetime.now().timestamp() * 1000)
                if end_millis is not None and end_millis < 10_000_000_000:
                    end_millis *= 1000
                if begin_millis is not None and begin_millis < 10_000_000_000:
                    begin_millis *= 1000
                attended = sign_arrive == 1
                ended = end_millis is not None and current_millis >= end_millis
                lecture["attendanceStatus"] = "attended" if attended else "missed" if ended else "notStarted"
                lecture["signArrive"] = sign_arrive
                lecture["signArriveTime"] = epoch_to_iso(item.get("signArriveTime"))
                lecture["canWithdraw"] = begin_millis is not None and current_millis < begin_millis - before
                normalized.append(lecture)
            return normalized

        normalized_applications = normalize_many(applications)
        groups = {key: normalize_many(records) for key, records in group_records.items()}
        groups["attended"] = [item for item in normalized_applications if item["attendanceStatus"] == "attended"]
        groups["missedAttendance"] = [item for item in normalized_applications if item["attendanceStatus"] == "missed"]
        return {
            "profile": {"account": user.get("userName") or "未返回", "role": "学生"},
            "metrics": [{"label": label, "value": numeric(status.get(key)) or 0} for label, key in metrics],
            "applications": normalized_applications,
            "groups": groups,
            "items": [],
        }

    def apply(self, chair_id):
        payload = self.request("POST", "/chair/chairApply.do", data={"chairId": str(chair_id)})
        if not payload:
            raise ApiError("报名接口未返回成功数据，未记为报名成功", "APPLY_NOT_CONFIRMED")
        return True

    def withdraw(self, chair_id, apply_id):
        payload = self.request("POST", "/chair/chairElect.do", data={"chairId": str(chair_id), "applyId": str(apply_id)})
        if not payload:
            raise ApiError("退课接口未返回成功数据，未记为退课成功", "WITHDRAW_NOT_CONFIRMED")
        return True

    def read_all(self):
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="Lecture800Parallel") as pool:
            lectures_future = pool.submit(self.lectures)
            mine_future = pool.submit(self.mine)
            return lectures_future.result(), mine_future.result()
