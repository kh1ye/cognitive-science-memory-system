"""Offline tests for run usage aggregation and cost estimation."""

import os
import unittest
from unittest import mock

from api.evaluation_center import usage_summary


def call(input_tokens, output_tokens):
    return {"usage": {"input_tokens": input_tokens, "output_tokens": output_tokens}}


class UsageSummaryTests(unittest.TestCase):
    def test_aggregates_provider_calls_and_judge_usage(self):
        result = {"provider_calls": [call(100, 10), call(200, 20), {"usage": None}]}
        scores = {"judge_usage": {"input_tokens": 50, "output_tokens": 5}}
        with mock.patch.dict(os.environ, {"EVAL_PRICE_INPUT_CNY_PER_MTOK": "2", "EVAL_PRICE_OUTPUT_CNY_PER_MTOK": "8"}):
            summary = usage_summary(result, scores)
        self.assertEqual(summary["input_tokens"], 350)
        self.assertEqual(summary["output_tokens"], 35)
        self.assertEqual(summary["calls"], 3)
        # 350e-6*2 + 35e-6*8 = 0.0007 + 0.00028 = 0.00098 -> 0.0 at 2 decimals
        self.assertEqual(summary["cost_cny"], 0.0)

    def test_cost_uses_env_prices_at_million_scale(self):
        result = {"provider_calls": [call(1_000_000, 100_000)]}
        with mock.patch.dict(os.environ, {"EVAL_PRICE_INPUT_CNY_PER_MTOK": "2", "EVAL_PRICE_OUTPUT_CNY_PER_MTOK": "8"}):
            summary = usage_summary(result, {})
        self.assertEqual(summary["cost_cny"], 2.8)

    def test_returns_none_when_nothing_recorded(self):
        self.assertIsNone(usage_summary({}, {}))
        self.assertIsNone(usage_summary(None, None))


if __name__ == "__main__":
    unittest.main()
