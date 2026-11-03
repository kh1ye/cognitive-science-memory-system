"""The UI control changes persisted policy, without changing stored evidence."""
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from api.app import create_app
from cognitive_memory import Memory


class RetentionControlTests(unittest.TestCase):
    def test_read_only_api_returns_real_curve_parameters_and_full_summary(self):
        with Memory() as memory, TestClient(create_app(service=memory)) as client:
            row = memory.add_memory({"user_id": "alice", "content": "独立事件", "importance": .6})["memory"]
            memory.add_memory({"user_id": "alice", "content": "保护偏好", "tags": ["preference"]})
            memory.add_memory({"user_id": "bob", "content": "其他空间事件"})
            before = memory.list_audit("alice")
            response = client.get("/api/retention?user_id=alice&limit=1")
            self.assertEqual(response.status_code, 200)
            result = response.json()
            self.assertTrue(result["enabled"])
            self.assertEqual(result["summary"]["total"], 2)
            self.assertEqual(result["summary"]["protected"], 1)
            self.assertTrue(result["truncated"])
            self.assertEqual(len(result["items"]), 1)
            point = result["items"][0]
            state = memory.retention.state(point, datetime.fromisoformat(result["evaluated_at"]))
            self.assertEqual(point["retention_probability"], state["retention_probability"])
            self.assertEqual(memory.list_audit("alice"), before)
            self.assertEqual(memory.storage.get_memory(row["id"]), row)

    def test_switch_is_persistent_normalized_and_isolated_between_users(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "memory.db"
            with Memory(path) as memory, TestClient(create_app(service=memory)) as client:
                result = client.put("/api/retention/settings", json={"user_id": " ALICE ", "enabled": False})
                self.assertEqual(result.status_code, 200)
                self.assertEqual(result.json(), {"user_id": "alice", "enabled": False})
                self.assertFalse(client.get("/api/retention?user_id=alice").json()["enabled"])
                self.assertTrue(client.get("/api/retention?user_id=bob").json()["enabled"])
                self.assertEqual(client.put("/api/retention/settings", json={"user_id": "alice"}).status_code, 400)
            with Memory(path) as reopened:
                self.assertFalse(reopened.retention.is_enabled("alice"))
                self.assertTrue(reopened.retention.is_enabled("bob"))

    def test_disabled_switch_blocks_archival_and_reenable_uses_elapsed_time(self):
        with Memory() as memory:
            row = memory.add_memory({"user_id": "alice", "content": "普通事件", "importance": .6})["memory"]
            evidence = memory.evidence("alice", row["id"])
            future = datetime.fromisoformat(row["created_at"]) + timedelta(days=365)
            memory.retention.set_enabled("alice", False)
            result = memory.run_retention("alice", future)
            self.assertEqual(result["reason"], "retention_disabled")
            self.assertEqual(result["archived_ids"], [])
            self.assertEqual(memory.storage.get_memory(row["id"]), row)
            memory.retention.set_enabled("alice", True)
            self.assertEqual(memory.run_retention("alice", future)["archived_ids"], [row["id"]])
            self.assertEqual(memory.evidence("alice", row["id"]), evidence)

    def test_switch_controls_real_retrieval_scores(self):
        with Memory() as memory:
            row = memory.add_memory({"user_id": "alice", "content": "苹果事件"})["memory"]
            old = {**row, "id": "old", "created_at": "2000-01-01T00:00:00+00:00"}
            ranked = memory.retriever.rank_candidates([old, row], "苹果")
            self.assertGreater(ranked[0]["retrieval"]["score"], ranked[1]["retrieval"]["score"])
            memory.retention.set_enabled("alice", False)
            disabled = memory.retriever.rank_candidates([old, row], "苹果")
            self.assertEqual(disabled[0]["retrieval"]["score"], disabled[1]["retrieval"]["score"])
            self.assertEqual(disabled[0]["retrieval"]["retention_factor"], 1.0)
            memory.retention.set_enabled("alice", True)
            restored = memory.retriever.rank_candidates([old, row], "苹果")
            self.assertEqual(restored[1]["retrieval"]["score"], ranked[1]["retrieval"]["score"])

    def test_failed_setting_write_rolls_back_and_reports_error(self):
        with Memory() as memory, TestClient(create_app(service=memory)) as client:
            with patch.object(memory.storage, "audit", side_effect=ValueError("设置保存失败")):
                response = client.put("/api/retention/settings", json={"user_id": "alice", "enabled": False})
            self.assertEqual(response.status_code, 400)
            self.assertTrue(memory.retention.is_enabled("alice"))


if __name__ == "__main__":
    unittest.main()
