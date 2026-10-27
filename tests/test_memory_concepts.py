"""Response-contract tests; semantic accuracy is measured by live evaluation."""

import unittest

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableLambda
from pydantic import ValidationError

from conversation_agent.llm import analyze_observation
from conversation_agent.memory_concepts import classify_memory_concept


class ResponseModel:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def with_structured_output(self, schema, **kwargs):
        def invoke(messages):
            self.calls.append(messages)
            return self.response

        return RunnableLambda(invoke)


class MemoryConceptTests(unittest.TestCase):
    def test_text_json_recovery_uses_the_same_response_without_reasking(self):
        model = ResponseModel(
            {
                "parsed": None,
                "raw": AIMessage(
                    content=[
                        {"type": "thinking", "thinking": "not a public prediction"},
                        {
                            "type": "text",
                            "text": '```json\n{"label":"semantic","reason":"陈述知识。"}\n```',
                        },
                    ]
                ),
            }
        )
        prediction, _ = classify_memory_concept(model, "只知道某种做法")
        self.assertEqual(prediction.label, "semantic")
        self.assertEqual(len(model.calls), 1)
        self.assertEqual(
            [m.content for m in model.calls[0] if isinstance(m, HumanMessage)],
            ["只知道某种做法"],
        )

    def test_invalid_category_is_not_silently_changed_to_a_valid_answer(self):
        model = ResponseModel({"parsed": {"label": "workflow", "reason": "流程"}})
        with self.assertRaises(ValidationError):
            classify_memory_concept(model, "某个例子")
        self.assertEqual(len(model.calls), 1)

    def test_malformed_response_fails_without_selecting_another_answer(self):
        model = ResponseModel({"parsed": None, "raw": AIMessage(content="not JSON")})
        with self.assertRaises(ValueError):
            classify_memory_concept(model, "某个例子")
        self.assertEqual(len(model.calls), 1)

    def test_empty_input_and_unknown_prompt_fail_before_calling_model(self):
        model = ResponseModel({})
        with self.assertRaises(ValueError):
            classify_memory_concept(model, " ")
        with self.assertRaises(KeyError):
            classify_memory_concept(model, "某个例子", prompt_version="missing")
        self.assertEqual(model.calls, [])

    def test_event_paraphrase_gets_one_grounded_repair_before_learning(self):
        class RepairModel(ResponseModel):
            def invoke(self, messages):
                self.calls.append(messages)
                return AIMessage(
                    content='{"episode_candidates":[{"observation":"刚才把木板装反了"}]}'
                )

        model = RepairModel(
            {"episode_candidates": [{"observation": "用户组装时把木板弄反了"}]}
        )
        analysis = analyze_observation(
            model, "user_id=test\n刚才把木板装反了", source_content="刚才把木板装反了"
        )
        self.assertEqual(analysis.episode_candidates[0].observation, "刚才把木板装反了")
        self.assertEqual(len(model.calls), 2)

    def test_metadata_is_not_valid_event_evidence_and_bad_repair_is_rejected(self):
        class InvalidRepairModel(ResponseModel):
            def invoke(self, messages):
                self.calls.append(messages)
                return AIMessage(
                    content='{"episode_candidates":[{"observation":"user_id=test"}]}'
                )

        model = InvalidRepairModel(
            {"episode_candidates": [{"observation": "user_id=test"}]}
        )
        with self.assertRaises(ValueError):
            analyze_observation(model, "user_id=test\n你好", source_content="你好")
        self.assertEqual(len(model.calls), 2)

    def test_event_punctuation_normalization_does_not_need_a_repair_call(self):
        model = ResponseModel({"episode_candidates": [{"observation": "我买了苹果。"}]})
        analysis = analyze_observation(model, "我买了苹果", source_content="我买了苹果")
        self.assertEqual(analysis.episode_candidates[0].observation, "我买了苹果")
        self.assertEqual(len(model.calls), 1)


if __name__ == "__main__":
    unittest.main()
