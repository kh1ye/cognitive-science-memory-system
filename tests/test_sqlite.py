import unittest
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from cognitive_memory import Memory
from cognitive_memory.storage import SQLiteStorage


class SQLiteIntegrationTests(unittest.TestCase):
    def test_legacy_working_types_are_backed_up_reclassified_and_idempotent(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "memory.db"
            cases = [(["event"], "episodic", "working"),
                     (["workflow"], "procedural", "archived"),
                     (["preference"], "semantic", "working"),
                     (["temporary"], "semantic", "history")]
            with Memory(path) as memory:
                for index, (tags, _, role) in enumerate(cases):
                    record = memory.add_memory({"user_id": "alice", "content": f"legacy {index}",
                                                "tags": tags, "metadata": {"keep": index}})["memory"]
                    with memory.storage.transaction():
                        memory.storage._conn.execute(
                            "UPDATE memories SET memory_type='working', state_role=? WHERE id=?",
                            (role, record["id"]),
                        )
                before = memory.list_memories("alice", include_archived=True)
                audit = memory.list_audit("alice")
            with Memory(path) as memory:
                after = memory.list_memories("alice", include_archived=True)
                self.assertEqual(memory.list_audit("alice"), audit)
                self.assertNotIn("working", memory.stats("alice")["by_type"])
                for old, new in zip(before, after):
                    index = old["metadata"]["keep"]
                    self.assertEqual(new["memory_type"], cases[index][1])
                    self.assertEqual(new["metadata"], {"keep": index, "legacy_memory_type": "working"})
                    self.assertEqual({k:v for k,v in old.items() if k not in ("memory_type", "metadata")},
                                     {k:v for k,v in new.items() if k not in ("memory_type", "metadata")})
                search = memory.search("alice", "legacy")
                self.assertTrue(search["has_results"])
                self.assertFalse(search["grounded"])  # Only working/history records exist.
                after = memory.list_memories("alice", include_archived=True)
            backups = list(path.parent.glob("memory.db.before-three-types-*.bak"))
            self.assertEqual(len(backups), 1)
            with closing(sqlite3.connect(backups[0])) as connection:
                self.assertEqual(connection.execute("SELECT count(*) FROM memories WHERE memory_type='working'").fetchone()[0], 4)
            with Memory(path) as memory:
                self.assertEqual(memory.list_memories("alice", include_archived=True), after)
            self.assertEqual(list(path.parent.glob("memory.db.before-three-types-*.bak")), backups)

    def test_records_and_audit_survive_reopening(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "memory.db"
            with Memory(path) as memory:
                record = memory.add_memory(
                    {
                        "user_id": "alice",
                        "content": "用户喜欢 Python",
                        "tags": ["preference"],
                        "metadata": {"language": "中文"},
                    }
                )["memory"]
            with Memory(path) as memory:
                self.assertEqual(memory.list_memories("alice"), [record])
                self.assertEqual(
                    memory.list_audit("alice")[0]["event_type"], "WRITE_CURRENT"
                )
                self.assertTrue(memory.search("alice", "Python")["grounded"])

    def test_failed_consolidation_rolls_back_states_and_audit(self):
        storage = SQLiteStorage()
        with Memory(storage=storage) as memory:
            base = {
                "user_id": "alice",
                "memory_key": "language",
                "tags": ["preference"],
                "importance": 0.9,
                "confidence": 0.95,
            }
            memory.add_memory(
                {**base, "content": "用户主要使用 Python", "memory_value": "Python"}
            )
            memory.add_memory(
                {**base, "content": "用户改用 Rust", "memory_value": "Rust"}
            )
            before = memory.list_memories("alice", include_archived=True)
            audit_before = memory.list_audit("alice")
            evidence_before = {row["id"]: memory.evidence("alice", row["id"]) for row in before}
            original_audit = storage.audit

            def failing_audit(user_id, event_type, *args, **kwargs):
                original_audit(user_id, event_type, *args, **kwargs)
                if event_type == "CONSOLIDATE":
                    raise RuntimeError("simulated audit failure")

            with patch.object(storage, "audit", side_effect=failing_audit):
                with self.assertRaisesRegex(RuntimeError, "simulated audit failure"):
                    memory.add_memory(
                        {
                            **base,
                            "content": "用户再次确认使用 Rust",
                            "memory_value": "Rust",
                        }
                    )
            self.assertEqual(
                memory.list_memories("alice", include_archived=True), before
            )
            self.assertEqual(memory.list_audit("alice"), audit_before)
            self.assertEqual({row["id"]: memory.evidence("alice", row["id"]) for row in before}, evidence_before)
            self.assertEqual(storage._conn.execute("SELECT count(*) FROM memory_evidence").fetchone()[0],
                             sum(item["total_count"] for item in evidence_before.values()))
            result = memory.add_memory(
                {**base, "content": "用户再次确认使用 Rust", "memory_value": "Rust"}
            )
            self.assertEqual(result["decision"], "CONSOLIDATED")

    def test_users_cannot_search_or_delete_each_others_records(self):
        with Memory() as memory:
            record = memory.add_memory({"user_id": "alice", "content": "喜欢 Python"})[
                "memory"
            ]
            self.assertFalse(memory.search("bob", "Python")["grounded"])
            self.assertFalse(memory.delete_memory("bob", record["id"]))
            memory.reset_user("bob")
            self.assertEqual(len(memory.list_memories("alice")), 1)
