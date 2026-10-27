from __future__ import annotations

import unittest
from datetime import timedelta

from cognitive_memory import Memory
from cognitive_memory.models import utc_now


class MemoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = Memory(":memory:")
        self.user = "test-user"

    def tearDown(self) -> None:
        self.service.close()

    def add(self, **overrides):
        payload = {
            "user_id": self.user,
            "content": "用户长期编程偏好是 Python。",
            "memory_key": "coding_language",
            "memory_value": "Python",
            "memory_type": "semantic",
            "source": "user",
            "tags": ["profile", "preference"],
            "importance": 0.86,
            "confidence": 0.95,
        }
        payload.update(overrides)
        return self.service.add_memory(payload)

    def test_first_high_value_memory_becomes_current(self):
        result = self.add()
        self.assertEqual(result["decision"], "WRITE_CURRENT")
        self.assertEqual(result["memory"]["state_role"], "current")
        self.assertEqual(result["memory"]["memory_type"], "semantic")

    def test_exact_duplicate_reinforces_instead_of_duplicating(self):
        first = self.add()
        second = self.add()
        self.assertEqual(second["decision"], "REINFORCED")
        self.assertEqual(first["memory"]["id"], second["memory"]["id"])
        self.assertEqual(second["memory"]["evidence_count"], 2)
        self.assertEqual(len(self.service.list_memories(self.user)), 1)

    def test_low_value_noise_stays_in_working_memory(self):
        result = self.add(
            content="可能是随口一提的无关碎片",
            memory_key="",
            memory_value="",
            tags=["noise"],
            importance=0.1,
            confidence=0.2,
        )
        self.assertEqual(result["decision"], "KEEP_SESSION_ONLY")
        self.assertEqual(result["memory"]["state_role"], "working")
        self.assertEqual(result["memory"]["memory_type"], "semantic")

    def test_three_content_types_are_independent_of_working_state(self):
        for memory_type in ("episodic", "semantic", "procedural"):
            with self.subTest(memory_type=memory_type):
                result = self.add(
                    content=f"低分内容 {memory_type}", memory_type=memory_type,
                    memory_key="", memory_value="", tags=["noise"],
                    importance=0.1, confidence=0.2,
                )
                self.assertEqual(result["memory"]["memory_type"], memory_type)
                self.assertEqual(result["memory"]["state_role"], "working")

    def test_invalid_content_type_is_rejected_without_side_effects(self):
        self.add()
        before = self.service.list_memories(self.user)
        audit = self.service.list_audit(self.user)
        for value in ("working", "unknown"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "memory_type"):
                self.add(memory_type=value)
        self.assertEqual(self.service.list_memories(self.user), before)
        self.assertEqual(self.service.list_audit(self.user), audit)

    def test_single_conflict_is_candidate_and_repeated_conflict_consolidates(self):
        original = self.add()
        first_conflict = self.add(
            content="用户最近更倾向使用 Rust 作为主要编程语言。",
            memory_value="Rust",
            source="user_correction",
            tags=["preference", "conflict"],
            importance=0.9,
            confidence=0.92,
        )
        self.assertEqual(first_conflict["decision"], "CANDIDATE")

        second_conflict = self.add(
            content="用户再次确认未来项目主要使用 Rust。",
            memory_value="Rust",
            source="user_feedback",
            tags=["preference", "conflict"],
            importance=0.9,
            confidence=0.94,
        )
        self.assertEqual(second_conflict["decision"], "CONSOLIDATED")
        memories = self.service.list_memories(self.user)
        rust_current = [
            m
            for m in memories
            if m["state_role"] == "current" and m["memory_value"] == "Rust"
        ]
        python_history = [
            m
            for m in memories
            if m["state_role"] == "history" and m["memory_value"] == "Python"
        ]
        self.assertEqual(len(rust_current), 1)
        self.assertEqual(len(python_history), 1)
        self.assertEqual(python_history[0]["id"], original["memory"]["id"])
        self.assertEqual(len(second_conflict["support_ids"]), 2)

    def test_alias_keys_share_one_preference_state_machine(self):
        tea = self.add(
            content="我喜欢喝茶。",
            memory_key="beverage_preference",
            memory_value="喜欢喝茶",
        )
        coffee_candidate = self.add(
            content="我现在更喜欢喝咖啡。",
            memory_key="preferred_beverage",
            memory_value="喜欢喝咖啡",
        )
        coffee_current = self.add(
            content="我目前最喜欢喝咖啡。",
            memory_key="favorite_drink",
            memory_value="咖啡",
        )

        self.assertEqual(tea["memory"]["memory_key"], "preferred_beverage")
        self.assertEqual(coffee_candidate["decision"], "CANDIDATE")
        self.assertEqual(coffee_current["decision"], "CONSOLIDATED")
        records = self.service.list_memories(self.user, include_archived=True)
        current = [row for row in records if row["state_role"] == "current"]
        history = [row for row in records if row["state_role"] == "history"]
        self.assertEqual(
            [(row["memory_key"], row["memory_value"]) for row in current],
            [("preferred_beverage", "咖啡")],
        )
        self.assertEqual(
            [(row["memory_key"], row["memory_value"]) for row in history],
            [("preferred_beverage", "茶")],
        )

    def test_search_prefers_current_over_history(self):
        self.test_single_conflict_is_candidate_and_repeated_conflict_consolidates()
        result = self.service.search(self.user, "我现在主要使用什么编程语言？")
        self.assertTrue(result["grounded"])
        self.assertEqual(result["results"][0]["state_role"], "current")
        self.assertIn("Rust", result["answer"])

    def test_history_intent_can_promote_history(self):
        self.test_single_conflict_is_candidate_and_repeated_conflict_consolidates()
        result = self.service.search(self.user, "我以前主要使用什么编程语言？")
        history_items = [
            item for item in result["results"] if item["state_role"] == "history"
        ]
        self.assertTrue(history_items)
        self.assertIn("Python", result["answer"])

    def test_sensitive_memory_requires_consent(self):
        result = self.add(
            content="身份证号是 000000000000000000",
            memory_key="identity_number",
            memory_value="000000000000000000",
            tags=["sensitive"],
        )
        self.assertEqual(result["decision"], "DROP")
        self.assertEqual(self.service.list_memories(self.user), [])

    def test_do_not_store_instruction_has_priority(self):
        result = self.add(
            content="不要记住：我今天临时住在某酒店", tags=["profile"], consent=True
        )
        self.assertEqual(result["decision"], "DROP")

    def test_retention_archives_old_unprotected_memory_but_keeps_protected_memory(self):
        unprotected = self.add(
            content="一次普通临时事件",
            memory_key="temporary_event",
            memory_value="done",
            tags=["event"],
            importance=0.55,
            confidence=0.7,
        )
        protected = self.add()
        future = utc_now() + timedelta(days=365)
        result = self.service.run_retention(self.user, future)
        self.assertIn(unprotected["memory"]["id"], result["archived_ids"])
        self.assertNotIn(protected["memory"]["id"], result["archived_ids"])

    def test_user_delete_physically_removes_content(self):
        record = self.add()["memory"]
        self.assertTrue(self.service.delete_memory(self.user, record["id"]))
        self.assertEqual(
            self.service.list_memories(self.user, include_archived=True), []
        )
        events = self.service.list_audit(self.user)
        self.assertEqual(events[0]["event_type"], "USER_DELETE")


if __name__ == "__main__":
    unittest.main(verbosity=2)
