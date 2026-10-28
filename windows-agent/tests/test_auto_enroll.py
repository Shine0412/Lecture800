import unittest
from unittest.mock import Mock, patch

import auto_enroll
import lecture_agent


TARGET = {
    "id": "target-800", "title": "符合条件的讲座", "level": "800",
    "status": "open", "registration": None, "startAt": "2026-10-30T18:30:00+08:00",
    "remaining": 10, "location": "一号院101",
}


class CandidateTests(unittest.TestCase):
    def test_excludes_campuses_and_third_site_then_prioritizes_first_site(self):
        other = {**TARGET, "id": "other", "location": "二号院201", "startAt": "2026-10-29T18:30:00+08:00"}
        first = {**TARGET, "id": "first", "location": "一号院101", "startAt": "2026-11-02T18:30:00+08:00"}
        lectures = [
            other, first,
            {**TARGET, "id": "nanjing", "title": "  南京校区测试讲座"},
            {**TARGET, "id": "wuhan", "title": "武汉校区测试讲座"},
            {**TARGET, "id": "third", "location": "三号院学术交流中心"},
            {**TARGET, "id": "registered", "registration": "enrolled"},
            {**TARGET, "id": "full", "status": "full"},
            {**TARGET, "id": "other-level", "level": "视野"},
        ]
        self.assertEqual([item["id"] for item in auto_enroll.select_candidates(lectures)], ["first", "other"])

    def test_user_location_rules_are_honored_without_fallback_to_all(self):
        lectures = [
            {**TARGET, "id": "first"},
            {**TARGET, "id": "third", "location": "三号院101"},
            {**TARGET, "id": "nanjing", "title": "南京校区测试"},
        ]
        rules = {"firstSite": False, "secondSite": False, "thirdSite": True, "nanjing": True, "wuhan": False, "other": False}
        self.assertEqual({item["id"] for item in auto_enroll.select_candidates(lectures, rules)}, {"third", "nanjing"})
        self.assertEqual(auto_enroll.select_candidates(lectures, {key: False for key in rules}), [])

    @patch("auto_enroll.append_log")
    @patch("auto_enroll.enroll_all_lectures")
    @patch("auto_enroll.load_settings", return_value={"autoEnabled": True})
    @patch("auto_enroll.scrape_lectures", return_value={"lectures": [TARGET], "count": 1, "source": "test"})
    def test_manual_precheck_never_submits(self, _scrape, _settings, enroll, _log):
        result = auto_enroll.run_scheduled()
        self.assertEqual(result["phase"], "manual_precheck")
        self.assertEqual(result["status"], "ready")
        enroll.assert_not_called()


class BatchEnrollmentTests(unittest.TestCase):
    @patch("lecture_agent.append_log")
    @patch("lecture_agent.h5_client")
    @patch("lecture_agent.scrape_mine")
    @patch("lecture_agent.scrape_lectures")
    def test_all_candidates_submit_concurrently_with_one_receipt_read(self, snapshot, mine, client, _log):
        first = {**TARGET, "id": "first", "location": "一号院101", "startAt": "2026-11-02T18:30:00+08:00"}
        other = {**TARGET, "id": "other", "location": "二号院201", "startAt": "2026-10-29T18:30:00+08:00"}
        excluded = {**TARGET, "id": "third", "location": "三号院101"}
        snapshot.return_value = {"lectures": [other, excluded, first]}
        mine.return_value = {"applications": [{**first, "registration": "enrolled"}, {**other, "registration": "enrolled"}]}
        import threading
        import time
        barrier = threading.Barrier(2)

        def slow_apply(_lecture_id):
            barrier.wait(timeout=1)
            time.sleep(0.08)

        client.return_value.apply.side_effect = slow_apply
        status, result = lecture_agent.enroll_all_lectures(confirm=True)
        self.assertEqual(status, 200)
        self.assertEqual(result["submittedCount"], 2)
        self.assertEqual(result["verifiedCount"], 2)
        self.assertEqual([item["id"] for item in result["results"]], ["first", "other"])
        self.assertIsInstance(result["submitElapsedMs"], int)
        self.assertLess(result["submitElapsedMs"], 140, "两场各 80 ms 的请求必须并行，不能串行耗时 160 ms")
        self.assertEqual(client.return_value.apply.call_count, 2)
        self.assertEqual({call.args[0] for call in client.return_value.apply.call_args_list}, {"first", "other"})
        snapshot.assert_called_once_with()
        mine.assert_called_once_with()


