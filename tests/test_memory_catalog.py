"""Regression checks for shared reads across evolution, chat and management."""

import unittest

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from api.app import create_app
from cognitive_memory import Memory
from cognitive_memory.architecture_models import (
    EpisodeEvent,
    Observation,
    ObservationAnalysis,
    SemanticAssertion,
)
from cognitive_memory.storage.sqlite import SQLiteStorage
from conversation_agent.llm import LLMSettings


class ContextModel:
    def __init__(self):
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        return AIMessage(content="测试答复")


def native_preference(memory, user="alice"):
    return memory.architecture.observe(
        Observation(
            user_id=user,
            thread_id="saved",
            task_id="task",
            source_event_id="tea",
            content="我喜欢喝乌龙茶，今天买了乌龙茶",
        ),
        ObservationAnalysis(
            semantic_candidates=[
                SemanticAssertion(
                    subject=user,
                    predicate="drink_preference",
                    value="乌龙茶",
                    evidence_text="我喜欢喝乌龙茶",
                )
            ],
            episode_candidates=[EpisodeEvent(observation="今天买了乌龙茶")],
        ),
    )


class MemoryCatalogTests(unittest.TestCase):
    def test_evolution_and_manual_write_reach_new_chat_with_typed_knowledge(self):
        with TestClient(create_app(":memory:", demo_token="")) as client:
            agent = client.app.state.conversation_agent
            agent.settings = LLMSettings(api_key="")
            evolution = client.post(
                "/api/evolution/analyze",
                json={
                    "user_id": "alice",
                    "content": "我喜欢用 Python。",
                },
            )
            self.assertEqual(evolution.status_code, 201, evolution.text)
            manual = client.post(
                "/api/memories",
                json={
                    "user_id": "alice",
                    "content": "我喜欢用 Rust。",
                    "tags": ["preference"],
                },
            )
            self.assertEqual(manual.status_code, 201, manual.text)
            native_preference(client.app.state.memory)
            model = ContextModel()
            agent._model = model
            chat = client.post(
                "/api/chat",
                json={
                    "user_id": "alice",
                    "thread_id": "fresh",
                    "message": "我喜欢什么？",
                    "auto_remember": False,
                },
            )
            self.assertEqual(chat.status_code, 200, chat.text)
            refs = chat.json()["references"]
            contents = str([r["content"] for r in refs])
            for text in ("Python", "Rust", "乌龙茶"):
                self.assertIn(text, contents)
                self.assertIn(text, model.calls[-1][0].content)
            self.assertTrue(any(r.get("storage_kind") == "legacy" for r in refs))
            self.assertTrue(any(r["record"].get("value") == "乌龙茶" for r in refs))
            isolated = client.post(
                "/api/chat",
                json={
                    "user_id": "bob",
                    "thread_id": "fresh",
                    "message": "我喜欢什么？",
                    "auto_remember": False,
                },
            ).json()
            self.assertEqual(isolated["references"], [])
            self.assertNotIn("乌龙茶", model.calls[-1][0].content)
            api_refs = client.post(
                "/api/architecture/retrieve",
                json={
                    "user_id": " ALICE ",
                    "thread_id": "fresh",
                    "task_id": "task",
                    "query": "我喜欢什么？",
                },
            ).json()["items"]
            self.assertEqual({r["id"] for r in api_refs}, {r["id"] for r in refs})

    def test_overview_and_all_list_cover_four_modules_without_duplicate_copies(self):
        with TestClient(create_app(":memory:")) as client:
            memory = client.app.state.memory
            legacy = memory.add_memory(
                {"user_id": "alice", "content": "我喜欢 Python", "tags": ["preference"]}
            )["memory"]
            result = native_preference(memory)
            memory.architecture.install_builtins("alice")
            memory.architecture.update_working_state(
                "alice", "saved", "task", {"constraints": ["本次简短回答"]}
            )
            overview = client.get("/api/overview?user_id=alice").json()
            rows = client.get(
                "/api/memories?user_id=alice&view=all&include_archived=true"
            ).json()["items"]
            self.assertEqual(overview["total_count"], len(rows))
            self.assertEqual(
                set(overview["by_type"]),
                {"working", "semantic", "episodic", "procedural"},
            )
            self.assertEqual(
                overview["by_storage"], {"legacy": 1, "typed": len(rows) - 1}
            )
            old_api = client.get("/api/memories?user_id=alice").json()["items"]
            self.assertEqual(old_api, [legacy])
            native = next(r for r in rows if r.get("module") == "semantic_assertions")
            path = "/api/memories/" + native["id"]
            self.assertEqual(
                client.get(path + "?user_id=alice").json()["storage_kind"], "typed"
            )
            self.assertEqual(
                client.get(path + "/evidence?user_id=alice").json()["items"][0][
                    "content"
                ],
                "我喜欢喝乌龙茶，今天买了乌龙茶",
            )
            self.assertEqual(client.get(path + "?user_id=bob").status_code, 404)
            self.assertEqual(
                client.get(path + "/evidence?user_id=bob").status_code, 404
            )
            self.assertIsNone(native["importance"])
            self.assertTrue(native["can_delete"])
            self.assertTrue(
                any(
                    e["related_memory"] and e["related_memory"]["id"] == native["id"]
                    for e in overview["recent_activity"]
                )
            )
            self.assertEqual(
                client.get("/api/overview?user_id=bob").json()["total_count"], 0
            )
            client.delete(
                "/api/architecture/sources/" + result["source_id"] + "?user_id=alice"
            )
            self.assertNotIn(
                "乌龙茶", str(client.get("/api/overview?user_id=alice").json())
            )
            self.assertNotIn(
                "乌龙茶", str(client.get("/api/memories?user_id=alice&view=all").json())
            )

    def test_real_pre_architecture_data_is_deduplicated_and_remains_unverified(self):
        # SQLiteStorage creates the old schema without architecture tables.
        storage = SQLiteStorage()
        with storage.transaction():
            record_id = storage.insert_memory(
                {
                    "user_id": "alice",
                    "content": "我喜欢 Python",
                    "normalized_content": "我喜欢 python",
                    "memory_type": "semantic",
                    "state_role": "current",
                    "source": "user",
                    "tags": ["preference"],
                    "importance": 0.7,
                    "confidence": 0.8,
                    "saliency": 0.5,
                    "goal_relevance": 0,
                    "preference_strength": 0.7,
                    "attention_bias": 0,
                    "write_score": 0.7,
                }
            )
        with Memory(storage=storage) as fixture:
            self.assertEqual(fixture.stats("alice")["total_count"], 1)
            refs = fixture.catalog.retrieve("alice", "new", "task", "我喜欢什么？")
            self.assertEqual(len(refs), 1)
            self.assertEqual(refs[0]["state_role"], "candidate")
            self.assertEqual(refs[0]["record"]["state_role"], "candidate")
            self.assertEqual(refs[0]["epistemic_status"], "legacy_unverified")
            self.assertEqual(fixture.architecture.retrieve_knowledge("alice"), [])
            self.assertFalse(fixture.delete_memory("bob", record_id))
            self.assertTrue(fixture.delete_memory("alice", record_id))
            self.assertEqual(
                fixture.architecture.repo.rows("semantic_documents", "alice"), []
            )
            self.assertEqual(
                fixture.catalog.retrieve("alice", "new", "task", "Python"), []
            )

    def test_counts_are_not_limited_to_the_first_1000_records(self):
        with Memory() as memory:
            record = memory.add_memory(
                {"user_id": "alice", "content": "我喜欢 Python", "tags": ["preference"]}
            )["memory"]
            with memory.storage.transaction():
                for i in range(1001):
                    memory.storage.insert_memory(
                        {**record, "id": str(i), "content": f"记录{i}"}
                    )
            self.assertEqual(len(memory.catalog.list("alice", limit=1000)), 1000)
            self.assertEqual(memory.stats("alice")["total_count"], 1002)

    def test_legacy_candidates_and_working_do_not_become_current_or_executable(self):
        with Memory() as memory:
            for kind, role, text in [
                ("working", "working", "这次用 Python"),
                ("semantic", "candidate", "我可能喜欢 Python"),
                ("procedural", "current", "使用 Python 清洗数据，先读入再去重"),
            ]:
                record = memory.add_memory(
                    {
                        "user_id": "alice",
                        "content": text,
                        "memory_type": "semantic" if kind == "working" else kind,
                        "tags": ["preference"],
                    }
                )["memory"]
                with memory.storage.transaction():
                    memory.storage._conn.execute(
                        "UPDATE memories SET memory_type=?, state_role=? WHERE id=?",
                        (kind, role, record["id"]),
                    )
            refs = memory.catalog.retrieve("alice", "new", "task", "Python")
            self.assertEqual(len(refs), 1)
            self.assertEqual(refs[0]["module"], "semantic")
            self.assertEqual(refs[0]["record"]["memory_type"], "procedural")
            self.assertEqual(
                memory.catalog.retrieve(
                    "alice", "new", "task", "Python", modules=("procedural",)
                ),
                [],
            )
            self.assertEqual(
                memory.architecture.working_state("alice", "new", "task").constraints,
                [],
            )
