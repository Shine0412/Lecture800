from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, request

from h5_client import ApiError, H5Client, SessionStore
from capture_service import CaptureManager


def default_data_dir():
    configured = os.environ.get("LECTURE800_DATA_DIR")
    if configured:
        return Path(configured)
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "Lecture800-data"
    return Path(__file__).resolve().parent / "data"


DATA_DIR = default_data_dir()
DATA_DIR.mkdir(parents=True, exist_ok=True)
SNAPSHOT_FILE = DATA_DIR / "latest-snapshot.json"
MINE_FILE = DATA_DIR / "latest-mine.json"
LOG_FILE = DATA_DIR / "operations.jsonl"
SETTINGS_FILE = DATA_DIR / "settings.json"
SESSION_FILE = DATA_DIR / "session.dpapi"
_settings_lock = threading.Lock()
_snapshot_lock = threading.Lock()
_enroll_lock = threading.Lock()


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def h5_client():
    return H5Client(SessionStore(SESSION_FILE))


def _read_stored_settings():
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, OSError):
        return {}


def load_settings():
    from enrollment_policy import normalize_location_rules

    with _settings_lock:
        stored = _read_stored_settings()
        return {
            "autoEnabled": stored.get("autoEnabled") is not False,
            "locationRules": normalize_location_rules(stored.get("locationRules")),
            "precheckTime": "11:58",
            "reviewTime": "12:00",
            "writeEnabled": True,
            "scheduler": "embedded",
        }


def update_settings(auto_enabled=None, location_rules=None):
    from enrollment_policy import DEFAULT_LOCATION_RULES

    if auto_enabled is None and location_rules is None:
        raise ValueError("没有可保存的设置")
    if auto_enabled is not None and not isinstance(auto_enabled, bool):
        raise ValueError("autoEnabled 必须是布尔值")
    if location_rules is not None:
        if not isinstance(location_rules, dict) or not location_rules:
            raise ValueError("locationRules 必须包含至少一个地点选项")
        unknown = set(location_rules) - set(DEFAULT_LOCATION_RULES)
        if unknown:
            raise ValueError(f"未知地点选项：{', '.join(sorted(unknown))}")
        if any(not isinstance(value, bool) for value in location_rules.values()):
            raise ValueError("地点选项必须使用布尔值")
    with _settings_lock:
        stored = _read_stored_settings()
        if auto_enabled is not None:
            stored["autoEnabled"] = auto_enabled
        if location_rules is not None:
            stored["locationRules"] = {**stored.get("locationRules", {}), **location_rules}
        temporary = SETTINGS_FILE.with_suffix(".tmp")
        temporary.write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(SETTINGS_FILE)
    return load_settings()


def set_auto_enabled(enabled):
    result = update_settings(auto_enabled=enabled)
    append_log("scheduler", "enabled" if enabled else "disabled", {"message": f"EXE 内置每日任务已{'开启' if enabled else '关闭'}；开启时每天 12:00 并发提交全部符合条件的讲座并统一核验报名记录。"})
    return result


def set_location_rules(location_rules):
    result = update_settings(location_rules=location_rules)
    append_log("scheduler", "updated", {"message": "自动报名地点范围已保存，下一次预检和报名立即使用新规则。"})
    return result


def append_log(action, result, detail=None):
    record = {"time": now_iso(), "action": action, "result": result, "detail": detail}
    with LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_json(path, payload):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def scrape_lectures():
    lectures = h5_client().lectures()
    snapshot = {
        "connected": True,
        "source": "https-api",
        "fetchedAt": now_iso(),
        "count": len(lectures),
        "lectures": lectures,
    }
    write_json(SNAPSHOT_FILE, snapshot)
    return snapshot


def scrape_mine():
    result = h5_client().mine()
    payload = {
        "connected": True,
        "source": "https-api",
        "page": "mine",
        "fetchedAt": now_iso(),
        **result,
    }
    write_json(MINE_FILE, payload)
    return payload


def refresh_all():
    lectures, mine = h5_client().read_all()
    lecture_snapshot = {"connected": True, "source": "https-api", "fetchedAt": now_iso(), "count": len(lectures), "lectures": lectures}
    mine_snapshot = {"connected": True, "source": "https-api", "page": "mine", "fetchedAt": now_iso(), **mine}
    write_json(SNAPSHOT_FILE, lecture_snapshot)
    write_json(MINE_FILE, mine_snapshot)
    return lecture_snapshot, mine_snapshot


