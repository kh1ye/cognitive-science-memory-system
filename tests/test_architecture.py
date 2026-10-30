"""Offline behavioral tests for module boundaries; no external provider/API key."""

import sqlite3
from contextlib import closing
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from cognitive_memory import Memory
from cognitive_memory.architecture_models import (
    EpisodeEvent,
    Observation,
    ObservationAnalysis,
    ProcedureProposal,
    SemanticAssertion,
)


class ArchitectureTests(unittest.TestCase):
    def setUp(self):
        self.memory = Memory()
        self.addCleanup(self.memory.close)
        self.a = self.memory.architecture

    def observe(self, text="以后默认用中文", event="one", task="task", **kw):
        return Observation(
            user_id="alice",
            thread_id="chat",
            task_id=task,
            source_event_id=event,
            content=text,
            **kw,
        )

    def assertion(self, value="中文", evidence="以后默认用中文", **kw):
        return SemanticAssertion(
            subject="alice",
            predicate="language",
            value=value,
            evidence_text=evidence,
            **kw,
        )

    def save(self, obs=None, assertion=None):
        return self.a.observe(
            obs or self.observe(),
            ObservationAnalysis(semantic_candidates=[assertion or self.assertion()]),
        )

    def test_temporary_request_and_new_task_isolation(self):
        self.save()
        self.a.observe(
            self.observe("这次用英文", "temp"),
            ObservationAnalysis(working_state_patch={"constraints": ["这次用英文"]}),
        )
        self.assertEqual(self.a.retrieve_knowledge("alice")[0]["value"], "中文")
        self.assertEqual(
            self.a.working_state("alice", "chat", "task").constraints, ["这次用英文"]
        )
        self.assertEqual(self.a.working_state("alice", "chat", "new").constraints, [])

    def test_explicit_preference_correction_preserves_history(self):
        self.save()
        self.save(
            self.observe("以后默认用英文", "new"),
            self.assertion("英文", "以后默认用英文", correction=True),
        )
        self.assertEqual(self.a.retrieve_knowledge("alice")[0]["value"], "英文")
        rows = self.a.retrieve_knowledge("alice", history=True)
        self.assertEqual({r["status"] for r in rows}, {"current", "history"})
        self.assertEqual(len(rows[0]["evidence_ids"]), 1)

    def test_same_text_different_event_and_retry(self):
        for event, date in [
            ("a", "2025-01-01"),
            ("b", "2026-01-01"),
            ("a", "2025-01-01"),
        ]:
            self.a.observe(
                self.observe("测试完成", event, observed_at=date),
                ObservationAnalysis(
                    episode_candidates=[EpisodeEvent(observation="测试完成")]
                ),
            )
        rows = self.a.retrieve_episodes("alice")
        self.assertEqual(len(rows), 2)
        self.assertEqual({r["occurred_at"] for r in rows}, {"2025-01-01", "2026-01-01"})

    def test_same_source_extraction_summary_not_independent_evidence(self):
        result = self.save()
        self.save()
        source = result["source_id"]
        self.a.upsert_assertion("alice", self.assertion(source_refs=[source]))
        self.a.append_episode(
            "alice",
            "chat",
            "task",
            EpisodeEvent(
                event_kind="summary", observation="摘要", source_refs=[source]
            ),
            source_event_id="summary",
        )
        self.assertEqual(len(self.a.retrieve_knowledge("alice")[0]["evidence_ids"]), 1)

    def test_scope_valid_time_cardinality_and_conflict(self):
        self.save(self.observe(scope="project:a"), self.assertion(scope="project:a"))
        self.save(
            self.observe("英文", "b", scope="project:b"),
            self.assertion("英文", "英文", scope="project:b"),
        )
        self.assertEqual(len(self.a.retrieve_knowledge("alice", scope="project:a")), 1)
        self.save(
            self.observe("英文", "c"),
            self.assertion("英文", "英文", cardinality="multiple"),
        )
        self.save(
            self.observe("中文", "d"),
            self.assertion("中文", "中文", cardinality="multiple"),
        )
        self.assertEqual(len(self.a.retrieve_knowledge("alice")), 2)
        self.save(self.observe("日语", "e"), self.assertion("日语", "日语"))
        self.assertTrue(
            all(r["status"] == "disputed" for r in self.a.retrieve_knowledge("alice"))
        )
        self.save(
            self.observe("法语", "f", scope="future"),
            self.assertion("法语", "法语", scope="future", valid_from="2099-01-01"),
        )
        self.assertEqual(self.a.retrieve_knowledge("alice", scope="future"), [])

    def test_activation_keeps_original_and_user_boundary(self):
        result = self.save()
        refs = self.a.retrieve("alice", "chat", "other", "中文")
        self.assertEqual(refs[0]["module"], "semantic")
        self.assertEqual(len(self.a.retrieve_knowledge("alice")), 1)
        self.assertEqual(self.a.retrieve_knowledge("bob"), [])
        self.assertEqual(self.a.working_state("bob", "chat", "task").observations, [])
        self.assertFalse(self.a.delete_source("bob", result["source_id"]))
        with self.assertRaises(ValueError):
            self.a.upsert_assertion(
                "bob", self.assertion(source_refs=[result["source_id"]])
            )

    def test_text_proposal_cannot_execute_registered_program_runs_and_fails(self):
        source = self.save()["source_id"]
        draft = self.a.propose_procedure(
            "alice",
            ProcedureProposal(
                description="先搜索再回答", kind="reasoning", source_refs=[source]
            ),
        )
        with self.assertRaises(ValueError):
            self.a.activate_procedure("alice", draft["id"])
        with self.assertRaises(ValueError):
            self.a.validate_procedure("alice", draft["id"])
        self.a.install_builtins("alice")
        p = next(
            r
            for r in self.a.retrieve_procedures("alice")
            if r["implementation_ref"] == "text.normalize"
        )
        run = self.a.execute_procedure(
            "alice", p["id"], {"text": " a   b "}, run_key="run"
        )
        self.assertEqual(run["result"], {"text": "a b"})
        self.assertEqual(
            run,
            self.a.execute_procedure(
                "alice", p["id"], {"text": " a   b "}, run_key="run"
            ),
        )
        fail = self.a.execute_procedure("alice", p["id"], {}, run_key="bad")
        self.assertEqual(fail["status"], "failed")
        self.assertIn(
            "failed", [r["outcome"] for r in self.a.retrieve_episodes("alice")]
        )
        self.assertEqual(run["version"], 1)

    def test_mixed_input_and_partial_failure_retry(self):
        obs = self.observe("这次用英文；以后默认用中文；今天测试失败")
        analysis = ObservationAnalysis(
            working_state_patch={"constraints": ["这次用英文"]},
            semantic_candidates=[self.assertion()],
            episode_candidates=[
                EpisodeEvent(observation="今天测试失败", outcome="failed"),
                EpisodeEvent(observation="编造的事件"),
            ],
        )
        result = self.a.observe(obs, analysis)
        self.assertEqual(result["status"], "partial_failure")
        self.assertEqual(
            [r["status"] for r in result["operations"]],
            ["succeeded", "failed", "succeeded"],
        )
        self.a.observe(obs, analysis)
        self.assertEqual(len(self.a.retrieve_episodes("alice")), 1)
        self.assertEqual(len(self.a.retrieve_knowledge("alice")), 1)
        self.assertEqual(result["analysis"]["procedure_proposals"], [])

    def test_no_persist_and_no_long_term(self):
        self.a.observe(
            self.observe("secret", retention_policy="no_persist"),
            ObservationAnalysis(working_state_patch={"constraints": ["secret"]}),
        )
        for table in ["working_states", "source_records", "learning_operations"]:
            self.assertEqual(self.a.repo.rows(table, "alice"), [])
        result = self.a.observe(
            self.observe(retention_policy="no_long_term"),
            ObservationAnalysis(semantic_candidates=[self.assertion()]),
        )
        self.assertEqual(result["operations"], [])
        self.assertEqual(self.a.retrieve_knowledge("alice"), [])
        self.assertTrue(self.a.working_state("alice", "chat", "task").observations)
        with self.assertRaises(ValueError):
            self.a.upsert_assertion(
                "alice", self.assertion(source_refs=[result["source_id"]])
            )

    def test_delete_source_purges_derived_and_activated_content(self):
        result = self.save()
        self.a.retrieve("alice", "chat", "later", "中文")
        self.assertTrue(self.a.delete_source("alice", result["source_id"]))
        self.assertEqual(self.a.retrieve_knowledge("alice"), [])
        self.assertEqual(
            self.a.working_state("alice", "chat", "later").active_knowledge, []
        )
        self.assertEqual(self.a.repo.rows("learning_operations", "alice"), [])

    def test_unrecognized_input_is_not_a_fact(self):
        self.a.observe(self.observe("???"))
        self.assertEqual(self.a.retrieve_knowledge("alice"), [])

    def test_file_restore_and_repeat_migration(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.db"
            with Memory(path) as m:
                m.architecture.update_working_state(
                    "alice", "t", "task", {"constraints": ["once"]}
                )
            with Memory(path) as m:
                self.assertEqual(
                    m.architecture.working_state("alice", "t", "task").constraints,
                    ["once"],
                )
                m.architecture.repo.migrate()
                self.assertEqual(
                    m.storage._conn.execute(
                        "SELECT COUNT(*) FROM architecture_migrations"
                    ).fetchone()[0],
                    1,
                )
            self.assertTrue(Path(str(path) + ".pre-coala-v1.bak").exists())

    def test_old_data_migration_ids_quarantine_and_backup(self):
        from cognitive_memory.storage.sqlite import SQLiteStorage

        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy.db"
            # Construct the real pre-migration schema and data, not a new-engine fixture.
            storage = SQLiteStorage(path)
            for kind in ["working", "semantic", "episodic", "procedural"]:
                with storage.transaction():
                    storage.insert_memory(
                        dict(  # noqa: C408 -- explicit pre-migration fixture
                            id=kind,
                            user_id="alice",
                            content="旧正文",
                            normalized_content="旧正文",
                            memory_type=kind,
                            state_role="current",
                            source="user",
                            tags=[],
                            importance=0.7,
                            confidence=0.8,
                            saliency=0.5,
                            goal_relevance=0,
                            preference_strength=0,
                            attention_bias=0,
                            write_score=0.7,
                        )
                    )
            storage.close()
            for _ in range(2):
                with Memory(path) as engine:
                    a = engine.architecture
                    self.assertEqual(
                        engine.storage._conn.execute(
                            "SELECT COUNT(*) FROM legacy_memory_map"
                        ).fetchone()[0],
                        4,
                    )
                    self.assertEqual(len(engine.list_memories("alice")), 4)
                    self.assertEqual(a.retrieve_procedures("alice"), [])
                    self.assertEqual(a.retrieve_knowledge("alice"), [])
                    self.assertEqual(
                        a.working_state("alice", "new", "new").observations, []
                    )
                    self.assertEqual(
                        a.repo.get("procedure_versions", "alice", "procedural")[
                            "status"
                        ],
                        "legacy_unverified",
                    )
            with closing(sqlite3.connect(str(path) + ".pre-coala-v1.bak")) as backup:
                self.assertEqual(
                    backup.execute("SELECT COUNT(*) FROM memories").fetchone()[0], 4
                )

    def test_document_versions_inference_and_procedure_rollback(self):
        from cognitive_memory.architecture_models import SemanticDocument

        result = self.save()
        d = SemanticDocument(
            document_id="guide",
            document_version="1",
            content="以后默认用中文",
            source_ref=result["source_id"],
        )
        self.a.ingest_document("alice", d)
        with self.assertRaises(ValueError):
            self.a.ingest_document("alice", d.model_copy(update={"content": "changed"}))
        self.save(
            self.observe("可能英文", "inference"),
            self.assertion(
                "英文", "可能英文", epistemic_status="inferred", cardinality="multiple"
            ),
        )
        self.assertNotIn(
            "英文", [r.get("value") for r in self.a.retrieve_knowledge("alice")]
        )
        self.a.install_builtins("alice")
        old = next(
            r
            for r in self.a.retrieve_procedures("alice")
            if r["implementation_ref"] == "text.normalize"
        )
        new = self.a.propose_procedure(
            "alice",
            ProcedureProposal(
                description="normalize v2",
                kind="reasoning",
                implementation_ref="text.normalize",
                source_refs=[result["source_id"]],
            ),
            key="text.normalize",
        )
        self.a.validate_procedure("alice", new["id"])
        self.a.activate_procedure("alice", new["id"])
        self.assertEqual(
            self.a.repo.get("procedure_versions", "alice", old["id"])["status"],
            "disabled",
        )
        self.a.activate_procedure("alice", old["id"])
        self.assertEqual(
            self.a.execute_procedure(
                "alice", old["id"], {"text": " x "}, run_key="rollback"
            )["version"],
            1,
        )

    def test_same_document_identity_does_not_inflate_evidence(self):
        self.save(self.observe(source_ref="document:one"))
        self.save(self.observe(event="second-extract", source_ref="document:one"))
        self.assertEqual(len(self.a.retrieve_knowledge("alice")[0]["evidence_ids"]), 1)

    def test_extraction_patch_rejects_wrong_types_and_unowned_fields(self):
        for patch in [
            {"constraints": {"value": "English"}},
            {"task_language": "en"},
            {"active_knowledge": [{"memory_id": "invented"}]},
        ]:
            with self.assertRaises(ValueError):
                ObservationAnalysis(working_state_patch=patch)
        analysis = ObservationAnalysis(
            working_state_patch={"constraints": ["this task only"]}
        )
        self.a.observe(self.observe(), analysis)
        self.assertEqual(
            self.a.working_state("alice", "chat", "task").constraints,
            ["this task only"],
        )
