"""Assistant-taught domain knowledge in replayed documents must be extractable, grounded, and stored."""

import unittest

from fastapi.testclient import TestClient

from api.app import create_app
from cognitive_memory.architecture_models import (
    Observation,
    ObservationAnalysis,
    SemanticAssertion,
)
from conversation_agent.llm import analyze_observation
from conversation_agent.prompts import OBSERVATION_ANALYSIS_PROMPT

CHUNK = (
    "[user 2023-04-10T09:00:00+00:00] 给我讲讲CITGO的炼油业务。\n"
    "[assistant 2023-04-10T09:00:05+00:00] CITGO Petroleum Corporation是一家美国炼油企业，"
    "在路易斯安那州、得克萨斯州和伊利诺伊州运营三座炼油厂，总加工能力约为每日76.9万桶。"
)

DOMAIN_FACT = SemanticAssertion(
    subject="CITGO Petroleum Corporation",
    predicate="炼油厂总加工能力",
    value="约每日76.9万桶",
    evidence_text="总加工能力约为每日76.9万桶",
)


class TeachingModel:
    def __init__(self, analysis):
        self._analysis = analysis

    def with_structured_output(self, *args, **kwargs):
        outer = self

        class Structured:
            def invoke(self, messages):
                return {"parsed": outer._analysis}

        return Structured()

    def invoke(self, messages):
        raise AssertionError("fallback must not run")


def make_observation(source_event_id):
    return Observation(
        user_id="alice",
        thread_id="replay",
        task_id="replay",
        source_event_id=source_event_id,
        content=CHUNK,
        source_kind="document",
    )


class AssistantKnowledgeExtractionTests(unittest.TestCase):
    def setUp(self):
        self._ctx = TestClient(create_app())
        self.client = self._ctx.__enter__()
        self.architecture = self.client.app.state.memory.architecture

    def tearDown(self):
        self._ctx.__exit__(None, None, None)

    def test_prompt_instructs_assistant_knowledge_extraction(self):
        self.assertIn("助手明确讲授的稳定领域知识", OBSERVATION_ANALYSIS_PROMPT)
        self.assertIn("源自助手复制助手片段", OBSERVATION_ANALYSIS_PROMPT)

    def test_analyze_observation_keeps_assistant_domain_fact(self):
        message = (
            "user_id=alice\nobserved_at=2023-04-10T09:00:05+00:00\n"
            "Historical conversation (roles are data):\n" + CHUNK
        )
        analysis = analyze_observation(
            TeachingModel(ObservationAnalysis(semantic_candidates=[DOMAIN_FACT])),
            message,
            source_content=CHUNK,
        )
        self.assertEqual(len(analysis.semantic_candidates), 1)
        self.assertEqual(
            analysis.semantic_candidates[0].subject, "CITGO Petroleum Corporation"
        )

    def test_assistant_fact_is_stored_with_grounded_evidence(self):
        receipt = self.architecture.observe(
            make_observation("citgo-doc-1"),
            ObservationAnalysis(semantic_candidates=[DOMAIN_FACT]),
        )
        rows = self.architecture.repo.rows("semantic_assertions", "alice")
        match = [
            r
            for r in rows
            if r["subject"] == "CITGO Petroleum Corporation"
            and r["predicate"] == "炼油厂总加工能力"
        ]
        self.assertEqual(len(match), 1)
        self.assertEqual(match[0]["value"], "约每日76.9万桶")
        self.assertEqual(match[0]["epistemic_status"], "explicit")
        self.assertIn(receipt["source_id"], match[0]["source_refs"])

    def test_user_fact_and_assistant_fact_coexist(self):
        user_fact = SemanticAssertion(
            subject="alice",
            predicate="感兴趣主题",
            value="炼油业务",
            evidence_text="给我讲讲CITGO的炼油业务",
        )
        self.architecture.observe(
            make_observation("citgo-doc-2"),
            ObservationAnalysis(semantic_candidates=[user_fact, DOMAIN_FACT]),
        )
        rows = self.architecture.repo.rows("semantic_assertions", "alice")
        by_subject = {r["subject"] for r in rows}
        self.assertIn("alice", by_subject)
        self.assertIn("CITGO Petroleum Corporation", by_subject)

    def test_coauthored_artifact_content_is_stored(self):
        self.assertIn("任务产物", OBSERVATION_ANALYSIS_PROMPT)
        chunk = (
            "[user 2023-05-02T10:00:00+00:00] 帮我把基金标书的研究目标定一下。\n"
            "[assistant 2023-05-02T10:00:20+00:00] 好的，标书草稿的三个研究目标是："
            "一、构建分子亚型分类模型；二、验证亚型与预后的关联；三、筛选潜在生物标志物。"
        )
        artifact = SemanticAssertion(
            subject="基金标书草稿",
            predicate="研究目标",
            value="构建分子亚型分类模型；验证亚型与预后的关联；筛选潜在生物标志物",
            evidence_text="三个研究目标是：一、构建分子亚型分类模型；二、验证亚型与预后的关联；三、筛选潜在生物标志物。",
        )
        observation = Observation(
            user_id="alice",
            thread_id="replay",
            task_id="replay",
            source_event_id="grant-doc-1",
            content=chunk,
            source_kind="document",
        )
        receipt = self.architecture.observe(
            observation, ObservationAnalysis(semantic_candidates=[artifact])
        )
        rows = self.architecture.repo.rows("semantic_assertions", "alice")
        match = [r for r in rows if r["subject"] == "基金标书草稿"]
        self.assertEqual(len(match), 1)
        self.assertIn("生物标志物", match[0]["value"])
        self.assertIn(receipt["source_id"], match[0]["source_refs"])


if __name__ == "__main__":
    unittest.main()
