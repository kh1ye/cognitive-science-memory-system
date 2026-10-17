from __future__ import annotations

import json
import threading
import unittest
from http.client import HTTPConnection

from api.app import MemoryHTTPServer
from cognitive_memory import Memory


class HttpApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.service = Memory(":memory:")
        cls.server = MemoryHTTPServer(("127.0.0.1", 0), cls.service)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.service.close()
        cls.thread.join(timeout=2)

    def request(self, method: str, path: str, payload: dict | None = None):
        connection = HTTPConnection("127.0.0.1", self.port, timeout=4)
        body = (
            json.dumps(payload, ensure_ascii=False).encode("utf-8")
            if payload is not None
            else None
        )
        headers = {"Content-Type": "application/json"} if body is not None else {}
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        data = response.read()
        content_type = response.getheader("Content-Type", "")
        connection.close()
        parsed = (
            json.loads(data.decode("utf-8"))
            if "application/json" in content_type
            else data
        )
        return response.status, parsed, content_type

    def test_health_and_index(self):
        status, data, _ = self.request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "ok")
        status, body, content_type = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", content_type)
        self.assertIn(b"Cognitive Memory Lab", body)

    def test_seed_search_and_stats_flow(self):
        status, seeded, _ = self.request(
            "POST", "/api/demo/seed", {"user_id": "http-user"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(seeded["events"][3]["decision"], "CONSOLIDATED")
        status, result, _ = self.request(
            "POST",
            "/api/search",
            {"user_id": "http-user", "query": "主要使用什么编程语言？", "top_k": 5},
        )
        self.assertEqual(status, 200)
        self.assertTrue(result["grounded"])
        self.assertIn("Rust", result["answer"])
        status, stats, _ = self.request("GET", "/api/stats?user_id=http-user")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(stats["by_role"]["current"], 2)

    def test_validation_error(self):
        status, data, _ = self.request(
            "POST", "/api/memories", {"user_id": "http-user", "content": ""}
        )
        self.assertEqual(status, 400)
        self.assertEqual(data["error"], "validation_error")


if __name__ == "__main__":
    unittest.main(verbosity=2)
