"""API regressions for real conversation provenance after typed-storage migration."""

import unittest

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from api.app import create_app


class SourceModel:
    def invoke(self, messages):
        return AIMessage(content="已收到")

    def with_structured_output(self, schema, **kwargs):
        return RunnableLambda(lambda messages: schema.model_validate({
            "semantic_candidates": [{"subject": "alice", "predicate": "favorite_drink",
                "value": "乌龙茶", "evidence_text": "我喜欢喝乌龙茶。"}]
        }))


class SourceProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app(":memory:", demo_token="", chat_model=SourceModel()))
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def evidence(self, memory_id):
        response = self.client.get(f"/api/memories/{memory_id}/evidence?user_id=alice")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["items"]

    def add(self, content="手动输入的测试偏好", **values):
        response = self.client.post("/api/memories", json={
            "user_id": "alice", "content": content, **values})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["memory"]["id"]

    def test_manual_form_has_evidence_without_fabricated_conversation(self):
        memory_id = self.add()
        item, = self.evidence(memory_id)
        self.assertEqual(item["content"], "手动输入的测试偏好")
        self.assertIsNone(item["thread_id"])
        self.assertIsNone(item["message_id"])
        self.assertTrue(item["source_event_id"])

    def test_policy_sources_preserve_message_id_instead_of_origin_hash(self):
        memory_id = self.add(metadata={"thread_id": "real-chat", "message_id": "real-message"})
        item, = self.evidence(memory_id)
        self.assertEqual((item["thread_id"], item["message_id"]), ("real-chat", "real-message"))
        self.assertNotEqual(item["source_event_id"], "real-message")
        self.assertEqual(self.client.get(
            f"/api/memories/{memory_id}/evidence?user_id=bob").status_code, 404)

    def test_thread_only_and_legitimately_named_manual_thread_remain_known(self):
        for thread in ("older-chat", "manual"):
            with self.subTest(thread=thread):
                memory_id = self.add(content=f"来自{thread}的偏好", metadata={"thread_id": thread})
                item, = self.evidence(memory_id)
                self.assertEqual(item["thread_id"], thread)
                self.assertIsNone(item["message_id"])

    def test_already_migrated_v2_manual_source_is_read_without_false_link(self):
        memory_id = self.add()
        memory = self.client.app.state.memory
        source_id = memory.catalog.get("alice", memory_id)["source_refs"][0]
        source = memory.architecture.repo.get("source_records", "alice", source_id)
        source["thread_id"] = source["task_id"] = "manual"
        source["metadata"].pop("thread_id")
        memory.architecture.repo.put("source_records", "alice", source_id, source)
        item, = self.evidence(memory_id)
        self.assertIsNone(item["thread_id"])
        self.assertIsNone(item["message_id"])

    def test_native_chat_uses_actual_persisted_message_identity(self):
        response = self.client.post("/api/chat", json={"user_id": "alice", "thread_id": "real-chat",
            "source_event_id": "real-message", "message": "我喜欢喝乌龙茶。"})
        self.assertEqual(response.status_code, 200, response.text)
        operation, = response.json()["memory_results"]
        self.assertEqual(operation["status"], "succeeded")
        item, = self.evidence(operation["result_refs"][0])
        self.assertEqual((item["thread_id"], item["message_id"]), ("real-chat", "real-message"))
        session = self.client.get("/api/sessions/real-chat?user_id=alice").json()
        self.assertTrue(any(m["id"] == item["message_id"] and m["role"] == "user"
                            for m in session["messages"]))

    def test_observation_task_and_system_program_are_not_chat_sources(self):
        receipt = self.client.post("/api/architecture/observe", json={
            "observation": {"user_id": "alice", "thread_id": "task-container", "task_id": "task",
                "source_event_id": "event-not-message", "content": "我喜欢喝乌龙茶。"},
            "analysis": {"semantic_candidates": [{"subject": "alice", "predicate": "drink",
                "value": "乌龙茶", "evidence_text": "我喜欢喝乌龙茶。"}]}}).json()
        item, = self.evidence(receipt["operations"][0]["result_refs"][0])
        self.assertIsNone(item["thread_id"])
        self.assertIsNone(item["message_id"])
        programs = self.client.post("/api/architecture/procedures/install-builtins",
                                    json={"user_id": "alice"}).json()["items"]
        for program in programs:
            for item in self.evidence(program["id"]):
                self.assertIsNone(item["thread_id"])
                self.assertIsNone(item["message_id"])


if __name__ == "__main__":
    unittest.main()