def verification_snapshot():
    status = SessionStore(SESSION_FILE).status()
    connected = False
    lecture_count = None
    message = "尚未捕获已登录会话；请按使用说明完成本机抓包"
    if status["saved"]:
        try:
            snapshot = scrape_lectures()
            connected = True
            lecture_count = snapshot["count"]
            message = f"接口请求验证通过，共读取 {lecture_count} 场 800 级讲座"
        except ApiError as error:
            message = str(error)
        except requests_error() as error:
            message = f"网络请求失败：{error}"
    return {
        "connected": connected,
        "time": now_iso(),
        "page": "http-api",
        "session": status,
        "checks": [
            {"key": "session", "label": "本机会话", "ok": status["saved"], "detail": "会话已由 Windows 用户加密保存" if status["saved"] else "尚未建立登录会话"},
            {"key": "network", "label": "HTTPS 接口", "ok": connected, "detail": message},
            {"key": "lectures", "label": "讲座与我的", "ok": connected, "detail": "两个接口可独立并发读取，无需切换小程序页面" if connected else "等待会话验证"},
        ],
    }


def requests_error():
    import requests
    return requests.RequestException


def enroll_lecture(lecture_id, confirm=False):
    from enrollment_policy import exclusion_reason

    def respond(status, payload, log_result=None, lecture=None):
        if lecture:
            payload["lecture"] = {
                "id": lecture["id"], "title": lecture["title"], "startAt": lecture.get("startAt"),
            }
        result = log_result or ("success" if payload.get("verified") else "failed")
        append_log("enroll", result, payload)
        return status, payload

    if not confirm:
        return respond(400, {"ok": False, "verified": False, "error": "CONFIRM_REQUIRED", "message": "必须明确确认后才能发送报名请求"}, "skipped")
    if not lecture_id:
        return respond(400, {"ok": False, "verified": False, "error": "LECTURE_ID_REQUIRED", "message": "缺少讲座 ID"}, "rejected")

    with _enroll_lock:
        lecture = None
        try:
            snapshot = scrape_lectures()
            lecture = next((item for item in snapshot["lectures"] if item["id"] == lecture_id), None)
            if lecture is None:
                return respond(404, {"ok": False, "verified": False, "error": "LECTURE_NOT_FOUND", "message": "最新讲座目录中未找到该讲座，未发送报名请求"}, "rejected")
            excluded = exclusion_reason(lecture, load_settings().get("locationRules"))
            if excluded:
                title = str(lecture.get("title") or "").lstrip()
                location = str(lecture.get("location") or "")
                code = "NANJING_EXCLUDED" if title.startswith("南京校区") else "WUHAN_EXCLUDED" if title.startswith("武汉校区") else "THIRD_CAMPUS_EXCLUDED" if "三号院" in location else "LOCATION_EXCLUDED"
                return respond(400, {"ok": False, "verified": False, "error": code, "message": f"{excluded}，未发送报名请求"}, "rejected", lecture)
            if lecture.get("level") != "800":
                return respond(400, {"ok": False, "verified": False, "error": "LEVEL_NOT_ALLOWED", "message": "只允许报名 800 级讲座"}, "rejected", lecture)

            mine = scrape_mine()
            enrolled = next((item for item in mine["applications"] if item["id"] == lecture_id), None)
            if enrolled:
                return respond(200, {"ok": True, "verified": True, "alreadyEnrolled": True, "message": "已在“我的报名”中独立核验到该讲座，未重复提交"}, lecture=enrolled)
            if lecture.get("registration") or lecture.get("status") == "enrolled":
                return respond(409, {"ok": False, "verified": False, "error": "RECEIPT_MISMATCH", "message": "目录显示已报名，但“我的报名”中尚未核验到，未重复提交"}, lecture=lecture)
            if lecture.get("status") != "open":
                return respond(409, {"ok": False, "verified": False, "error": "NOT_OPEN", "message": "该讲座当前不可报名，未发送报名请求"}, "rejected", lecture)

            h5_client().apply(lecture_id)
            receipt = scrape_mine()
            enrolled = next((item for item in receipt["applications"] if item["id"] == lecture_id), None)
            if not enrolled:
                return respond(502, {"ok": False, "verified": False, "error": "RECEIPT_NOT_FOUND", "message": "报名请求已发送，但“我的报名”未出现该讲座，不能记为成功，请勿立即重复提交"}, lecture=lecture)
            return respond(200, {"ok": True, "verified": True, "alreadyEnrolled": False, "message": "报名请求已提交，并已在“我的报名”中独立核验到该讲座"}, lecture=enrolled)
        except (ApiError, requests_error()) as error:
            code = getattr(error, "code", None) or "REQUEST_FAILED"
            return respond(502, {"ok": False, "verified": False, "error": code, "message": f"报名或回执核验未完成：{error}"}, lecture=lecture)


