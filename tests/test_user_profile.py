"""Profiles must follow the engine's lifecycle, never invent a second one."""
import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from api.app import create_app
from cognitive_memory import Memory
from cognitive_memory.profile import UserProfile, save_preferences
from cognitive_memory.architecture_models import Observation
from conversation_agent import ConversationAgent


class ReplyModel:
    def __init__(self):
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        return AIMessage(content="已按偏好回答")


class UserProfileTests(unittest.TestCase):
    def setUp(self):
        self.memory = Memory(":memory:")
        self.addCleanup(self.memory.close)

    def add(self, value, *, key="preferred_language", user="alice", event=None, **kwargs):
        return self.memory.add_memory({"user_id": user, "content": f"我偏好{value}",
            "memory_type": "semantic", "memory_key": key, "memory_value": value,
            "tags": ["preference"], "metadata": {"event_id": event or value}, **kwargs})

    def values(self, user="alice"):
        return [item["value"] for item in UserProfile.read(self.memory, user).items]

    def test_open_vocabulary_personal_memories_are_not_lost_to_fixed_categories(self):
        for predicate, value in (("喜欢的运动/爱好", "跑步"), ("爱好/偏好", "打篮球"), ("喜欢", "喝水")):
            self.memory.add_memory({"user_id": "alice", "memory_type": "semantic", "memory_key": predicate,
                "memory_value": value, "content": f"我喜欢{value}"})
        profile = UserProfile.read(self.memory, "alice")
        self.assertEqual(len(profile.items), 3)
        self.assertEqual({item["description"] for item in profile.items}, {"你喜欢跑步", "你喜欢打篮球", "你喜欢喝水"})
        self.assertTrue(all(item["evidence_text"].startswith("我喜欢") for item in profile.items))
        self.add("特殊经历", key="unlisted_personal_topic", tags=[])
        self.assertIn("特殊经历", self.values())

    def test_empty_cold_start_and_settings_cross_session(self):
        self.assertEqual(self.values(), [])
        profile = save_preferences(self.memory, "alice", {"name": "小林", "language": "中文", "style": "简洁直接", "interests": "阅读", "tools": "Python"})
        self.assertEqual(len(profile.items), 5)
        self.assertEqual(UserProfile.read(self.memory, "alice").to_dict()["preferences"]["name"], "小林")
        self.assertEqual(self.values("bob"), [])
        # Reads construct a view and do not persist another object.
        before = self.memory.storage._conn.total_changes
        UserProfile.read(self.memory, "alice")
        self.assertEqual(before, self.memory.storage._conn.total_changes)
        model = ReplyModel()
        agent = ConversationAgent(self.memory, ":memory:", model=model)
        self.addCleanup(agent.close)
        for thread in ("first", "second"):
            agent.chat("alice", thread, "你好", auto_remember=False)
            self.assertIn("小林", model.calls[-1][0].content)
            self.assertIn("中文", model.calls[-1][0].content)

    def test_existing_memory_bootstraps_and_candidate_consolidation_updates_view(self):
        old = self.add("中文")["memory"]
        self.assertEqual(self.values(), ["中文"])
        for i in range(self.memory.config.minimum_evidence_count - 1):
            result = self.add("English", event=f"english-{i}")
            self.assertEqual(result["decision"], "CANDIDATE")
            self.assertEqual(self.values(), ["中文"])
        result = self.add("English", event="english-final")
        self.assertEqual(result["decision"], "CONSOLIDATED")
        self.assertEqual(self.memory.storage.get_memory(old["id"])["state_role"], "history")
        self.assertEqual(self.values(), ["English"])

    def test_conversation_aliases_share_settings_evidence_gate(self):
        save_preferences(self.memory, "alice", {"language": "中文"})
        result = self.add("English", key="response_language", event="alias-1")
        self.assertEqual(result["decision"], "CANDIDATE")
        self.assertEqual(self.values(), ["中文"])
        for i in range(1, self.memory.config.minimum_evidence_count):
            self.add("English", key="preferred_response_language", event=f"alias-{i + 1}")
        self.assertEqual(self.values(), ["English"])

    def test_explicit_setting_replaces_current_and_archives_pending(self):
        old = self.add("中文")["memory"]
        pending = self.add("English")["memory"]
        save_preferences(self.memory, "alice", {"language": "中英双语"})
        self.assertEqual(self.values(), ["中英双语"])
        self.assertEqual(self.memory.storage.get_memory(old["id"])["state_role"], "history")
        self.assertEqual(self.memory.storage.get_memory(pending["id"])["state_role"], "archived")

    def test_history_working_and_inferred_never_enter_profile(self):
        for value, role in (("过期", "history"), ("候选", "candidate"), ("临时", "working"), ("已归档", "archived")):
            item = self.add(value, key=f"profile_{role}")["memory"]
            with self.memory.storage.transaction():
                self.memory.storage._conn.execute("UPDATE memories SET state_role=? WHERE id=?", (role, item["id"]))
        self.assertEqual(self.values(), [])
        native = self.memory.architecture
        with self.memory.storage.transaction():
            source = native.register_source(Observation(user_id="alice", thread_id="a", task_id="a", source_event_id="inferred", content="可能喜欢中文"))
        native.upsert_assertion("alice", {"subject": "alice", "predicate": "preferred_language", "value": "推测值", "evidence_text": "可能喜欢中文", "epistemic_status": "inferred", "source_refs": [source["id"]]})
        self.assertEqual(self.values(), [])

    def test_third_party_and_task_facts_are_not_personal_identity(self):
        a = self.memory.architecture
        with self.memory.storage.transaction():
            source = a.register_source(Observation(user_id="alice", thread_id="a", task_id="a", source_event_id="other", content="Bob使用English"))
        a.upsert_assertion("alice", {"subject": "Bob", "predicate": "preferred_language", "value": "English", "evidence_text": "Bob使用English", "source_refs": [source["id"]]})
        self.assertEqual(self.values(), [])

    def test_privacy_rejection_rolls_back_entire_settings_edit(self):
        save_preferences(self.memory, "alice", {"name": "原称呼"})
        with self.assertRaises(ValueError):
            save_preferences(self.memory, "alice", {"name": "新称呼", "notes": "不要保存这个偏好"})
        self.assertEqual(self.values(), ["原称呼"])
        dropped = self.add("私人内容", tags=["preference", "sensitive"])
        self.assertEqual(dropped["decision"], "DROP")
        self.assertEqual(self.values(), ["原称呼"])

    def test_source_deletion_removes_view_and_no_cache(self):
        item = self.add("中文")["memory"]
        source = UserProfile.read(self.memory, "alice").items[0]["source_refs"][0]
        self.memory.architecture.delete_source("alice", source)
        self.assertEqual(self.values(), [])

    def test_context_budget_and_user_isolation_and_no_persist(self):
        save_preferences(self.memory, "alice", {"name": "小林", "language": "中文", "notes": "x" * 2000})
        context = UserProfile.read(self.memory, "alice").context(300)
        self.assertLessEqual(len(json.dumps(context, ensure_ascii=False)), 300)
        model = ReplyModel()
        agent = ConversationAgent(self.memory, ":memory:", model=model)
        self.addCleanup(agent.close)
        agent.chat("bob", "other", "你好", auto_remember=False)
        self.assertNotIn("小林", model.calls[-1][0].content)
        before = len(agent.list_sessions("alice"))
        agent.chat("alice", "private", "你好", retention_policy="no_persist")
        self.assertNotIn("小林", model.calls[-1][0].content)
        self.assertEqual(len(agent.list_sessions("alice")), before)
        self.assertIn("小林", self.values())

    def test_api_edit_delete_and_ownership(self):
        with TestClient(create_app(service=self.memory)) as client:
            response = client.put("/api/profile", json={"user_id": "Alice", "preferences": {"name": "小林", "language": "中文"}})
            self.assertEqual(response.status_code, 200, response.text)
            item = next(item for item in response.json()["items"] if item["value"] == "小林")
            self.assertEqual(client.patch(f"/api/profile/{item['id']}", json={"user_id": "bob", "value": "其他"}).status_code, 404)
            self.assertEqual(client.delete(f"/api/profile/{item['id']}?user_id=bob").status_code, 404)
            edited = client.patch(f"/api/profile/{item['id']}", json={"user_id": "alice", "value": "小王"})
            self.assertEqual(edited.status_code, 200, edited.text)
            new = next(item for item in edited.json()["items"] if item["value"] == "小王")
            self.assertEqual(client.delete(f"/api/profile/{new['id']}?user_id=alice").status_code, 200)
            self.assertNotIn("小王", self.values())
            self.assertEqual(client.get("/api/profile?user_id=bob").json()["items"], [])
            self.assertEqual(client.get("/api/profile?user_id=alice").headers["cache-control"], "no-store")

    def test_reply_reloads_profile_after_consolidation_and_deletion(self):
        from conversation_agent.prompts import DIALOGUE_PROMPT

        self.add("中文")
        model = ReplyModel()
        agent = ConversationAgent(self.memory, ":memory:", model=model)
        self.addCleanup(agent.close)

        def reply_profile():
            agent.chat("alice", "check", "请回答", auto_remember=False)
            payload = json.loads(model.calls[-1][0].content[len(DIALOGUE_PROMPT):])
            return [item["value"] for item in payload["user_profile"]]

        self.assertEqual(reply_profile(), ["中文"])
        self.add("English", event="new-0")
        self.assertEqual(reply_profile(), ["中文"])
        for i in range(1, self.memory.config.minimum_evidence_count):
            self.add("English", event=f"new-{i}")
        self.assertEqual(reply_profile(), ["English"])
        item = UserProfile.read(self.memory, "alice").items[0]
        self.memory.delete_memory("alice", item["id"])
        self.assertEqual(reply_profile(), [])

    def test_unchanged_settings_do_not_create_new_history(self):
        save_preferences(self.memory, "alice", {"language": "中文"})
        count = len(self.memory.list_memories("alice", include_archived=True))
        save_preferences(self.memory, "alice", {"language": "中文"})
        self.assertEqual(len(self.memory.list_memories("alice", include_archived=True)), count)

    def test_sensitive_edit_requires_consent_and_preserves_privacy_label(self):
        original = self.add("私人偏好", tags=["preference", "sensitive"], consent=True)["memory"]
        with self.assertRaises(ValueError):
            self.memory.edit_semantic_memory("alice", "preferred_language", "新值", "我的新偏好", tags=["preference"], replace_ids=[original["id"]])
        self.assertEqual(self.memory.storage.get_memory(original["id"])["state_role"], "current")
        self.memory.edit_semantic_memory("alice", "preferred_language", "新值", "我的新偏好", tags=["preference"], replace_ids=[original["id"]], consent=True)
        self.assertEqual(self.values(), ["新值"])
        self.assertIn("sensitive", self.memory.list_memories("alice")[0]["tags"])

    def test_clearing_setting_does_not_restore_history(self):
        save_preferences(self.memory, "alice", {"language": "中文"})
        save_preferences(self.memory, "alice", {"language": "English"})
        save_preferences(self.memory, "alice", {"language": ""})
        self.assertEqual(self.values(), [])
        save_preferences(self.memory, "bob", {"language": "中文"})
        self.assertEqual(self.values(), [])
        self.assertEqual(self.values("bob"), ["中文"])

    def test_explicit_edit_admission_failure_preserves_original(self):
        old = self.add("中文")["memory"]
        with patch.object(self.memory.encoder, "write_score", return_value=0):
            with self.assertRaises(ValueError):
                save_preferences(self.memory, "alice", {"language": "English"})
        self.assertEqual(self.values(), ["中文"])
        self.assertEqual(self.memory.storage.get_memory(old["id"])["state_role"], "current")
