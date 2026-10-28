"""Deletion must work for every catalog module without deleting shared evidence."""

import unittest
from fastapi.testclient import TestClient
from api.app import create_app
from cognitive_memory.architecture_models import (
    Observation,
    SemanticDocument,
    ProcedureProposal,
)


class ManagedDeletionTests(unittest.TestCase):
    def seed(self, client):
        a = client.app.state.memory.architecture
        observation = Observation(
            user_id="alice",
            thread_id="saved",
            task_id="task",
            source_event_id="one",
            content="我喜欢晨跑，今天去了公园",
        )
        analysis = {
            "semantic_candidates": [
                {
                    "subject": "alice",
                    "predicate": "preference",
                    "value": "晨跑",
                    "evidence_text": "我喜欢晨跑",
                }
            ],
            "episode_candidates": [{"observation": "今天去了公园"}],
        }
        receipt = a.observe(observation, analysis)
        a.ingest_document(
            "alice",
            SemanticDocument(
                document_id="note",
                document_version="1",
                content="我喜欢晨跑",
                source_ref=receipt["source_id"],
            ),
        )
        a.install_builtins("alice")
        return a, observation, analysis, receipt

    def test_all_catalog_types_delete_with_owner_isolation_and_counts(self):
        with TestClient(create_app(":memory:")) as c:
            a, _, _, _ = self.seed(c)
            rows = c.get(
                "/api/memories?user_id=alice&view=all&include_archived=true"
            ).json()["items"]
            self.assertEqual(
                {r["memory_type"] for r in rows},
                {"working", "semantic", "episodic", "procedural"},
            )
            for row in rows:
                self.assertTrue(row["can_delete"])
                path = "/api/memories/" + row["id"]
                self.assertEqual(c.delete(path + "?user_id=bob").status_code, 404)
                self.assertEqual(c.delete(path + "?user_id= ALICE ").status_code, 200)
                self.assertEqual(c.get(path + "?user_id=alice").status_code, 404)
                self.assertEqual(c.delete(path + "?user_id=alice").status_code, 404)
            self.assertEqual(
                c.get("/api/overview?user_id=alice").json()["total_count"], 0
            )

    def test_deleting_one_fact_preserves_siblings_source_and_conversation(self):
        with TestClient(create_app(":memory:")) as c:
            a, observation, analysis, receipt = self.seed(c)
            fact = a.repo.rows("semantic_assertions", "alice")[0]
            a.retrieve("alice", "other", "task", "晨跑", modules=["semantic"])
            self.assertTrue(a.working_state("alice", "other", "task").active_knowledge)
            self.assertEqual(
                c.delete("/api/memories/" + fact["id"] + "?user_id=alice").status_code,
                200,
            )
            self.assertIsNotNone(
                a.repo.get("source_records", "alice", receipt["source_id"])
            )
            self.assertEqual(len(a.repo.rows("episode_events", "alice")), 1)
            self.assertEqual(len(a.repo.rows("semantic_documents", "alice")), 1)
            self.assertFalse(
                any(
                    r.get("memory_id") == fact["id"]
                    for r in a.working_state("alice", "other", "task").active_knowledge
                )
            )
            replay = a.observe(observation, analysis)
            self.assertEqual(a.repo.rows("semantic_assertions", "alice"), [])
            self.assertTrue(
                any(r.get("result_status") == "deleted" for r in replay["operations"])
            )
            self.assertFalse(
                any(
                    fact["id"] in (r["from"], r["to"])
                    for r in a.repo.rows("memory_links", "alice")
                )
            )

    def test_deleted_procedure_versions_are_not_reused_or_executable(self):
        with TestClient(create_app(":memory:")) as c:
            a, _, _, receipt = self.seed(c)
            proposal = ProcedureProposal(
                description="Normalize text",
                kind="reasoning",
                implementation_ref="text.normalize",
                source_refs=[receipt["source_id"]],
            )
            v1 = a.propose_procedure("alice", proposal, key="version-check")
            v2 = a.propose_procedure("alice", proposal, key="version-check")
            a.validate_procedure("alice", v2["id"])
            a.activate_procedure("alice", v2["id"])
            a.execute_procedure("alice", v2["id"], {"text": "a   b"}, run_key="run")
            c.delete("/api/memories/" + v2["id"] + "?user_id=alice")
            self.assertIsNone(
                a.repo.get("procedures", "alice", v2["procedure_id"])["active_version"]
            )
            self.assertFalse(
                any(
                    r["version_id"] == v2["id"]
                    for r in a.repo.rows("procedure_runs", "alice")
                )
            )
            with self.assertRaises(ValueError):
                a.execute_procedure("alice", v2["id"], {"text": "a"}, run_key="new")
            v3 = a.propose_procedure("alice", proposal, key="version-check")
            self.assertEqual(v3["version"], 3)
            self.assertNotEqual(v3["id"], v2["id"])
            self.assertIsNotNone(a.repo.get("procedure_versions", "alice", v1["id"]))
