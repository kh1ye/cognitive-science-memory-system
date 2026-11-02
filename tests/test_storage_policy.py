"""Storage-only equivalence against the original algorithms on the original SQL tables."""

from datetime import timedelta
from pathlib import Path
import sqlite3
from contextlib import closing
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from cognitive_memory import Memory, MemoryConfig
from cognitive_memory.encoding import Encoder
from cognitive_memory.consolidation import Consolidator
from cognitive_memory.retention import RetentionManager
from cognitive_memory.retrieval.retriever import Retriever
from cognitive_memory.storage.sqlite import SQLiteStorage
from cognitive_memory.models import utc_now
from cognitive_memory.architecture_models import (
    Observation,
    ObservationAnalysis,
    SemanticAssertion,
)


def original_table_engine(path=":memory:"):
    # Deliberately bypass typed storage setup; policy classes and methods are identical.
    engine = Memory.__new__(Memory)
    engine.config = MemoryConfig()
    engine.storage = SQLiteStorage(path)
    engine.architecture = None
    engine.catalog = None
    engine.encoder = Encoder(engine.storage)
    engine.consolidator = Consolidator(engine.storage, engine.config)
    engine.retriever = Retriever(engine.storage, engine.config)
    engine.retention = RetentionManager(engine.storage, engine.config)
    return engine


