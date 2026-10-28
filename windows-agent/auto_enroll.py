from __future__ import annotations

import json
from datetime import datetime

from enrollment_policy import exclusion_reason, select_candidates
from lecture_agent import append_log, enroll_all_lectures, load_settings, now_iso, scrape_lectures


def run_precheck():
    snapshot = scrape_lectures()
    location_rules = load_settings().get("locationRules")
    candidates = select_candidates(snapshot["lectures"], location_rules)
    excluded_count = sum(exclusion_reason(item, location_rules) is not None for item in snapshot["lectures"])
    result = {
        "status": "no_open_lecture" if not candidates else "ready",
        "writeEnabled": True,
        "candidateCount": len(candidates),
        "excludedCount": excluded_count,
        "visibleCount": snapshot["count"],
        "source": snapshot["source"],
        "locationRules": location_rules,
        "candidates": [
            {"id": item["id"], "title": item["title"], "startAt": item["startAt"], "location": item["location"], "remaining": item["remaining"]}
            for item in candidates
        ],
        "message": (
            f"接口发现 {len(candidates)} 场符合当前地点选择的可报名讲座；12:00 将全部并发提交，优先一号院。"
            if candidates else f"已通过接口检查 {snapshot['count']} 场 800 级讲座，按当前校区和地点规则暂无可报名课程。"
        ),
        "checkedAt": now_iso(),
    }
    append_log("auto_enroll", "precheck", result)
    return result


def run_scheduled():
    import time

    if not load_settings()["autoEnabled"]:
        result = {"status": "disabled", "phase": "manual_precheck", "message": "自动报名已关闭，未执行每日任务。", "checkedAt": now_iso()}
        append_log("auto_enroll", "skipped", result)
        return result
    precheck = run_precheck()
    now = datetime.now()
    if now.hour == 11 and now.minute in (58, 59):
        target = now.replace(hour=12, minute=0, second=0, microsecond=0)
        while datetime.now() < target:
            time.sleep(min(1, max(0.05, (target - datetime.now()).total_seconds())))
        _, receipt = enroll_all_lectures(confirm=True)
        results = receipt.get("results") or []
        return {
            "status": "enrolled" if receipt.get("verified") and results else "no_open_lecture" if not results else "enroll_failed",
            "phase": "noon_check_complete", "precheck": precheck,
            "results": results, "verifiedCount": receipt.get("verifiedCount", 0),
            "submittedCount": receipt.get("submittedCount", 0),
            "submitElapsedMs": receipt.get("submitElapsedMs"),
            "message": receipt.get("message"), "checkedAt": now_iso(),
        }
    precheck["phase"] = "manual_precheck"
    return precheck


if __name__ == "__main__":
    print(json.dumps(run_scheduled(), ensure_ascii=False))