def enroll_all_lectures(confirm=False):
    from concurrent.futures import ThreadPoolExecutor
    import time
    from enrollment_policy import select_candidates

    if not confirm:
        result = {"ok": False, "verified": False, "error": "CONFIRM_REQUIRED", "message": "必须明确确认后才能批量报名"}
        append_log("enroll_all", "skipped", result)
        return 400, result
    with _enroll_lock:
        started = time.perf_counter()
        candidates = []
        submissions = []
        try:
            snapshot = scrape_lectures()
            candidates = select_candidates(snapshot["lectures"], load_settings().get("locationRules"))
            if not candidates:
                result = {"ok": True, "verified": True, "submittedCount": 0, "verifiedCount": 0, "results": [], "message": "按当前规则没有可提交的课程，未发送报名请求"}
                append_log("enroll_all", "skipped", result)
                return 200, result

            def submit(lecture):
                try:
                    h5_client().apply(lecture["id"])
                    return {"lecture": lecture, "submitted": True, "error": None}
                except (ApiError, requests_error()) as error:
                    return {"lecture": lecture, "submitted": True, "error": str(error)}

            submit_started = time.perf_counter()
            with ThreadPoolExecutor(max_workers=len(candidates), thread_name_prefix="Lecture800NoonApply") as pool:
                submissions = list(pool.map(submit, candidates))
            submit_elapsed_ms = round((time.perf_counter() - submit_started) * 1000)
            receipt = scrape_mine()
            enrolled_ids = {item["id"] for item in receipt["applications"]}
            results = []
            for submission in submissions:
                lecture = submission["lecture"]
                verified = lecture["id"] in enrolled_ids
                results.append({
                    "id": lecture["id"], "title": lecture["title"], "location": lecture["location"],
                    "submitted": True, "verified": verified,
                    "error": None if verified else submission["error"] or "RECEIPT_NOT_FOUND",
                })
            verified_count = sum(item["verified"] for item in results)
            result = {
                "ok": verified_count == len(candidates), "verified": verified_count == len(candidates),
                "submittedCount": len(submissions), "verifiedCount": verified_count,
                "submitElapsedMs": submit_elapsed_ms, "totalElapsedMs": round((time.perf_counter() - started) * 1000),
                "results": results,
                "message": f"已并发提交 {len(submissions)} 场，并发阶段耗时 {submit_elapsed_ms} ms；我的报名核验到 {verified_count} 场。",
            }
            append_log("enroll_all", "success" if result["ok"] else "failed", result)
            return (200 if result["ok"] else 502), result
        except (ApiError, requests_error()) as error:
            results = [
                {"id": item["lecture"]["id"], "title": item["lecture"]["title"], "submitted": True, "verified": False, "error": "RECEIPT_UNVERIFIED"}
                for item in submissions
            ]
            result = {
                "ok": False, "verified": False, "error": getattr(error, "code", None) or "REQUEST_FAILED",
                "submittedCount": len(submissions), "verifiedCount": 0, "results": results,
                "message": f"批量报名或回执核验未完成：{error}；已提交请求不会自动重发，请先查询我的报名。",
            }
            append_log("enroll_all", "failed", result)
            return 502, result


def withdraw_lecture(lecture_id, apply_id, confirm=False):
    def respond(status, payload, lecture=None):
        if lecture:
            payload["lecture"] = {"id": lecture["id"], "title": lecture["title"], "applyId": lecture.get("applyId")}
        append_log("withdraw", "success" if payload.get("verified") else "failed", payload)
        return status, payload

    if not confirm:
        return respond(400, {"ok": False, "verified": False, "error": "CONFIRM_REQUIRED", "message": "必须在退课确认框中再次确认"})
    if not lecture_id or not apply_id:
        return respond(400, {"ok": False, "verified": False, "error": "WITHDRAW_IDS_REQUIRED", "message": "缺少讲座 ID 或报名 ID"})
    with _enroll_lock:
        lecture = None
        try:
            mine = scrape_mine()
            lecture = next((item for item in mine["applications"] if item["id"] == lecture_id), None)
            if lecture is None:
                return respond(404, {"ok": False, "verified": False, "error": "ENROLLMENT_NOT_FOUND", "message": "我的报名中未找到该讲座，未发送退课请求"})
            if str(lecture.get("applyId") or "") != str(apply_id):
                return respond(409, {"ok": False, "verified": False, "error": "APPLY_ID_STALE", "message": "报名记录已变化，请刷新后再操作，未发送退课请求"}, lecture)
            if not lecture.get("canWithdraw"):
                return respond(409, {"ok": False, "verified": False, "error": "WITHDRAW_CLOSED", "message": "该讲座已超出小程序允许的退课时间，未发送退课请求"}, lecture)
            h5_client().withdraw(lecture_id, apply_id)
            receipt = scrape_mine()
            if any(item["id"] == lecture_id for item in receipt["applications"]):
                return respond(502, {"ok": False, "verified": False, "error": "WITHDRAW_RECEIPT_STILL_PRESENT", "message": "退课请求已发送，但该讲座仍在我的报名中，不能记为退课成功"}, lecture)
            return respond(200, {"ok": True, "verified": True, "message": "退课请求已提交，并已独立确认该讲座从我的报名中移除"}, lecture)
        except (ApiError, requests_error()) as error:
            return respond(502, {"ok": False, "verified": False, "error": getattr(error, "code", None) or "REQUEST_FAILED", "message": f"退课或回执核验未完成：{error}"}, lecture)


