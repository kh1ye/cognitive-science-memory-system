from __future__ import annotations

import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableLambda

from api.app import create_app
from cognitive_memory import Memory
from conversation_agent import ConversationAgent
from conversation_agent.llm import LLMSettings


class LocalModel:
    """Deterministic LangChain-compatible test double; the graph/SQLite are real."""

    def __init__(self):
        self.calls = []
        self.extraction_calls = []
        self.extraction = {"semantic_candidates": []}
        self.fail_reply = False
        self.fail_extraction = False

    def invoke(self, messages):
        self.calls.append(messages)
        if self.fail_reply:
            raise RuntimeError("provider failure with secret details")
        history = " | ".join(
            str(m.content) for m in messages if isinstance(m, HumanMessage)
        )
        return AIMessage(content="回答：" + history)

    def with_structured_output(self, schema, **kwargs):
        def extract(messages):
            self.extraction_calls.append(messages)
            if self.fail_extraction:
                raise ValueError("invalid structured response")
            return schema.model_validate(self.extraction)

        return RunnableLambda(extract)


def candidate(content, value="Python", **extra):
    return {
        "evidence_text": content,
        "subject": "alice",
        "predicate": "preferred_programming_language",
        "value": value,
        "sensitive": extra.get("sensitive", False),
        "correction": extra.get("correction", False),
    }


class ConversationAgentTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.engine = Memory(Path(self.directory.name) / "memory.db")
        self.addCleanup(self.engine.close)
        self.path = Path(self.directory.name) / "sessions.db"
        self.model = LocalModel()
        self.agent = ConversationAgent(self.engine, self.path, model=self.model)
        self.addCleanup(lambda: self.agent.close())

    def test_format_changes_preserve_the_original_user_evidence(self):
        self.model.extraction = {
            "semantic_candidates": [
                candidate(
                    "我喜欢用 Python 做数据分析。", tags=["preference", "communication"]
                )
            ]
        }
        result = self.agent.chat("alice", "format", "我喜欢用Python做数据分析")
        self.assertEqual(result["memory_results"][0]["status"], "succeeded")
        self.assertEqual(
            self.engine.architecture.retrieve_knowledge("alice")[0]["evidence_text"],
            "我喜欢用Python做数据分析",
        )

    def test_memory_status_distinguishes_empty_disabled_and_privacy(self):
        empty = self.agent.chat("alice", "status", "你是谁")
        self.assertEqual(empty["memory_status"], "no_new_memory")
        disabled = self.agent.chat(
            "alice", "status", "我喜欢 Python", auto_remember=False
        )
        self.assertEqual(disabled["memory_status"], "disabled")
        blocked = self.agent.chat("alice", "status", "不要保存这句话")
        self.assertEqual(blocked["memory_status"], "privacy_blocked")
        self.assertEqual(
            self.agent.get_session("alice", "status")["messages"][-1]["memory_status"],
            "privacy_blocked",
        )

    def test_failed_structured_extraction_gets_one_json_recovery(self):
        self.model.fail_extraction = True
        original = self.model.invoke

        def invoke(messages):
            if "只输出符合以下 schema" in messages[0].content:
                return AIMessage(
                    content=json.dumps(
                        {"semantic_candidates": [candidate("以后请用中文回答")]}
                    )
                )
            return original(messages)

        self.model.invoke = invoke
        result = self.agent.chat("alice", "recover", "以后请用中文回答")
        self.assertEqual(result["memory_results"][0]["status"], "succeeded")
        self.assertEqual(result["warnings"], [])

    def test_tool_free_json_response_is_recovered_without_another_model_call(self):
        self.model.with_structured_output = lambda *args, **kwargs: RunnableLambda(
            lambda messages: {
                "parsed": None,
                "raw": AIMessage(content='```json\n{"semantic_candidates": []}\n```'),
                "parsing_error": None,
            }
        )
        result = self.agent.chat("alice", "json", "你好")
        self.assertEqual(result["memory_status"], "no_new_memory")
        self.assertEqual(len(self.model.calls), 1)

    def test_anthropic_text_blocks_are_saved_without_thinking(self):
        self.model.invoke = lambda messages: AIMessage(
            content=[
                {
                    "type": "thinking",
                    "thinking": "internal reasoning",
                    "signature": "test",
                },
                {"type": "text", "text": "你好，测试完成。"},
            ]
        )
        result = self.agent.chat("alice", "blocks", "你好", auto_remember=False)
        self.assertEqual(result["answer"], "你好，测试完成。")
        self.assertNotIn(
            "internal reasoning", str(self.agent.get_session("alice", "blocks"))
        )

    def test_sqlite_restores_context_after_reopening(self):
        self.agent.chat("alice", "thread-one", "我的项目叫 Atlas", auto_remember=False)
        self.agent.close()
        self.agent = ConversationAgent(self.engine, self.path, model=self.model)
        result = self.agent.chat(
            "alice", "thread-one", "项目叫什么？", auto_remember=False
        )
        self.assertIn("Atlas", result["answer"])
        session = self.agent.get_session("alice", "thread-one")
        self.assertEqual(len(session["messages"]), 4)
        self.assertEqual(session["messages"][0]["text"], "我的项目叫 Atlas")
        self.assertEqual(len(self.model.extraction_calls), 0)

    def test_long_term_memory_is_shared_across_threads_but_not_users(self):
        self.model.extraction = {"semantic_candidates": [candidate("我喜欢 Python")]}
        saved = self.agent.chat("alice", "first", "我喜欢 Python")
        self.assertEqual(saved["memory_results"][0]["status"], "succeeded")
        result = self.agent.chat(
            "alice", "second", "我喜欢什么编程语言？", auto_remember=False
        )
        self.assertEqual(
            result["references"][0]["record"]["evidence_text"], "我喜欢 Python"
        )
        self.assertIn("我喜欢 Python", self.model.calls[-1][0].content)
        self.assertEqual(
            len([m for m in self.model.calls[-1] if isinstance(m, HumanMessage)]), 1
        )
        bob = self.agent.chat(
            "bob", "second", "我喜欢什么编程语言？", auto_remember=False
        )
        self.assertEqual(bob["references"], [])
        self.assertEqual(len(self.agent.list_sessions("alice")), 2)
        self.assertEqual(len(self.agent.list_sessions("bob")), 1)

    def test_memory_engine_still_owns_conflict_and_consolidation(self):
        for text, value in [
            ("我主要使用 Python", "Python"),
            ("我现在主要使用 Rust", "Rust"),
            ("确认我的主要语言已变成 Rust", "Rust"),
        ]:
            self.model.extraction = {
                "semantic_candidates": [
                    candidate(text, value, correction=value == "Rust")
                ]
            }
            result = self.agent.chat("alice", "preferences", text)
        self.assertEqual(result["memory_results"][0]["status"], "succeeded")
        rows = self.engine.architecture.retrieve_knowledge("alice", history=True)
        self.assertTrue(
            any(row["status"] == "history" and row["value"] == "Python" for row in rows)
        )
        self.assertTrue(
            any(row["status"] == "current" and row["value"] == "Rust" for row in rows)
        )

    def test_privacy_opt_out_sensitive_and_invented_memory_are_rejected(self):
        self.model.extraction = {"semantic_candidates": [candidate("我喜欢 Python")]}
        self.agent.chat("alice", "privacy", "不要记住，我喜欢 Python")
        self.assertEqual(self.model.extraction_calls, [])
        self.model.extraction = {
            "semantic_candidates": [candidate("我有花生过敏", sensitive=True)]
        }
        result = self.agent.chat("alice", "privacy", "我有花生过敏")
        self.assertEqual(result["memory_status"], "privacy_blocked")
        self.model.extraction = {"semantic_candidates": [candidate("我喜欢 Rust")]}
        result = self.agent.chat("alice", "privacy", "我喜欢茶")
        self.assertEqual(result["memory_results"][0]["status"], "failed")
        self.assertEqual(self.engine.architecture.retrieve_knowledge("alice"), [])

    def test_extraction_failure_keeps_answer_and_checkpoint(self):
        self.model.fail_extraction = True
        result = self.agent.chat("alice", "failure", "我喜欢茶")
        self.assertTrue(result["answer"])
        self.assertTrue(result["warnings"])
        session = self.agent.get_session("alice", "failure")
        self.assertEqual(len(session["messages"]), 2)
        self.assertEqual(session["messages"][-1]["warnings"], result["warnings"])

    def test_delete_session_removes_checkpoints_and_preserves_long_term_memory(self):
        self.model.extraction = {"semantic_candidates": [candidate("我喜欢 Python")]}
        self.agent.chat("alice", "delete", "我喜欢 Python")
        self.assertFalse(self.agent.delete_session("bob", "delete"))
        self.assertTrue(self.agent.delete_session("alice", "delete"))
        self.assertIsNone(self.agent.get_session("alice", "delete"))
        self.assertIsNone(
            self.agent.checkpointer.get_tuple(self.agent._config("alice", "delete"))
        )
        self.assertEqual(len(self.engine.architecture.retrieve_knowledge("alice")), 1)


