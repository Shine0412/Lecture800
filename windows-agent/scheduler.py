from __future__ import annotations

import threading
from datetime import datetime

from auto_enroll import run_scheduled
from lecture_agent import append_log, load_settings, now_iso

_status_lock = threading.Lock()
_status = {"running": False, "lastRunKey": None, "lastResult": None, "lastError": None}


def get_scheduler_status():
    with _status_lock:
        return dict(_status)


def should_run(now, last_run_key):
    run_key = now.strftime("%Y-%m-%d@11:58")
    return now.hour == 11 and now.minute == 58 and run_key != last_run_key


def scheduler_loop(stop_event):
    global _status
    while not stop_event.is_set():
        settings = load_settings()
        now = datetime.now()
        if settings["autoEnabled"] and should_run(now, get_scheduler_status()["lastRunKey"]):
            run_key = now.strftime("%Y-%m-%d@11:58")
            with _status_lock:
                _status.update({"running": True, "lastRunKey": run_key, "lastError": None})
            try:
                result = run_scheduled()
                with _status_lock:
                    _status.update({"running": False, "lastResult": result, "completedAt": now_iso()})
            except Exception as error:
                append_log("scheduler", "failed", str(error))
                with _status_lock:
                    _status.update({"running": False, "lastError": str(error), "completedAt": now_iso()})
        stop_event.wait(1)


def start_scheduler():
    stop_event = threading.Event()
    thread = threading.Thread(target=scheduler_loop, args=(stop_event,), daemon=True, name="Lecture800Scheduler")
    thread.start()
    return stop_event, thread