def create_app():
    app = Flask(__name__)
    capture_manager = CaptureManager(DATA_DIR, SESSION_FILE, refresh_all)
    app.extensions["lecture800_capture"] = capture_manager

    @app.after_request
    def security_headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.route("/api/health")
    def health():
        result = verification_snapshot()
        return jsonify({"connected": result["connected"], "visible": result["connected"], "message": result["checks"][1]["detail"], "time": result["time"]})

    @app.route("/api/verify")
    def verify():
        return jsonify(verification_snapshot())

    @app.route("/api/capture")
    def capture_status():
        return jsonify(capture_manager.snapshot())

    @app.route("/api/capture/start", methods=["POST"])
    def capture_start():
        body = request.get_json(silent=True) or {}
        try:
            result = capture_manager.start(authorized=body.get("authorized") is True)
            append_log("capture", "started", {"message": "用户已在 EXE 内授权进程级会话配置；未修改系统代理。"})
            return jsonify(result), 202
        except ValueError as error:
            return jsonify({"message": str(error), **capture_manager.snapshot()}), 400

    @app.route("/api/capture/cancel", methods=["POST"])
    def capture_cancel():
        result = capture_manager.cancel()
        append_log("capture", "cancelled", {"message": result["detail"]})
        return jsonify(result)

    @app.route("/api/lectures")
    def lectures():
        try:
            return jsonify(scrape_lectures())
        except Exception as error:
            append_log("scrape", "failed", str(error))
            return jsonify({"connected": False, "error": str(error), "fetchedAt": now_iso(), "lectures": []}), 503

    @app.route("/api/mine")
    def mine():
        try:
            return jsonify(scrape_mine())
        except Exception as error:
            return jsonify({"connected": False, "page": "unavailable", "message": str(error)}), 503

    @app.route("/api/refresh", methods=["POST"])
    def refresh():
        try:
            snapshot, _ = refresh_all()
            return jsonify(snapshot)
        except Exception as error:
            append_log("scrape", "failed", str(error))
            return jsonify({"connected": False, "error": str(error), "fetchedAt": now_iso(), "lectures": []}), 503

    @app.route("/api/enroll", methods=["POST"])
    def enroll():
        body = request.get_json(silent=True) or {}
        status, payload = enroll_lecture(str(body.get("lectureId", "")), body.get("confirm") is True)
        return jsonify(payload), status

    @app.route("/api/enroll/all", methods=["POST"])
    def enroll_all():
        body = request.get_json(silent=True) or {}
        status, payload = enroll_all_lectures(confirm=body.get("confirm") is True)
        return jsonify(payload), status

    @app.route("/api/withdraw", methods=["POST"])
    def withdraw():
        body = request.get_json(silent=True) or {}
        status, payload = withdraw_lecture(
            str(body.get("lectureId", "")), str(body.get("applyId", "")), body.get("confirm") is True,
        )
        return jsonify(payload), status

    @app.route("/api/settings", methods=["GET", "PUT"])
    def settings():
        from scheduler import get_scheduler_status
        if request.method == "GET":
            return jsonify({**load_settings(), "runtime": get_scheduler_status()})
        try:
            body = request.get_json(silent=True) or {}
            if "locationRules" in body:
                result = update_settings(
                    auto_enabled=body.get("autoEnabled") if "autoEnabled" in body else None,
                    location_rules=body["locationRules"],
                )
                append_log("scheduler", "updated", {"message": "自动报名设置已保存，下一次预检和报名立即使用新规则。"})
            else:
                result = set_auto_enabled(body.get("autoEnabled"))
            return jsonify({**result, "runtime": get_scheduler_status()})
        except Exception as error:
            return jsonify({"message": str(error)}), 400

    @app.route("/api/logs")
    def logs():
        if not LOG_FILE.exists():
            return jsonify({"logs": []})
        lines = LOG_FILE.read_text(encoding="utf-8").splitlines()[-100:]
        return jsonify({"logs": [json.loads(line) for line in reversed(lines)]})

    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if args.once:
        print(json.dumps(scrape_lectures(), ensure_ascii=False, indent=2))
        return
    create_app().run(host=args.host, port=args.port, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
