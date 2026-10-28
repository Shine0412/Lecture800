import unittest
from unittest.mock import patch

import lecture_agent


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
