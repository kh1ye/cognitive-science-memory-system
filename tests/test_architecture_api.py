import unittest

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from api.app import create_app
from cognitive_memory import Memory
from conversation_agent import ConversationAgent


class FakeModel:
    def __init__(self):
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        return AIMessage(content="已回答")

    def with_structured_output(self, schema, **kwargs):
        return RunnableLambda(
            lambda messages: schema.model_validate(
                {
                    "working_state_patch": {"constraints": ["this task only"]},
                    "semantic_candidates": [
                        {
                            "subject": "alice",
                            "predicate": "language",
                            "value": "中文",
                            "evidence_text": "以后用中文",
                        }
                    ],
                }
            )
        )


class ArchitectureIntegrationTests(unittest.TestCase):
    def test_api_observe_retrieve_registry_run_and_delete(self):
        with TestClient(create_app(":memory:")) as c:
            body = {
                "observation": {
                    "user_id": "alice",
                    "thread_id": "chat",
                    "task_id": "task",
                    "source_event_id": "e",
                    "content": "以后用中文",
                },
                "analysis": {
                    "semantic_candidates": [
                        {
                            "subject": "alice",
                            "predicate": "language",
                            "value": "中文",
                            "evidence_text": "以后用中文",
                        }
                    ]
                },
            }
            r = c.post("/api/architecture/observe", json=body)
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json()["operations"][0]["status"], "succeeded")
            source = r.json()["source_id"]
            self.assertEqual(
                c.get(
                    "/api/architecture/objects/semantic_assertions?user_id=bob"
                ).json()["items"],
                [],
            )
            c.post(
                "/api/architecture/procedures/install-builtins",
                json={"user_id": "alice"},
            )
            versions = c.get(
                "/api/architecture/objects/procedure_versions?user_id=alice"
            ).json()["items"]
            p = next(
                row for row in versions if row["implementation_ref"] == "text.normalize"
            )
            result = c.post(
                "/api/architecture/runs/" + p["id"],
                json={
                    "user_id": "alice",
                    "arguments": {"text": " a   b "},
                    "run_key": "one",
                },
            )
            self.assertEqual(result.json()["result"], {"text": "a b"})
            self.assertEqual(
                c.delete(
                    "/api/architecture/sources/" + source + "?user_id=bob"
                ).status_code,
                404,
            )
            self.assertEqual(
                c.delete(
                    "/api/architecture/sources/" + source + "?user_id=alice"
                ).status_code,
                200,
            )
            self.assertEqual(
                c.get(
                    "/api/architecture/objects/semantic_assertions?user_id=alice"
                ).json()["items"],
                [],
            )

    def test_graph_loop_task_boundary_no_persist_and_source_deletion(self):
        with Memory() as m:
            model = FakeModel()
            agent = ConversationAgent(m, ":memory:", model=model)
            self.addCleanup(agent.close)
            result = agent.chat(
                "alice", "chat", "以后用中文", task_id="one", source_event_id="e"
            )
            self.assertEqual(result["stop_reason"], "turn_complete")
            self.assertEqual(result["memory_results"][0]["status"], "succeeded")
            agent.chat(
                "alice", "chat", "second task", task_id="two", auto_remember=False
            )
            self.assertEqual(
                m.architecture.working_state("alice", "chat", "two").constraints, []
            )
            self.assertNotIn(
                "以后用中文", str([x.content for x in model.calls[-1][1:]])
            )
            before = {
                table: len(m.architecture.repo.rows(table, "alice"))
                for table in ["working_states", "source_records", "learning_operations"]
            }
            agent.chat("alice", "ephemeral", "private", retention_policy="no_persist")
            self.assertIsNone(agent.get_session("alice", "ephemeral"))
            for table, count in before.items():
                self.assertEqual(len(m.architecture.repo.rows(table, "alice")), count)
            source = next(
                r
                for r in m.architecture.repo.rows("source_records", "alice")
                if r["source_event_id"] == "e"
            )
            m.architecture.delete_source("alice", source["id"])
            self.assertEqual(agent.list_sessions("alice"), [])

    def test_no_persist_policy_does_not_create_any_checkpoint(self):
        with TestClient(create_app(":memory:", chat_model=FakeModel())) as c:
            r = c.post(
                "/api/chat",
                json={
                    "user_id": "alice",
                    "message": "private",
                    "thread_id": "private",
                    "retention_policy": "no_persist",
                },
            )
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(c.get("/api/sessions?user_id=alice").json()["items"], [])
            self.assertEqual(
                c.get("/api/architecture/objects/source_records?user_id=alice").json()[
                    "items"
                ],
                [],
            )
