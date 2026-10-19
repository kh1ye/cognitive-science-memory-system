import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.app import create_app
from conversation_agent.llm import LLMSettings


class OverviewTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app(":memory:", demo_token=""))
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.agent = self.client.app.state.conversation_agent
        self.agent.settings = LLMSettings(api_key="")

    def add(self, content, user_id="alice", **values):
        return self.client.post("/api/memories", json={
            "user_id": user_id, "content": content, **values,
        }).json()["memory"]

    def overview(self, user_id="alice"):
        return self.client.get("/api/overview", params={"user_id": user_id}).json()

    def test_recent_activity_links_owned_existing_records_and_normalizes_user(self):
        record = self.add("我喜欢喝茶。")
        result = self.overview(" ALICE ")
        self.assertEqual(result["total_count"], 1)
        related = result["recent_activity"][0]["related_memory"]
        self.assertEqual(related["id"], record["id"])
        self.assertEqual(related["content"], "我喜欢喝茶。")
        self.assertEqual(set(related), {"id", "content", "memory_type", "state_role"})
        self.assertEqual(self.overview("bob")["recent_activity"], [])

    def test_deleted_body_is_not_returned_through_older_activity(self):
        record = self.add("此处的私人正文必须在删除后消失")
        self.client.delete(f"/api/memories/{record['id']}?user_id=alice")
        result = self.overview()
        self.assertEqual(result["total_count"], 0)
        self.assertEqual(len(result["recent_activity"]), 2)
        self.assertTrue(all(event["related_memory"] is None for event in result["recent_activity"]))
        self.assertNotIn("此处的私人正文必须在删除后消失", str(result))

    def test_foreign_user_record_cannot_be_resolved_from_audit_reference(self):
        record = self.add("bob 的正文", user_id="bob")
        memory = self.client.app.state.memory
        with memory.storage.transaction():
            memory.storage.audit("alice", "REINFORCE", "测试关联", record["id"])
        result = self.overview()
        self.assertIsNone(result["recent_activity"][0]["related_memory"])
        self.assertNotIn("bob 的正文", str(result))

    def test_configured_model_is_not_claimed_connected_and_overview_is_read_only(self):
        self.agent.settings = LLMSettings(api_key="secret-test-key", model="test-model")
        self.add("保留一条测试记忆")
        before = self.client.get("/api/stats?user_id=alice").json()
        with patch.object(self.agent, "_get_model", side_effect=AssertionError("must not call model")):
            result = self.overview()
        language = next(module for module in result["modules"] if module["name"] == "语言模型")
        vector = next(module for module in result["modules"] if module["name"] == "向量模型")
        self.assertEqual(language["status"], "configured")
        self.assertIn("尚未验证连接", language["description"])
        self.assertEqual(vector["status"], "not_implemented")
        self.assertNotIn("secret-test-key", str(result))
        self.assertEqual(self.client.get("/api/stats?user_id=alice").json(), before)

    def test_unconfigured_and_unsupported_provider_are_distinguished(self):
        language = next(module for module in self.overview()["modules"] if module["name"] == "语言模型")
        self.assertEqual(language["status"], "unconfigured")
        self.agent.settings = LLMSettings(api_key="test", provider="unsupported-provider")
        language = next(module for module in self.overview()["modules"] if module["name"] == "语言模型")
        self.assertEqual(language["status"], "unsupported")


if __name__ == "__main__":
    unittest.main()
