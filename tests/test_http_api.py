from __future__ import annotations

import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.app import create_app
from api.middleware import MAX_BODY_SIZE
from cognitive_memory import Memory


class HttpApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app(":memory:"))
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def request(self, method: str, path: str, payload: dict | None = None):
        response = self.client.request(method, path, json=payload)
        content_type = response.headers.get("content-type", "")
        parsed = (
            response.json() if "application/json" in content_type else response.content
        )
        return response.status_code, parsed, content_type

    def test_health_and_index(self):
        status, data, _ = self.request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "ok")
        status, body, content_type = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", content_type)
        self.assertIn("记忆工作台".encode(), body)

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

    def test_overview_counts_user_scope_and_storage(self):
        self.request(
            "POST", "/api/memories", {"user_id": "alice", "content": "用户喜欢 Python"}
        )
        alice = self.client.get("/api/overview?user_id=alice").json()
        bob = self.client.get("/api/overview?user_id=bob").json()
        self.assertEqual(alice["total_count"], 1)
        self.assertEqual(sum(alice["by_type"].values()), 1)
        self.assertEqual(bob["total_count"], 0)
        self.assertEqual(bob["recent_activity"], [])
        self.assertEqual(alice["storage"]["scope"], "database")
        self.assertGreater(alice["storage"]["allocated_bytes"], 0)
        self.assertEqual(alice["storage"]["mode"], "memory")
        self.assertEqual(alice["storage"], bob["storage"])
        self.assertEqual(alice["modules"][-2]["status"], "unconfigured")

    def test_memory_list_limit(self):
        for index in range(3):
            self.request("POST", "/api/memories", {"content": f"任务记录 {index}"})
        self.assertEqual(
            len(self.client.get("/api/memories?limit=2").json()["items"]), 2
        )
        self.assertEqual(self.client.get("/api/memories?limit=1001").status_code, 400)

    def test_frontend_assets_are_served(self):
        index = self.client.get("/").text
        assets = re.findall(r'(?:src|href)="(/assets/[^"]+)"', index)
        self.assertTrue(any(path.endswith(".js") for path in assets))
        self.assertTrue(any(path.endswith(".css") for path in assets))
        for path in assets:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn(
                "javascript" if path.endswith(".js") else "text/css",
                response.headers["content-type"],
            )

    def test_backend_works_without_frontend_build(self):
        with (
            TemporaryDirectory() as directory,
            patch("api.app.STATIC_ROOT", Path(directory)),
        ):
            with TestClient(create_app(":memory:")) as client:
                self.assertEqual(client.get("/").status_code, 503)
                self.assertEqual(client.get("/api/health").status_code, 200)
                self.assertEqual(client.get("/docs").status_code, 200)

    def test_validation_error(self):
        status, data, _ = self.request(
            "POST", "/api/memories", {"user_id": "http-user", "content": ""}
        )
        self.assertEqual(status, 400)
        self.assertEqual(data["error"], "validation_error")

    def test_openapi_documents_request_fields(self):
        schema = self.client.get("/openapi.json").json()
        self.assertIn("/api/memories", schema["paths"])
        self.assertIn(
            "content", schema["components"]["schemas"]["MemoryRequest"]["properties"]
        )
        self.assertEqual(self.client.get("/docs").status_code, 200)

    def test_malformed_json_and_invalid_fields_return_400(self):
        for body in ("{", "[]", '{"top_k":"invalid"}', '{"query":null}'):
            with self.subTest(body=body):
                response = self.client.post(
                    "/api/search",
                    content=body,
                    headers={"content-type": "application/json"},
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["error"], "validation_error")
                self.assertIsInstance(response.json()["message"], str)

    def test_request_size_limit_with_and_without_content_length(self):
        oversized = b"x" * (MAX_BODY_SIZE + 1)
        for content in (oversized, iter([oversized[:500000], oversized[500000:]])):
            response = self.client.post("/api/memories", content=content)
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["message"], "请求体过大")
        self.assertEqual(self.client.get("/api/memories").json()["items"], [])

    def test_create_list_audit_retention_and_delete(self):
        status, result, _ = self.request(
            "POST",
            "/api/memories",
            {
                "user_id": "alice",
                "content": "用户喜欢 Python",
                "tags": "preference",
            },
        )
        self.assertEqual(status, 201)
        memory_id = result["memory"]["id"]
        self.assertEqual(
            len(self.client.get("/api/memories?user_id=alice").json()["items"]), 1
        )
        self.assertTrue(self.client.get("/api/audit?user_id=alice").json()["items"])
        self.assertIn("write_threshold", self.client.get("/api/config").json())
        self.assertEqual(
            self.client.post(
                "/api/maintenance/retention", json={"user_id": "alice"}
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.delete(f"/api/memories/{memory_id}?user_id=bob").status_code,
            404,
        )
        self.assertTrue(
            self.client.delete(f"/api/memories/{memory_id}?user_id=alice").json()[
                "deleted"
            ]
        )
        self.assertEqual(
            self.client.delete(f"/api/memories/{memory_id}?user_id=alice").status_code,
            404,
        )

    def test_unknown_api_and_static_traversal(self):
        for method in ("GET", "POST", "DELETE"):
            response = self.client.request(method, "/api/unknown")
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json()["error"], "not_found")
        self.assertIn(self.client.get("/%2e%2e/pyproject.toml").status_code, (403, 404))

    def test_internal_error_keeps_json_contract(self):
        with Memory() as memory:
            with TestClient(
                create_app(service=memory), raise_server_exceptions=False
            ) as client:
                with patch.object(
                    memory, "stats", side_effect=RuntimeError("storage failed")
                ):
                    response = client.get("/api/stats")
                self.assertEqual(response.status_code, 500)
                self.assertEqual(response.json()["error"], "internal_error")
                self.assertEqual(response.headers["cache-control"], "no-store")

    def test_cache_headers(self):
        self.assertEqual(
            self.client.get("/api/health").headers["cache-control"], "no-store"
        )
        self.assertEqual(self.client.get("/").headers["cache-control"], "no-cache")


class AppLifecycleTests(unittest.TestCase):
    def test_lifespan_closes_owned_memory(self):
        memory = Memory()
        with (
            patch("api.app.Memory", return_value=memory),
            patch.object(memory, "close", wraps=memory.close) as close,
        ):
            application = create_app(":memory:")
            with TestClient(application) as client:
                self.assertEqual(client.get("/api/stats").status_code, 200)
                close.assert_not_called()
            close.assert_called_once()

    def test_lifespan_preserves_injected_memory(self):
        with Memory() as memory:
            with TestClient(create_app(service=memory)) as client:
                self.assertEqual(client.get("/api/stats").status_code, 200)
            self.assertEqual(memory.stats("demo-user")["active_count"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