class EnrollmentTests(unittest.TestCase):
    @patch("lecture_agent.append_log")
    @patch("lecture_agent.scrape_lectures")
    def test_requires_explicit_confirmation(self, scrape, _log):
        status, result = lecture_agent.enroll_lecture("target-800")
        self.assertEqual(status, 400)
        self.assertFalse(result["verified"])
        scrape.assert_not_called()

    @patch("lecture_agent.append_log")
    @patch("lecture_agent.h5_client")
    @patch("lecture_agent.scrape_mine")
    @patch("lecture_agent.scrape_lectures", return_value={"lectures": [{**TARGET, "title": "南京校区测试讲座"}]})
    def test_nanjing_is_never_submitted(self, _snapshot, mine, client, _log):
        status, result = lecture_agent.enroll_lecture("target-800", confirm=True)
        self.assertEqual(status, 400)
        self.assertEqual(result["error"], "NANJING_EXCLUDED")
        mine.assert_not_called()
        client.assert_not_called()

    @patch("lecture_agent.append_log")
    @patch("lecture_agent.h5_client")
    @patch("lecture_agent.scrape_mine", side_effect=[{"applications": []}, {"applications": [{**TARGET, "registration": "enrolled"}]}])
    @patch("lecture_agent.scrape_lectures", return_value={"lectures": [TARGET]})
    def test_success_requires_independent_mine_receipt(self, _snapshot, mine, client, _log):
        status, result = lecture_agent.enroll_lecture("target-800", confirm=True)
        self.assertEqual(status, 200)
        self.assertTrue(result["ok"])
        self.assertTrue(result["verified"])
        self.assertFalse(result["alreadyEnrolled"])
        client.return_value.apply.assert_called_once_with("target-800")
        self.assertEqual(mine.call_count, 2)

    @patch("lecture_agent.append_log")
    @patch("lecture_agent.h5_client")
    @patch("lecture_agent.scrape_mine", side_effect=[{"applications": []}, {"applications": []}])
    @patch("lecture_agent.scrape_lectures", return_value={"lectures": [TARGET]})
    def test_http_apply_without_receipt_is_not_success(self, _snapshot, _mine, client, _log):
        status, result = lecture_agent.enroll_lecture("target-800", confirm=True)
        self.assertEqual(status, 502)
        self.assertFalse(result["ok"])
        self.assertFalse(result["verified"])
        self.assertEqual(result["error"], "RECEIPT_NOT_FOUND")
        client.return_value.apply.assert_called_once_with("target-800")

    @patch("lecture_agent.append_log")
    @patch("lecture_agent.h5_client")
    @patch("lecture_agent.scrape_mine", return_value={"applications": [{**TARGET, "registration": "enrolled"}]})
    @patch("lecture_agent.scrape_lectures", return_value={"lectures": [TARGET]})
    def test_existing_enrollment_is_not_submitted_again(self, _snapshot, _mine, client, _log):
        status, result = lecture_agent.enroll_lecture("target-800", confirm=True)
        self.assertEqual(status, 200)
        self.assertTrue(result["verified"])
        self.assertTrue(result["alreadyEnrolled"])
        client.assert_not_called()


class WithdrawTests(unittest.TestCase):
    enrolled = {**TARGET, "registration": "enrolled", "applyId": "apply-1", "canWithdraw": True}

    @patch("lecture_agent.append_log")
    @patch("lecture_agent.scrape_mine")
    def test_withdraw_requires_confirmation(self, mine, _log):
        status, result = lecture_agent.withdraw_lecture("target-800", "apply-1")
        self.assertEqual(status, 400)
        self.assertEqual(result["error"], "CONFIRM_REQUIRED")
        mine.assert_not_called()

    @patch("lecture_agent.append_log")
    @patch("lecture_agent.h5_client")
    @patch("lecture_agent.scrape_mine", side_effect=[{"applications": [enrolled]}, {"applications": []}])
    def test_withdraw_uses_apply_id_and_verifies_absence(self, mine, client, _log):
        status, result = lecture_agent.withdraw_lecture("target-800", "apply-1", confirm=True)
        self.assertEqual(status, 200)
        self.assertTrue(result["verified"])
        client.return_value.withdraw.assert_called_once_with("target-800", "apply-1")
        self.assertEqual(mine.call_count, 2)

    @patch("lecture_agent.append_log")
    @patch("lecture_agent.h5_client")
    @patch("lecture_agent.scrape_mine", side_effect=[{"applications": [enrolled]}, {"applications": [enrolled]}])
    def test_withdraw_is_not_success_while_receipt_still_present(self, _mine, client, _log):
        status, result = lecture_agent.withdraw_lecture("target-800", "apply-1", confirm=True)
        self.assertEqual(status, 502)
        self.assertFalse(result["verified"])
        self.assertEqual(result["error"], "WITHDRAW_RECEIPT_STILL_PRESENT")
        client.return_value.withdraw.assert_called_once()

    @patch("lecture_agent.append_log")
    @patch("lecture_agent.h5_client")
    @patch("lecture_agent.scrape_mine", return_value={"applications": [enrolled]})
    def test_stale_apply_id_never_submits(self, _mine, client, _log):
        status, result = lecture_agent.withdraw_lecture("target-800", "old-apply", confirm=True)
        self.assertEqual(status, 409)
        self.assertEqual(result["error"], "APPLY_ID_STALE")
        client.assert_not_called()


if __name__ == "__main__":
    unittest.main()
