import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.vatsalabench_score import quality_metrics, resource_metrics, aggregate


class VatsalaMetricsTests(unittest.TestCase):
    def judgment(self, initial=1):
        ids = ["BASE-1", "BASE-2", "BASE-3", "UMRR-1", "R1R2", "RET-10", "RET-30", "RET-50", "CUR-H2", "CON-U", "CON-P", "CON-N"]
        return {"answers": [{"probe_id": key, "correct": initial if key == "BASE-1" else int(key != "RET-30")} for key in ids],
            "fsrc_pairs": [{"match": 1}, {"match": 0}, {"match": 0}],
            "tic_slots": [{"covered": 1}, {"covered": 0}],
            "afp_units": [{"relevant": 1}, {"relevant": 1}, {"relevant": 0}]}

    def test_quality_uses_document_formulas(self):
        result = quality_metrics(self.judgment())
        self.assertEqual(result["CR-AUC"], .5)  # (1 + 2*0 + 1)/4; D0 excluded.
        self.assertAlmostEqual(result["FSRC"], 1/3)
        self.assertEqual(result["TIC"], .5)
        self.assertAlmostEqual(result["AFP"], 2/3)

    def test_initial_failure_is_not_zero_retention(self):
        self.assertIsNone(quality_metrics(self.judgment(initial=0))["CR-AUC"])

    def test_consistency_and_coverage_are_not_accuracy(self):
        judgment = self.judgment(initial=0)
        # An equal wrong conclusion can be consistent; wrong slot values can cover intent.
        result = quality_metrics(judgment)
        self.assertEqual(result["AFA"], 0)
        self.assertGreater(result["FSRC"], 0)
        self.assertEqual(result["TIC"], .5)

    def test_empty_answer_focus_is_zero(self):
        judgment = self.judgment()
        judgment["afp_units"] = []
        self.assertEqual(quality_metrics(judgment)["AFP"], 0)

    def test_resources_include_build_recovery_but_not_judge_or_double_cache(self):
        run = {"resource": {"planned_queries": 3, "queries": [{"seconds": n} for n in (1, 3, 2)],
            "empty_storage_bytes": 100, "built_storage_bytes": 500, "history_bytes": 200},
            "provider_calls": [{"phase": phase, "usage": {"input_tokens": 100, "output_tokens": 20,
                "input_token_details": {"cache_read": 50}}} for phase in ("resource_build", "resource_build", "resource_query", "judge")]}
        result = resource_metrics(run)
        self.assertEqual(result["ATC"], 120)  # 3 actual calls *120 /3 planned queries.
        self.assertEqual(result["SAF"], 2)
        self.assertEqual(result["L95_seconds"], 3)
        run["provider_calls"].append({"phase": "resource_build", "usage": None})
        result = resource_metrics(run)
        self.assertIsNone(result["ATC"])
        self.assertEqual(result["ATC_known_usage_lower_bound"], 120)

    def test_incomplete_sample_stays_in_planned_coverage(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "done").mkdir()
            (root / "batch.json").write_text(json.dumps({"selected": [{"sample_id": "done"}, {"sample_id": "failed"}]}))
            resource = {"planned_queries": 3, "completed_queries": 3, "latencies_seconds": [1, 2, 3],
                "ATC": 60, "ATC_known_usage_lower_bound": 60, "SAF": 2,
                "built_storage_bytes": 500, "empty_storage_bytes": 100, "history_bytes": 200}
            (root / "done" / "scores.json").write_text(json.dumps({"quality": quality_metrics(self.judgment()), "resource": resource}))
            result = aggregate(root)
            self.assertEqual(result["quality"]["AFA"]["valid_n"], 1)
            self.assertEqual(result["quality"]["AFA"]["planned_n"], 2)
            self.assertIsNone(result["resource"]["L95_seconds"])
            self.assertEqual(result["resource"]["completed_cohort_only"]["L95_seconds"], 3)
            self.assertEqual(result["resource"]["ATC_known_lower_bound"], 30)


if __name__ == "__main__":
    unittest.main()
