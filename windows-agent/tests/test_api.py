import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import lecture_agent


class MineCacheTests(unittest.TestCase):
    def setUp(self):
        lecture_agent.invalidate_mine_cache()
        app = lecture_agent.create_app()
        app.testing = True
        self.client = app.test_client()

    @patch("lecture_agent.scrape_mine", side_effect=[{"applications": ["first"]}, {"applications": ["second"]}])
    def test_route_caches_within_ttl_and_refresh_bypasses(self, scrape):
        self.assertEqual(self.client.get("/api/mine").get_json()["applications"], ["first"])
        self.assertEqual(self.client.get("/api/mine").get_json()["applications"], ["first"])
        self.assertEqual(self.client.get("/api/mine?refresh=true").get_json()["applications"], ["second"])
        self.assertEqual(scrape.call_count, 2)

    @patch("lecture_agent.scrape_mine")
    def test_enrollment_invalidation_forces_next_route_call_to_refetch(self, scrape):
        scrape.side_effect = [{"applications": ["old"]}, {"applications": ["new"]}]
        self.assertEqual(self.client.get("/api/mine").get_json()["applications"], ["old"])
        lecture_agent.invalidate_mine_cache()
        self.assertEqual(self.client.get("/api/mine").get_json()["applications"], ["new"])
        self.assertEqual(scrape.call_count, 2)


class LectureSnapshotCandidatesTests(unittest.TestCase):
    def setUp(self):
        self.app = lecture_agent.create_app()
        self.app.testing = True
        self.client = self.app.test_client()

    @patch("lecture_agent.h5_client")
    def test_lectures_route_includes_backend_computed_candidates(self, client):
        client.return_value.lectures.return_value = [
            {"id": "first", "title": "讲座", "level": "800", "status": "open", "registration": None, "location": "一号院101"},
            {"id": "nanjing", "title": "南京校区讲座", "level": "800", "status": "open", "registration": None, "location": "某地"},
        ]
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(lecture_agent, "SNAPSHOT_FILE", Path(directory) / "latest-snapshot.json"), \
             patch.object(lecture_agent, "SETTINGS_FILE", Path(directory) / "settings.json"):
            payload = self.client.get("/api/lectures").get_json()
        self.assertEqual(payload["candidates"], ["first"])


class ImmediateBatchApiTests(unittest.TestCase):
    def setUp(self):
        app = lecture_agent.create_app()
        app.testing = True
        self.client = app.test_client()

    @patch("lecture_agent.enroll_all_lectures")
    def test_immediate_batch_requires_explicit_confirmation(self, enroll_all):
        enroll_all.return_value = (400, {"ok": False, "verified": False, "error": "CONFIRM_REQUIRED"})
        response = self.client.post("/api/enroll/all", json={})
        self.assertEqual(response.status_code, 400)
        enroll_all.assert_called_once_with(confirm=False)

    @patch("lecture_agent.enroll_all_lectures")
    def test_immediate_batch_executes_without_changing_daily_schedule(self, enroll_all):
        enroll_all.return_value = (200, {
            "ok": True, "verified": True, "submittedCount": 1,
            "verifiedCount": 1, "results": [], "message": "模拟报名成功",
        })
        response = self.client.post("/api/enroll/all", json={"confirm": True})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["verifiedCount"], 1)
        enroll_all.assert_called_once_with(confirm=True)


if __name__ == "__main__":
    unittest.main()
