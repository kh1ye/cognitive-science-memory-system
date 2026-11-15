"""Portable example history must not overwrite user chats or teach profile facts."""
import json
from langchain_core.messages import AIMessage
from pathlib import Path
import unittest

from cognitive_memory import Memory
from conversation_agent import ConversationAgent
from conversation_agent.llm import LLMSettings
from scripts.seed_emotion_conversations import seed_conversations
from tests.test_conversation_agent import LocalModel

FIXTURE = Path(__file__).resolve().parents[1] / "examples/assistant-emotions/conversations.json"


class EmotionExampleTests(unittest.TestCase):
    def test_import_is_idempotent_isolated_and_never_writes_long_term_memory(self):
        with Memory(":memory:") as memory:
            agent = ConversationAgent(memory, ":memory:", settings=LLMSettings())
            try:
                fixture = json.loads(FIXTURE.read_text())
                before = memory.storage._conn.total_changes
                result = seed_conversations(agent, fixture, "demo-user")
                self.assertEqual(len(result["added"]), 6)
                self.assertEqual(before, memory.storage._conn.total_changes)
                sessions = agent.list_sessions("demo-user")
                self.assertEqual(len(sessions), 6)
                self.assertTrue(all("[示例]" not in session["title"] for session in sessions))
                self.assertEqual(agent.list_sessions("other-user"), [])
                multi = agent.get_session("demo-user", "emotion-example-changes-v1")
                self.assertEqual(len(multi["messages"]), 8)
                self.assertNotIn("本组测试", str(multi["messages"]))
                self.assertEqual(multi["example_emotion"]["label"], "tired")
                self.assertEqual(agent._emotions, {})
                self.assertNotIn("emotion", multi)
                repeated = seed_conversations(agent, fixture, "demo-user")
                self.assertEqual(repeated["added"], [])
                self.assertEqual(len(repeated["skipped"]), 6)
                self.assertEqual(len(agent.get_session("demo-user", multi["id"])["messages"]), 8)
                legacy_id = "emotion-example-happy-v1"
                agent.graph.update_state(agent._config("demo-user", legacy_id), {
                    "messages": [AIMessage(content="本组测试表情：😄", id=legacy_id + "-intro")]
                }, as_node="decide")
                seed_conversations(agent, fixture, "demo-user")
                cleaned = agent.get_session("demo-user", legacy_id)
                self.assertNotIn("本组测试", str(cleaned["messages"]))
                self.assertEqual(len(cleaned["messages"]), 2)
                agent._model = LocalModel()
                result = agent.chat("demo-user", multi["id"], "继续聊聊", auto_remember=False)
                self.assertEqual(result["emotion"]["label"], "neutral")
                self.assertNotIn("example_emotion", agent.get_session("demo-user", multi["id"]))
                seed_conversations(agent, fixture, "demo-user")
                self.assertEqual(len(agent.get_session("demo-user", multi["id"])["messages"]), 10)
            finally:
                agent.close()
