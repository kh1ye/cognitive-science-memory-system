import unittest

from langchain_core.messages import AIMessage

from cognitive_memory import Memory
from cognitive_memory.architecture_models import (
    Observation,
    ObservationAnalysis,
    SemanticAssertion,
)
from cognitive_memory.value import context_only
from conversation_agent import ConversationAgent


class ReplyOnlyModel:
    def invoke(self, messages):
        return AIMessage(content="你好")

    def with_structured_output(self, *args, **kwargs):
        raise AssertionError("Context-only input must skip extraction")


class ContextOnlyTests(unittest.TestCase):
    def test_noise_is_blocked_even_if_analyzer_proposes_long_term_facts(self):
        for i, text in enumerate(
            [
                "在吗",
                "你好！",
                "好的",
                "收到",
                "谢谢",
                "哈哈哈",
                "。。。",
                "😊",
                "aaaaaa",
                "测试一下",
                "我试一下能不能发出去",
                "这是一条测试消息",
                "1+1等于几？",
            ]
        ):
            with self.subTest(text=text), Memory() as memory:
                result = memory.architecture.observe(
                    Observation(
                        user_id="alice",
                        thread_id="chat",
                        task_id="task",
                        source_event_id=str(i),
                        content=text,
                    ),
                    ObservationAnalysis(
                        semantic_candidates=[
                            SemanticAssertion(
                                subject="alice",
                                predicate="noise",
                                value=text,
                                evidence_text=text,
                            )
                        ]
                    ),
                )
                self.assertEqual(result["operations"], [])
                self.assertEqual(memory.architecture.retrieve_knowledge("alice"), [])
                self.assertIsNone(
                    memory.architecture.repo.rows("source_records", "alice")[0][
                        "content"
                    ]
                )
                self.assertEqual(
                    memory.architecture.working_state(
                        "alice", "chat", "task"
                    ).observations[0]["content"],
                    text,
                )

    def test_short_facts_and_mixed_greeting_are_not_rejected(self):
        for text in [
            "我喜欢茶",
            "我叫李明",
            "你好，我喜欢 Python",
            "项目测试通过了",
            "我想学游泳",
            "我试着修好了电风扇",
        ]:
            self.assertFalse(context_only(text), text)

    def test_graph_keeps_conversation_without_extraction_or_long_term_write(self):
        with Memory() as memory:
            agent = ConversationAgent(memory, ":memory:", model=ReplyOnlyModel())
            try:
                result = agent.chat("alice", "chat", "在吗")
                self.assertEqual(result["memory_status"], "no_new_memory")
                self.assertEqual(result["warnings"], [])
                self.assertEqual(result["memory_results"], [])
                self.assertTrue(agent.get_session("alice", "chat")["messages"])
                self.assertEqual(memory.architecture.retrieve_knowledge("alice"), [])
                self.assertTrue(
                    all(
                        s["content"] is None
                        for s in memory.architecture.repo.rows(
                            "source_records", "alice"
                        )
                    )
                )
            finally:
                agent.close()

    def test_unmatched_chitchat_with_empty_analysis_keeps_only_context_body(self):
        from langchain_core.runnables import RunnableLambda

        class EmptyAnalysisModel(ReplyOnlyModel):
            def with_structured_output(self, schema, **kwargs):
                return RunnableLambda(lambda messages: schema())

        with Memory() as memory:
            agent = ConversationAgent(memory, ":memory:", model=EmptyAnalysisModel())
            try:
                result = agent.chat("alice", "chat", "路过打个招呼")
                self.assertEqual(result["memory_status"], "no_new_memory")
                self.assertEqual(result["warnings"], [])
                self.assertEqual(result["memory_results"], [])
                self.assertTrue(agent.get_session("alice", "chat")["messages"])
                self.assertTrue(
                    all(
                        s["content"] is None
                        for s in memory.architecture.repo.rows(
                            "source_records", "alice"
                        )
                    )
                )
            finally:
                agent.close()