class ConversationApiTests(unittest.TestCase):
    def test_chat_and_session_api_survive_restart(self):
        model = LocalModel()
        with TemporaryDirectory() as directory:
            db_path = Path(directory) / "memory.db"
            with TestClient(create_app(db_path, chat_model=model)) as client:
                created = client.post("/api/sessions", json={"user_id": "alice"})
                self.assertEqual(created.status_code, 201)
                thread_id = created.json()["id"]
                payload = {
                    "user_id": "alice",
                    "thread_id": thread_id,
                    "message": "我叫小明",
                }
                self.assertEqual(
                    client.post("/api/chat", json=payload).status_code, 200
                )
            with TestClient(create_app(db_path, chat_model=model)) as client:
                payload["message"] = "我叫什么？"
                response = client.post("/api/chat", json=payload)
                self.assertEqual(response.status_code, 200)
                self.assertIn("小明", response.json()["answer"])
                sessions = client.get("/api/sessions?user_id=alice").json()["items"]
                self.assertEqual(len(sessions), 1)
                self.assertEqual(len(sessions[0]["messages"]), 4)
                self.assertEqual(
                    client.get(f"/api/sessions/{thread_id}?user_id=bob").status_code,
                    404,
                )
                self.assertEqual(
                    client.delete(f"/api/sessions/{thread_id}?user_id=bob").status_code,
                    404,
                )
                self.assertEqual(
                    client.delete(
                        f"/api/sessions/{thread_id}?user_id=alice"
                    ).status_code,
                    200,
                )
                self.assertEqual(
                    client.get("/api/sessions?user_id=alice").json()["items"], []
                )

    def test_missing_model_and_validation_errors_are_clear(self):
        with (
            patch.dict(os.environ, {"LLM_API_KEY": "", "OPENAI_API_KEY": ""}),
            TestClient(create_app(":memory:")) as client,
        ):
            response = client.post("/api/chat", json={"message": "你好"})
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()["error"], "model_not_configured")
            self.assertFalse(client.get("/api/chat/status").json()["configured"])
            for payload in (
                {"message": "  "},
                {"message": "你好", "thread_id": "../other"},
                {"message": "你好", "user_id": " "},
            ):
                self.assertEqual(
                    client.post("/api/chat", json=payload).status_code, 400
                )
            self.assertEqual(client.get("/api/health").status_code, 200)

    def test_model_failure_does_not_expose_provider_details_and_can_continue(self):
        model = LocalModel()
        model.fail_reply = True
        with TestClient(create_app(":memory:", chat_model=model)) as client:
            payload = {"thread_id": "retry", "message": "你好"}
            response = client.post("/api/chat", json=payload)
            self.assertEqual(response.status_code, 502)
            self.assertNotIn("secret", response.text)
            model.fail_reply = False
            payload["message"] = "继续"
            self.assertEqual(client.post("/api/chat", json=payload).status_code, 200)

    def test_env_file_and_anthropic_model_configuration(self):
        with (
            patch(
                "conversation_agent.llm.dotenv_values",
                return_value={
                    "LLM_PROVIDER": "anthropic",
                    "LLM_MODEL": "test-anthropic-model",
                    "LLM_BASE_URL": "https://provider.example/anthropic",
                    "LLM_API_KEY": "file-test-key",
                },
            ),
            patch.dict(os.environ, {"LLM_MODEL": "shell-model"}, clear=True),
        ):
            settings = LLMSettings.from_env()
            self.assertEqual(settings.model, "shell-model")
            self.assertEqual(settings.api_key, "file-test-key")
            model = settings.create_model()
            from langchain_anthropic import ChatAnthropic

            self.assertIsInstance(model, ChatAnthropic)
            self.assertEqual(
                model.anthropic_api_url, "https://provider.example/anthropic"
            )
            self.assertNotIn("file-test-key", repr(settings))

    def test_real_langchain_openai_transport_with_local_provider(self):
        requests = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append(data)
                message = {
                    "role": "assistant",
                    "content": "你好，我会结合记忆与你交谈。",
                }
                if data.get("tools"):
                    message = {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "extract-1",
                                "type": "function",
                                "function": {
                                    "name": data["tools"][0]["function"]["name"],
                                    "arguments": json.dumps(
                                        {
                                            "semantic_candidates": [
                                                candidate("我喜欢 Python")
                                            ]
                                        },
                                        ensure_ascii=False,
                                    ),
                                },
                            }
                        ],
                    }
                body = json.dumps(
                    {
                        "id": "local-response",
                        "object": "chat.completion",
                        "created": 1,
                        "model": data["model"],
                        "choices": [
                            {
                                "index": 0,
                                "message": message,
                                "finish_reason": "tool_calls"
                                if data.get("tools")
                                else "stop",
                            }
                        ],
                        "usage": {
                            "prompt_tokens": 1,
                            "completion_tokens": 1,
                            "total_tokens": 2,
                        },
                    }
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with (
                patch.dict(
                    os.environ,
                    {
                        "LLM_MODEL": "local-test-model",
                        "LLM_PROVIDER": "openai",
                        "LLM_API_KEY": "local-test-key",
                        "LLM_BASE_URL": f"http://127.0.0.1:{server.server_port}/v1",
                        "NO_PROXY": "127.0.0.1,localhost",
                    },
                ),
                TestClient(create_app(":memory:")) as client,
            ):
                response = client.post("/api/chat", json={"message": "我喜欢 Python"})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(
                    response.json()["memory_results"][0]["status"],
                    "succeeded",
                )
                self.assertEqual(requests[0]["model"], "local-test-model")
                self.assertEqual(len(requests), 2)
                self.assertNotIn("local-test-key", repr(LLMSettings.from_env()))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