class StoragePolicyTests(unittest.TestCase):
    def test_same_inputs_produce_identical_scores_decisions_rankings_and_decay(self):
        with original_table_engine() as old, Memory() as new:
            events = [
                {
                    "content": "我喜欢用Python",
                    "memory_key": "coding_language",
                    "memory_value": "Python",
                    "tags": ["preference"],
                },
                {
                    "content": "我改为用Rust",
                    "memory_key": "coding_language",
                    "memory_value": "Rust",
                    "tags": ["preference"],
                },
                {
                    "content": "再次确认使用Rust",
                    "memory_key": "coding_language",
                    "memory_value": "Rust",
                    "tags": ["preference"],
                },
                {
                    "content": "我喜欢用Python",
                    "memory_key": "coding_language",
                    "memory_value": "Python",
                    "tags": ["preference"],
                },
                {
                    "content": "普通临时事件",
                    "tags": ["event"],
                    "importance": 0.5,
                    "confidence": 0.8,
                },
                {
                    "content": "低价值碎片",
                    "tags": ["noise"],
                    "importance": 0.1,
                    "confidence": 0.2,
                },
                {"content": "先测试再启动服务", "memory_type": "procedural"},
                {"content": "不要记住这条内容"},
                {"content": "账户资料", "tags": ["sensitive"]},
                {
                    "content": "同一个来源的记忆",
                    "metadata": {"thread_id": "t", "message_id": "m"},
                },
                {
                    "content": "同一个来源的记忆",
                    "metadata": {"thread_id": "t", "message_id": "m"},
                },
            ]
            fields = (
                "content",
                "memory_type",
                "state_role",
                "importance",
                "confidence",
                "saliency",
                "goal_relevance",
                "preference_strength",
                "attention_bias",
                "write_score",
                "prediction_error",
                "evidence_count",
                "is_protected",
            )
            for event in events:
                payload = {"user_id": "alice", **event}
                left, right = old.add_memory(payload), new.add_memory(payload)
                self.assertEqual(
                    (left["decision"], left["reason"]),
                    (right["decision"], right["reason"]),
                )
                if left["memory"]:
                    self.assertEqual(
                        {k: left["memory"][k] for k in fields},
                        {k: right["memory"][k] for k in fields},
                    )
                self.assertEqual(left.get("gate"), right.get("gate"))
            for query in (
                "现在用什么语言",
                "以前Python",
                "Rust",
                "临时事件",
                "启动服务",
                "不存在的词",
            ):
                left, right = old.search(
                    "alice", query, active_goal="编程", recent_focus="Rust"
                ), new.search("alice", query, active_goal="编程", recent_focus="Rust")
                self.assertEqual(left["answer"], right["answer"])
                self.assertEqual(left["grounded"], right["grounded"])
                self.assertEqual(
                    [
                        (r["content"], r["state_role"], r["retrieval"])
                        for r in left["results"]
                    ],
                    [
                        (r["content"], r["state_role"], r["retrieval"])
                        for r in right["results"]
                    ],
                )
            future = utc_now() + timedelta(days=365)
            old.run_retention("alice", future)
            new.run_retention("alice", future)
            self.assertEqual(
                sorted(
                    (r["content"], r["state_role"])
                    for r in old.list_memories("alice", True)
                ),
                sorted(
                    (r["content"], r["state_role"])
                    for r in new.list_memories("alice", True)
                ),
            )

    def test_migration_preserves_exact_records_evidence_and_audit_and_reopens_once(
        self,
    ):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "memory.db"
            with original_table_engine(path) as fixture:
                for index in range(3):
                    fixture.add_memory(
                        {
                            "user_id": "alice",
                            "content": f"原始证据{index}",
                            "memory_key": "topic",
                            "memory_value": "same",
                            "metadata": {"thread_id": "t", "message_id": str(index)},
                        }
                    )
                before = fixture.list_memories("alice", True)
                evidence = {r["id"]: fixture.evidence("alice", r["id"]) for r in before}
                audit = fixture.list_audit("alice")
            for _ in range(2):
                with Memory(path) as memory:
                    self.assertEqual(memory.list_memories("alice", True), before)
                    self.assertEqual(
                        {r["id"]: memory.evidence("alice", r["id"]) for r in before},
                        evidence,
                    )
                    self.assertEqual(memory.list_audit("alice"), audit)
                    for name in ("memories", "memory_evidence"):
                        self.assertEqual(
                            memory.storage._conn.execute(
                                "SELECT type FROM sqlite_master WHERE name=?", (name,)
                            ).fetchone()[0],
                            "view",
                        )
                    count = sum(
                        len(memory.architecture.repo.rows(table, "alice"))
                        for table in (
                            "working_states",
                            "semantic_assertions",
                            "semantic_documents",
                            "episode_events",
                            "procedure_versions",
                        )
                    )
                    self.assertEqual(count, len(before))
            backups = list(path.parent.glob("*.before-typed-storage-*.bak"))
            self.assertEqual(len(backups), 1)
            with closing(sqlite3.connect(backups[0])) as backup:
                self.assertEqual(
                    backup.execute("SELECT COUNT(*) FROM memories").fetchone()[0],
                    len(before),
                )

    def test_failed_migration_rolls_back_and_keeps_recovery_backup(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "memory.db"
            with original_table_engine(path) as fixture:
                saved = fixture.add_memory(
                    {"user_id": "alice", "content": "必须保留的原始记录"}
                )["memory"]
            with patch(
                "cognitive_memory.storage.typed_records._views",
                side_effect=RuntimeError("simulated migration failure"),
            ):
                with self.assertRaisesRegex(RuntimeError, "migration failure"):
                    Memory(path)
            with closing(sqlite3.connect(path)) as original:
                self.assertEqual(
                    original.execute("SELECT id FROM memories").fetchone()[0],
                    saved["id"],
                )
                self.assertEqual(
                    original.execute(
                        "SELECT type FROM sqlite_master WHERE name='memories'"
                    ).fetchone()[0],
                    "table",
                )
            self.assertTrue(list(path.parent.glob("*.before-typed-storage-*.bak")))
            with Memory(path) as restored:
                self.assertEqual(restored.list_memories("alice")[0], saved)

    def test_native_learning_uses_existing_gate_and_keeps_policy_metadata(self):
        with Memory() as memory:
            for event, value in [
                ("old", "茶"),
                ("candidate", "咖啡"),
                ("confirm", "咖啡"),
            ]:
                content = "我偏好" + value + event
                result = memory.architecture.observe(
                    Observation(
                        user_id="alice",
                        thread_id="t",
                        task_id="task",
                        source_event_id=event,
                        content=content,
                    ),
                    ObservationAnalysis(
                        semantic_candidates=[
                            SemanticAssertion(
                                subject="alice",
                                predicate="饮品",
                                value=value,
                                evidence_text=content,
                            )
                        ]
                    ),
                )
                self.assertEqual(
                    result["operations"][0]["result_status"],
                    "candidate" if event == "candidate" else "current",
                )
            rows = memory.list_memories("alice", True)
            self.assertEqual(sum(r["state_role"] == "current" for r in rows), 1)
            for row in rows:
                self.assertIn("write_score", row)
                self.assertIn("attention_bias", row)
            self.assertIn("咖啡", memory.search("alice", "咖啡")["answer"])

    def test_native_scores_and_tags_reach_the_existing_admission_gate(self):
        with Memory() as memory:
            result = memory.architecture.observe(
                Observation(
                    user_id="alice",
                    thread_id="t",
                    task_id="task",
                    source_event_id="weak",
                    content="低分事实",
                ),
                ObservationAnalysis(
                    semantic_candidates=[
                        SemanticAssertion(
                            subject="alice",
                            predicate="info",
                            value="x",
                            evidence_text="低分事实",
                            importance=0.1,
                            confidence=0.2,
                            tags=["noise"],
                        )
                    ]
                ),
            )
            self.assertEqual(result["operations"][0]["result_status"], "working")
            record = memory.storage.get_memory(
                result["operations"][0]["result_refs"][0]
            )
            self.assertLess(record["write_score"], memory.config.write_threshold)
            self.assertEqual(
                memory.architecture.repo.rows("semantic_assertions", "alice"), []
            )
            self.assertIn("noise", record["tags"])

    def test_low_score_proposal_cannot_execute_or_reuse_a_version(self):
        from cognitive_memory.architecture_models import ProcedureProposal

        with Memory() as memory:
            a = memory.architecture
            with memory.storage.transaction():
                source = a.register_source(
                    Observation(
                        user_id="alice",
                        thread_id="t",
                        task_id="task",
                        source_event_id="proposal",
                        content="文本整理能力",
                    )
                )
            weak = a.propose_procedure(
                "alice",
                ProcedureProposal(
                    description="文本整理能力",
                    kind="reasoning",
                    implementation_ref="text.normalize",
                    source_refs=[source["id"]],
                    importance=0.1,
                    confidence=0.2,
                    tags=["noise"],
                ),
                key="normalize",
            )
            self.assertEqual(weak["_policy"]["state_role"], "working")
            with self.assertRaises(ValueError):
                a.validate_procedure("alice", weak["id"])
            strong = a.propose_procedure(
                "alice",
                ProcedureProposal(
                    description="可靠的文本整理能力",
                    kind="reasoning",
                    implementation_ref="text.normalize",
                    source_refs=[source["id"]],
                ),
                key="normalize",
            )
            self.assertEqual(strong["version"], 2)
            a.validate_procedure("alice", strong["id"])
            a.activate_procedure("alice", strong["id"])
            self.assertEqual(
                a.execute_procedure(
                    "alice", strong["id"], {"text": "a   b"}, run_key="one"
                )["result"],
                {"text": "a b"},
            )

    def test_existing_native_documents_are_visible_to_original_search_after_reopen(
        self,
    ):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "native.db"
            with Memory(path) as memory:
                with memory.storage.transaction():
                    source = memory.architecture.register_source(
                        Observation(
                            user_id="alice",
                            thread_id="t",
                            task_id="task",
                            source_event_id="source",
                            content="材料包含Python方案",
                        )
                    )
                from cognitive_memory.architecture_models import SemanticDocument

                doc = memory.architecture.ingest_document(
                    "alice",
                    SemanticDocument(
                        document_id="plan",
                        document_version="1",
                        content="Python方案",
                        source_ref=source["id"],
                    ),
                )
                self.assertEqual(
                    memory.search("alice", "Python")["results"][0]["id"], doc["id"]
                )
            with Memory(path) as memory:
                self.assertEqual(
                    memory.search("alice", "Python")["results"][0]["id"], doc["id"]
                )
                self.assertEqual(memory.evidence("alice", doc["id"])["total_count"], 1)
