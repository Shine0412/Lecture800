import tempfile
import threading
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import lecture_agent
import scheduler


def reset_status():
    with scheduler._status_lock:
        scheduler._status.clear()
        scheduler._status.update({"running": False, "lastRunKey": None, "lastResult": None, "lastError": None})


class ShouldRunTests(unittest.TestCase):
    def test_triggers_only_in_1158_minute_once_per_day(self):
        self.assertTrue(scheduler.should_run(datetime(2026, 11, 6, 11, 58, 30), None))
        self.assertFalse(scheduler.should_run(datetime(2026, 11, 6, 11, 58, 30), "2026-11-06@11:58"))
        self.assertFalse(scheduler.should_run(datetime(2026, 11, 6, 11, 59, 0), None))
        self.assertFalse(scheduler.should_run(datetime(2026, 11, 6, 12, 0, 0), None))

    def test_yesterday_run_key_still_triggers_today(self):
        self.assertTrue(scheduler.should_run(datetime(2026, 11, 6, 11, 58), "2026-11-05@11:58"))


class MissedRunTests(unittest.TestCase):
    def setUp(self):
        reset_status()

    def _announce(self, auto_enabled, last_run_key, now):
        with patch.object(scheduler, "load_settings", return_value={"autoEnabled": auto_enabled, "lastRunKey": last_run_key}), \
             patch.object(scheduler, "datetime") as fake_dt, \
             patch.object(scheduler, "append_log") as fake_log:
            fake_dt.now.return_value = now
            scheduler.announce_missed_run()
            return fake_log

    def test_after_noon_without_today_run_logs_missed(self):
        fake_log = self._announce(True, None, datetime(2026, 11, 6, 13, 0))
        fake_log.assert_called_once()
        self.assertEqual(fake_log.call_args.args[1], "missed")

    def test_today_run_already_completed_does_not_log_missed(self):
        fake_log = self._announce(True, "2026-11-06@11:58", datetime(2026, 11, 6, 13, 0))
        fake_log.assert_not_called()

    def test_before_noon_never_logs_missed(self):
        fake_log = self._announce(True, None, datetime(2026, 11, 6, 10, 0))
        fake_log.assert_not_called()

    def test_disabled_schedule_never_logs_missed(self):
        fake_log = self._announce(False, None, datetime(2026, 11, 6, 13, 0))
        fake_log.assert_not_called()


class LastRunKeyTests(unittest.TestCase):
    def setUp(self):
        reset_status()

    def test_set_last_run_key_persists_to_settings_file(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(lecture_agent, "SETTINGS_FILE", Path(directory) / "settings.json"):
            lecture_agent.set_last_run_key("2026-11-06@11:58")
            self.assertEqual(lecture_agent.load_settings()["lastRunKey"], "2026-11-06@11:58")

    def test_start_scheduler_seeds_last_run_key_from_settings(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(lecture_agent, "SETTINGS_FILE", Path(directory) / "settings.json"), \
             patch.object(scheduler, "load_settings", return_value={"autoEnabled": True, "lastRunKey": "2026-11-06@11:58"}), \
             patch.object(scheduler, "append_log") as fake_log, \
             patch.object(scheduler, "datetime") as fake_dt:
            fake_dt.now.return_value = datetime(2026, 11, 6, 13, 0)
            stop_event, thread = scheduler.start_scheduler()
            try:
                self.assertEqual(scheduler.get_scheduler_status()["lastRunKey"], "2026-11-06@11:58")
                fake_log.assert_not_called()
            finally:
                stop_event.set()
                thread.join(timeout=5)

    def test_start_scheduler_logs_missed_when_run_not_done_today(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(lecture_agent, "SETTINGS_FILE", Path(directory) / "settings.json"), \
             patch.object(scheduler, "load_settings", return_value={"autoEnabled": True, "lastRunKey": "2026-11-05@11:58"}), \
             patch.object(scheduler, "append_log") as fake_log, \
             patch.object(scheduler, "datetime") as fake_dt:
            fake_dt.now.return_value = datetime(2026, 11, 6, 13, 0)
            stop_event, thread = scheduler.start_scheduler()
            try:
                fake_log.assert_called_once()
                self.assertEqual(fake_log.call_args.args[1], "missed")
            finally:
                stop_event.set()
                thread.join(timeout=5)

    def test_loop_persists_run_key_when_triggered(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(lecture_agent, "SETTINGS_FILE", Path(directory) / "settings.json"), \
             patch.object(scheduler, "load_settings", return_value={"autoEnabled": True, "lastRunKey": None}), \
             patch.object(scheduler, "set_last_run_key") as fake_set, \
             patch.object(scheduler, "run_scheduled", return_value={"status": "ready"}), \
             patch.object(scheduler, "datetime") as fake_dt:
            fake_dt.now.return_value = datetime(2026, 11, 6, 11, 58, 10)
            stop_event = threading.Event()
            thread = threading.Thread(target=scheduler.scheduler_loop, args=(stop_event,))
            thread.start()
            deadline = time.time() + 5
            while time.time() < deadline and not fake_set.call_count:
                time.sleep(0.05)
            stop_event.set()
            thread.join(timeout=5)
            fake_set.assert_called_once_with("2026-11-06@11:58")
            self.assertEqual(scheduler.get_scheduler_status()["lastRunKey"], "2026-11-06@11:58")


if __name__ == "__main__":
    unittest.main()
