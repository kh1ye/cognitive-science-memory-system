import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from cognitive_memory import Memory
from cognitive_memory.architecture_models import Observation, ObservationAnalysis, SemanticAssertion
from conversation_agent import ConversationAgent
from langchain_core.messages import AIMessage
from scripts.vatsalabench_full import analyze_block, chunks, fork, ProbeModel


class AnswerModel:
    def invoke(self, messages):
        assert any("Query time: 2023-06-01" in str(m.content) for m in messages)
        assert any("hallway" in str(m.content) for m in messages)
        return AIMessage(content="hallway")


class FailingExtractionModel:
    def with_structured_output(self, *args, **kwargs):
        return self

    def invoke(self, messages):
        raise RuntimeError("schema rejected")


class StubExtractionModel:
    def with_structured_output(self, *args, **kwargs):
        class Structured:
            def invoke(self, messages):
                return {"parsed": ObservationAnalysis()}

        return Structured()

    def invoke(self, messages):
        raise AssertionError("fallback must not run")


class VatsalaAdapterTests(unittest.TestCase):
    def test_chunks_keep_original_role_and_text(self):
        content = "original\ntext" * 3000
        session = {"messages": [{"role": "assistant", "turn_id": "T1", "content": content}]}
        parts = chunks(session)
        self.assertEqual("".join(parts), "[assistant T1]\n" + content)
        self.assertTrue(all(len(p) <= 16000 for p in parts))

    def test_probe_uses_native_retrieval_and_does_not_change_checkpoint(self):
        with TemporaryDirectory() as directory:
            source, copy = Path(directory) / "source.db", Path(directory) / "copy.db"
            with Memory(source) as memory:
                memory.architecture.observe(Observation(user_id="alice", thread_id="history", task_id="import",
                    source_event_id="one", content="Harbor Sketch is in hallway", observed_at="2023-05-31T10:00:00"),
                    ObservationAnalysis(semantic_candidates=[SemanticAssertion(subject="Harbor Sketch",
                        predicate="display_room", value="hallway", evidence_text="Harbor Sketch is in hallway")]))
            before = hashlib.sha256(source.read_bytes()).hexdigest()
            fork(source, copy)
            with Memory(copy) as memory:
                wrapper = ProbeModel(AnswerModel(), "Use only memory", "2023-06-01")
                agent = ConversationAgent(memory, ":memory:", model=wrapper)
                try:
                    response = agent.chat("alice", "probe", "Harbor Sketch display room?", auto_remember=False, retention_policy="no_long_term")
                    self.assertEqual(response["answer"], "hallway")
                    self.assertTrue(response["references"])
                    self.assertEqual(len(memory.architecture.repo.rows("semantic_assertions", "alice")), 1)
                finally:
                    agent.close()
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)

    def test_analyze_block_failure_is_reported_not_raised(self):
        analysis, error = analyze_block(FailingExtractionModel(), "user message", "user message")
        self.assertIsNone(analysis)
        self.assertEqual(error["type"], "RuntimeError")
        self.assertIn("schema rejected", error["messages"])

    def test_analyze_block_returns_analysis_on_success(self):
        analysis, error = analyze_block(StubExtractionModel(), "user message", "user message")
        self.assertIsInstance(analysis, ObservationAnalysis)
        self.assertIsNone(error)


if __name__ == "__main__":
    unittest.main()
