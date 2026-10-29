import json
import tempfile
import unittest
from pathlib import Path

from h5_client import ApiError, H5Client, SessionStore, normalize_lecture


class MemoryStore:
    def __init__(self):
        self.cookies = {"session": "test-only"}
        self.headers = {}

    def load(self):
        return {"cookies": self.cookies, "headers": self.headers}

    def save(self, cookies, headers=None):
        self.cookies = dict(cookies)
        self.headers = dict(headers or {})


class Response:
    def __init__(self, payload, status=200):
        import requests
        self.payload = payload
        self.status_code = status
        self.cookies = requests.cookies.RequestsCookieJar()

    def json(self):
        return self.payload


class FakeSession:
    routes = {}
    requests = []
    instances = []

    def __init__(self):
        import requests
        self.cookies = requests.cookies.RequestsCookieJar()
        self.headers = {}
        self.instances.append(self)

    def close(self):
        pass

    def request(self, method, url, **kwargs):
        import requests
        self.requests.append((method, url, kwargs))
        result = self.routes[url.rsplit("/api/", 1)[-1]]
        payload = result(kwargs) if callable(result) else result
        if isinstance(payload, requests.RequestException):
            raise payload
        if isinstance(payload, Response):
            return payload
        return Response(payload)


class ClientTests(unittest.TestCase):
    def setUp(self):
        FakeSession.routes = {}
        FakeSession.requests = []
        FakeSession.instances = []
        self.client = H5Client(MemoryStore(), session_factory=FakeSession)

    def test_normalizes_actual_h5_fields_and_status(self):
        item = {
            "chairId": 42, "chairName": "接口测试讲座", "chairType": 0,
            "teacherName": "测试教师", "chairSite": "测试地点", "label": "学术前沿",
            "chairBeginTime": 1_800_000_000, "chairEndTime": 1_800_003_600,
            "applyBeginTime": 1_700_000_000, "currentTime": 1_750_000_000,
            "applyTopNum": 100, "applyNum": 20, "leaveNum": 80, "applyStatus": 0,
        }
        result = normalize_lecture(item)
        self.assertEqual(result["id"], "42")
        self.assertEqual(result["level"], "800")
        self.assertEqual(result["status"], "open")
        self.assertEqual(result["capacity"], 100)
        self.assertEqual(result["enrollmentOpenAt"], "2023-11-15T06:13:20+08:00")

    def test_reads_latest_catalogue_page_without_ui(self):
        FakeSession.routes = {
            "chair/pageChair.do": {"code": "00000", "data": {"records": [{"chairId": 1, "chairName": "L1", "chairType": 0}, {"chairId": 2, "chairName": "L2", "chairType": 0}], "total": 1336, "pages": 27}},
            "common/getBeforeTimeMillis.do": {"code": "00000", "data": 0},
        }
        result = self.client.lectures()
        self.assertEqual(len(result), 2)
        catalogue_calls = [call for call in FakeSession.requests if "pageChair" in call[1]]
        self.assertEqual(len(catalogue_calls), 1)
        self.assertEqual(catalogue_calls[0][2]["params"], {"size": 50, "current": 1, "chairType": 0})

    def test_mine_reads_profile_metrics_and_applications(self):
        FakeSession.routes = {
            "user/getUserInfo.do": {"code": "00000", "data": {"userName": "TEST800"}},
            "user/getRegisrationByUserId.do": {"code": "00000", "data": {"myAppNum": 5, "waitToParticipateNum": 0, "effectiveAttendanceNum": 3, "completedEvaluationNum": 3}},
            "chair/pageUserChair.do": self.user_chair_response,
            "common/getBeforeTimeMillis.do": {"code": "00000", "data": 0},
        }
        result = self.client.mine()
        self.assertEqual(result["profile"]["account"], "TEST800")
        self.assertEqual([metric["value"] for metric in result["metrics"]], [5, 0, 3, 3])
        self.assertEqual(result["applications"][0]["registration"], "enrolled")
        self.assertEqual(result["applications"][0]["attendanceStatus"], "missed")
        self.assertEqual(result["groups"]["missedAttendance"][0]["title"], "已报名讲座")
        self.assertEqual(result["groups"]["pending"][0]["title"], "待参与讲座")
        self.assertEqual(result["groups"]["pendingEvaluation"][0]["title"], "待评价讲座")
        self.assertEqual(result["groups"]["evaluated"][0]["title"], "已评价讲座")
        group_calls = [call for call in FakeSession.requests if "pageUserChair" in call[1]]
        self.assertEqual({call[2]["params"].get("type") for call in group_calls}, {None, 1, 6, 7})

    @staticmethod
    def user_chair_response(kwargs):
        titles = {None: "已报名讲座", 1: "待参与讲座", 6: "待评价讲座", 7: "已评价讲座"}
        group_type = kwargs["params"].get("type")
        title = titles[group_type]
        item = {"chairId": title, "chairName": title, "applyStatus": 1, "signArrive": 1, "applyId": f"apply-{title}"}
        if group_type is None:
            item.update({"signArrive": 0, "chairEndTime": 1_700_000_000_000, "chairBeginTime": 1_700_000_000_000})
        return {"code": "00000", "data": {"records": [item]}}

    def test_reuses_thread_local_https_session(self):
        FakeSession.routes = {"common/getBeforeTimeMillis.do": {"code": "00000", "data": 0}}
        self.client.before_time_millis()
        self.client.before_time_millis()
        self.assertEqual(len(FakeSession.instances), 1)
        self.assertEqual(len(FakeSession.requests), 2)

    def test_get_retries_connection_failure_once(self):
        import requests
        responses = iter([requests.ConnectionError("temporary"), {"code": "00000", "data": 0}])
        FakeSession.routes = {"common/getBeforeTimeMillis.do": lambda kwargs: next(responses)}
        self.assertEqual(self.client.before_time_millis(), 0)
        self.assertEqual(len(FakeSession.requests), 2)

    def test_post_never_retries_connection_failure(self):
        import requests
        FakeSession.routes = {"chair/chairApply.do": requests.ConnectionError("temporary")}
        with self.assertRaises(requests.ConnectionError):
            self.client.apply("42")
        self.assertEqual(len(FakeSession.requests), 1)

    def test_auth_failure_is_not_success(self):
        FakeSession.routes = {"user/getUserInfo.do": {"code": "A0230", "msg": "TOKEN校验失败或过期"}}
        with self.assertRaises(ApiError) as error:
            self.client.request("GET", "/user/getUserInfo.do")
        self.assertEqual(error.exception.code, "A0230")

    def test_apply_requires_success_data(self):
        FakeSession.routes = {"chair/chairApply.do": {"code": "00000", "data": False}}
        with self.assertRaises(ApiError) as error:
            self.client.apply("42")
        self.assertEqual(error.exception.code, "APPLY_NOT_CONFIRMED")
        self.assertEqual(FakeSession.requests[0][2]["data"], {"chairId": "42"})

    def test_withdraw_uses_real_endpoint_and_both_ids(self):
        FakeSession.routes = {"chair/chairElect.do": {"code": "00000", "data": True}}
        self.assertTrue(self.client.withdraw("42", "apply-42"))
        self.assertEqual(FakeSession.requests[0][2]["data"], {"chairId": "42", "applyId": "apply-42"})

    @unittest.skipUnless(__import__("os").name == "nt", "DPAPI 是 Windows 功能")
    def test_dpapi_round_trip_does_not_store_plaintext(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.dpapi"
            store = SessionStore(path)
            store.save({"dummy": "not-a-real-credential"})
            self.assertNotIn("not-a-real-credential", path.read_text(encoding="ascii"))
            self.assertEqual(store.load()["cookies"]["dummy"], "not-a-real-credential")

    @unittest.skipUnless(__import__("os").name == "nt", "DPAPI 是 Windows 功能")
    def test_concurrent_clients_safely_share_session_file_lock(self):
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.dpapi"
            with ThreadPoolExecutor(max_workers=8) as pool:
                futures = [pool.submit(SessionStore(path).save, {"dummy": f"test-{index}"}) for index in range(8)]
                for future in futures:
                    future.result(timeout=5)
            cookies = SessionStore(path).load()["cookies"]
            self.assertIn(cookies["dummy"], {f"test-{index}" for index in range(8)})


if __name__ == "__main__":
    unittest.main()
