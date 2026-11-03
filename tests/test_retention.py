"""Forgetting, confirmation and archival contracts on real SQLite policy views."""

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from cognitive_memory import Memory, MemoryConfig
from cognitive_memory.retrieval.retriever import Retriever
from cognitive_memory.storage.sqlite import SQLiteStorage


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.memory = Memory()
        self.addCleanup(self.memory.close)

    def add(self, **values):
        return self.memory.add_memory({
            "user_id": "alice", "content": "普通事件记录", "importance": 0.6,
            **values,
        })["memory"]

    def test_exponential_curve_and_independent_stability(self):
        row = self.add()
        start = datetime.fromisoformat(row["created_at"])
        manager = self.memory.retention
        initial = manager.state(row, start)
        stability = initial["stability_days"]
        self.assertEqual(initial["retention_probability"], 1.0)
        for factor in (1, 2, 10):
            state = manager.state(row, start + timedelta(days=factor * stability))
            self.assertAlmostEqual(state["retention_probability"], math.exp(-factor))
            self.assertAlmostEqual(state["retention"], row["write_score"] * math.exp(-factor))
        important = self.add(content="重要事件记录", importance=0.9)
        self.assertGreater(manager.state(important, start)["stability_days"], stability)
        supported = {**row, "evidence_count": 3}
        self.assertGreater(manager.state(supported, start)["stability_days"], stability)
        self.assertEqual(manager.state(row, start)["stability_days"], stability)

    def test_timezones_future_times_and_legacy_naive_timestamps(self):
        row = self.add()
        row["created_at"] = "2020-01-01T00:00:00"
        manager = self.memory.retention
        past = manager.state(row, datetime(2019, 1, 1))
        self.assertEqual(past["retention_probability"], 1.0)
        utc = manager.state(row, datetime(2020, 1, 2, tzinfo=timezone.utc))
        local = manager.state(row, datetime(2020, 1, 2, 8, tzinfo=timezone(timedelta(hours=8))))
        self.assertEqual(utc, local)

    def test_invalid_optional_state_falls_back_without_rewriting_old_data(self):
        row = self.add(metadata={"keep": "original"})
        manager = self.memory.retention
        start = datetime.fromisoformat(row["created_at"])
        expected = manager.state(row, start)
        for value in (None, "old value", {}, {"stability_days": -1},
                      {"stability_days": float("nan")}, {"stability_days": float("inf")},
                      {"stability_days": "bad", "last_reinforced_at": 123},
                      {"last_reinforced_at": "bad timestamp"}):
            with self.subTest(value=value):
                legacy = {**row, "metadata": {"retention": value}}
                self.assertEqual(manager.state(legacy, start), expected)
        self.assertEqual(self.memory.storage.get_memory(row["id"]), row)

    def test_duplicate_and_same_value_confirmations_extend_forgetting_time(self):
        for content in ("普通事件记录", "再次确认这项事件"):
            with self.subTest(content=content):
                key = "event_" + content
                row = self.add(memory_key=key, memory_value="done", metadata={"keep": True})
                start = datetime.fromisoformat(row["created_at"])
                confirmation = start + timedelta(days=40)
                before = self.memory.retention.state(row, confirmation)
                with patch("cognitive_memory.retention.utc_now", return_value=confirmation):
                    result = self.memory.add_memory({
                        "user_id": "alice", "content": content,
                        "memory_key": key, "memory_value": "done", "importance": 0.6,
                    })
                self.assertEqual(result["decision"], "REINFORCED")
                reinforced = result["memory"]
                self.assertEqual(reinforced["id"], row["id"])
                self.assertEqual(reinforced["created_at"], row["created_at"])
                self.assertEqual(reinforced["evidence_count"], 2)
                self.assertTrue(reinforced["metadata"]["keep"])
                after = self.memory.retention.state(reinforced, confirmation)
                self.assertGreater(after["stability_days"], before["stability_days"])
                self.assertEqual(after["retention_probability"], 1.0)
                self.assertEqual(after["last_reinforced_at"], confirmation.isoformat())
                self.assertGreater(after["forget_at"], before["forget_at"])
                later = confirmation + timedelta(days=before["stability_days"])
                self.assertGreater(self.memory.retention.state(reinforced, later)["retention_probability"], math.exp(-1))

    def test_source_replay_does_not_reinforce_twice(self):
        payload = {"user_id": "alice", "content": "同一来源确认",
                   "metadata": {"thread_id": "t", "message_id": "1"}}
        self.memory.add_memory(payload)
        payload["metadata"]["message_id"] = "2"
        confirmed = self.memory.add_memory(payload)["memory"]
        later = datetime.fromisoformat(confirmed["created_at"]) + timedelta(days=20)
        with patch("cognitive_memory.retention.utc_now", return_value=later):
            replay = self.memory.add_memory(payload)
        self.assertEqual(replay["decision"], "UNCHANGED")
        self.assertEqual(replay["memory"], confirmed)

    def test_retrieval_does_not_reset_decay_or_count_as_confirmation(self):
        row = self.add()
        start = datetime.fromisoformat(row["created_at"])
        later = start + timedelta(days=30)
        before = self.memory.retention.state(row, later)
        with patch("cognitive_memory.retrieval.retriever.utc_now", return_value=later):
            self.memory.search("alice", "事件")
            self.memory.search("alice", "事件")
        touched = self.memory.storage.get_memory(row["id"])
        self.assertIsNotNone(touched["last_accessed_at"])
        self.assertEqual(touched["evidence_count"], row["evidence_count"])
        self.assertEqual(touched["metadata"], row["metadata"])
        self.assertEqual(self.memory.retention.state(touched, later), before)

    def test_conflicts_keep_incumbent_curve_and_consolidation_keeps_evidence_gate(self):
        row = self.add(memory_key="event_status", memory_value="old")
        candidate = self.memory.add_memory({"user_id": "alice", "content": "事件发生变化",
                                            "memory_key": "event_status", "memory_value": "new"})
        self.assertEqual(candidate["decision"], "CANDIDATE")
        self.assertEqual(self.memory.storage.get_memory(row["id"]), row)
        result = self.memory.add_memory({"user_id": "alice", "content": "确认事件变化",
                                        "memory_key": "event_status", "memory_value": "new"})
        self.assertEqual(result["decision"], "CONSOLIDATED")
        consolidated = result["memory"]
        self.assertEqual(consolidated["evidence_count"], 2)
        self.assertEqual(len(consolidated["support_ids"]), 2)
        self.assertEqual(self.memory.evidence("alice", consolidated["id"])["total_count"], 2)
        self.assertGreater(self.memory.retention.state(consolidated)["stability_days"],
                           self.memory.retention.state({**consolidated, "evidence_count": 1})["stability_days"])

    def test_failed_confirmation_rolls_back_curve_evidence_and_audit(self):
        row = self.add()
        audit = self.memory.list_audit("alice")
        evidence = self.memory.evidence("alice", row["id"])
        with patch.object(self.memory.storage, "audit", side_effect=RuntimeError("audit failure")):
            with self.assertRaisesRegex(RuntimeError, "audit failure"):
                self.add()
        self.assertEqual(self.memory.storage.get_memory(row["id"]), row)
        self.assertEqual(self.memory.list_audit("alice"), audit)
        self.assertEqual(self.memory.evidence("alice", row["id"]), evidence)

    def test_low_value_archive_preserves_important_records_and_all_evidence(self):
        weak = self.add()
        important = self.add(content="重要但无保护标签", importance=0.9)
        protected = self.add(content="用户稳定偏好", tags=["preference"])
        procedure = self.add(content="先测试再启动", memory_type="procedural")
        other = self.add(user_id="bob", content="其他用户的事件")
        records = self.memory.list_memories("alice", True)
        evidence = {r["id"]: self.memory.evidence("alice", r["id"]) for r in records}
        future = datetime.fromisoformat(weak["created_at"]) + timedelta(days=36500)
        result = self.memory.run_retention("alice", future)
        self.assertEqual(result["archived_ids"], [weak["id"]])
        for row in (important, protected, procedure):
            self.assertEqual(self.memory.storage.get_memory(row["id"])["state_role"], "current")
        archived = self.memory.storage.get_memory(weak["id"])
        self.assertEqual(archived["updated_at"], future.isoformat())
        self.assertEqual(self.memory.storage.get_memory(other["id"]), other)
        self.assertEqual(len(self.memory.list_memories("alice", True)), len(records))
        self.assertEqual({r["id"]: self.memory.evidence("alice", r["id"]) for r in records}, evidence)
        self.assertEqual(self.memory.run_retention("alice", future)["archived_ids"], [])

    def test_confirmation_prevents_immediate_archival_of_old_low_value_record(self):
        row = self.add()
        later = datetime.fromisoformat(row["created_at"]) + timedelta(days=365)
        with patch("cognitive_memory.retention.utc_now", return_value=later):
            self.add()
        self.assertEqual(self.memory.run_retention("alice", later)["archived_ids"], [])
        self.assertIn(row["id"], self.memory.run_retention("alice", later + timedelta(days=365))["archived_ids"])

    def test_retention_is_a_bounded_ranking_factor_and_keeps_relevance_gate(self):
        row = self.add(content="苹果事件")
        old = {**row, "id": "old", "created_at": "2000-01-01T00:00:00+00:00"}
        unrelated = {**old, "id": "unrelated", "content": "完全无关"}
        now = datetime.fromisoformat(row["created_at"])
        with patch("cognitive_memory.retrieval.retriever.utc_now", return_value=now):
            results = self.memory.retriever.rank_candidates([old, row, unrelated], "苹果")
        self.assertEqual([r["id"] for r in results], [row["id"], "old"])
        ratio = results[1]["retrieval"]["score"] / results[0]["retrieval"]["score"]
        self.assertAlmostEqual(ratio, 0.85, places=5)
        self.assertEqual(results[0]["retrieval"]["retention"], 1.0)
        self.assertGreater(results[1]["retrieval"]["score"], 0.0)

    def test_zero_decay_preserves_existing_disable_behavior(self):
        with Memory(config=MemoryConfig(retention_decay=0)) as memory:
            row = memory.add_memory({"user_id": "alice", "content": "普通记录"})["memory"]
            future = datetime.fromisoformat(row["created_at"]) + timedelta(days=36500)
            state = memory.retention.state(row, future)
            self.assertEqual(state["retention_probability"], 1.0)
            self.assertIsNone(state["forget_at"])
            self.assertEqual(memory.run_retention("alice", future)["archived_ids"], [])

    def test_retention_ranking_can_be_disabled_without_changing_original_scores(self):
        row = self.add(content="苹果事件")
        old = {**row, "id": "old", "created_at": "2000-01-01T00:00:00+00:00"}
        retriever = Retriever(self.memory.storage, MemoryConfig(retrieval_retention_weight=0))
        results = retriever.rank_candidates([old, row], "苹果")
        self.assertEqual(results[0]["retrieval"]["score"], results[1]["retrieval"]["score"])
        self.assertEqual(results[0]["retrieval"]["retention_factor"], 1.0)

    def test_native_knowledge_retrieval_uses_the_same_retention_ranking(self):
        row = self.add(content="苹果事件")
        with self.memory.storage.transaction():
            self.memory.storage.insert_memory({**row, "id": "old-native",
                "created_at": "2000-01-01T00:00:00+00:00"})
        results = self.memory.architecture.retrieve_knowledge("alice", "苹果")
        self.assertEqual([r["id"] for r in results], [row["id"], "old-native"])
        self.assertGreater(results[0]["_retrieval_score"], results[1]["_retrieval_score"])

    def test_reopen_and_legacy_table_migration_preserve_retention_metadata(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.db"
            row = self.add(metadata={"keep": "legacy"})
            # Write an actual old-format SQL table, then use the normal migration.
            storage = SQLiteStorage(path)
            try:
                with storage.transaction():
                    storage.insert_memory(row)
            finally:
                storage.close()
            with Memory(path) as migrated:
                original = migrated.storage.get_memory(row["id"])
                self.assertEqual(original, row)
                result = migrated.add_memory({"user_id": "alice", "content": row["content"]})
                confirmed = result["memory"]
                self.assertGreater(confirmed["metadata"]["retention"]["stability_days"],
                                   migrated.retention.state(row)["stability_days"])
                self.assertEqual(confirmed["metadata"]["keep"], "legacy")
                typed = migrated.architecture.repo.get("semantic_documents", "alice", row["id"])
                self.assertEqual(json.loads(typed["_policy"]["metadata_json"]), confirmed["metadata"])
            for _ in range(2):
                with Memory(path) as reopened:
                    self.assertEqual(reopened.storage.get_memory(row["id"]), confirmed)
                    self.assertEqual(reopened.storage._conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")


if __name__ == "__main__":
    unittest.main()
