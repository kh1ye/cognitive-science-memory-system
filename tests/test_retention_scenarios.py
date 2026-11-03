"""Replay diverse timed examples through the actual admission and evidence paths."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from cognitive_memory import Memory
from scripts.seed_retention_demo import CASES, DEMO_USER, seed_examples, simulated_clock

NOW = datetime(2026, 11, 4, tzinfo=timezone.utc)


class RetentionScenarioTests(unittest.TestCase):
    def setUp(self):
        self.memory = Memory()
        self.addCleanup(self.memory.close)
        seed_examples(self.memory, reference_time=NOW)
        self.records = {m["metadata"]["fixture_case_id"]: m for m in self.memory.list_memories(DEMO_USER, True)}

    def states(self):
        return {key: self.memory.retention.state(row, NOW) for key, row in self.records.items()}

    def test_all_examples_are_real_independent_records_with_real_evidence_counts(self):
        self.assertEqual(len(self.records), len(CASES))
        for case in CASES:
            with self.subTest(case=case["id"]):
                row = self.records[case["id"]]
                expected_count = case.get("evidence_count", 1)
                self.assertEqual(row["evidence_count"], expected_count)
                self.assertEqual(self.memory.evidence(DEMO_USER, row["id"])["total_count"], expected_count)
                self.assertTrue(row["metadata"]["synthetic"])
                self.assertAlmostEqual(self.memory.retention.state(row, NOW)["elapsed_days"], case["age_days"])
        self.assertEqual(self.records["working-noise-old"]["state_role"], "working")

    def test_unconfirmed_aging_is_monotonic_and_importance_changes_stability(self):
        states = self.states()
        order = ["fresh", "age-1", "age-7", "age-15", "age-30", "age-60", "age-120"]
        values = [states[key]["retention_probability"] for key in order]
        self.assertEqual(values, sorted(values, reverse=True))
        self.assertAlmostEqual(states["age-30"]["retention_probability"], .22313016014842982)
        self.assertGreater(states["importance-medium"]["retention_probability"], states["importance-low"]["retention_probability"])

    def test_repeated_independent_confirmations_preserve_old_records_longer(self):
        states = self.states()
        values = [states[key]["retention_probability"] for key in ["age-30", "evidence-2", "evidence-4", "evidence-7"]]
        self.assertEqual(values, sorted(values))
        self.assertAlmostEqual(states["evidence-4"]["stability_days"], 80)
        self.assertAlmostEqual(states["evidence-4"]["retention_probability"], .6872892787909722)
        recent = states["recent-confirmation"]
        self.assertGreater(recent["retention_probability"], .95)
        self.assertEqual(self.records["recent-confirmation"]["created_at"], (NOW - timedelta(days=180)).isoformat(timespec="seconds"))

    def test_archive_matches_preview_and_keeps_protected_records_sources_and_counts(self):
        memory = self.memory
        before = memory.list_memories(DEMO_USER, True)
        evidence = {r["id"]: memory.evidence(DEMO_USER, r["id"]) for r in before}
        with simulated_clock(NOW):
            preview = memory.retention.overview(DEMO_USER, 1000)
        expected = {m["id"] for m in preview["items"] if m["archive_eligible"]}
        archived = memory.run_retention(DEMO_USER, NOW)
        self.assertTrue(expected)
        self.assertEqual(set(archived["archived_ids"]), expected)
        self.assertEqual(len(memory.list_memories(DEMO_USER, True)), len(before))
        for row in before:
            current = memory.storage.get_memory(row["id"])
            self.assertEqual(current["content"], row["content"])
            self.assertEqual(memory.evidence(DEMO_USER, row["id"]), evidence[row["id"]])
            if memory.retention.is_protected(row):
                self.assertNotEqual(current["state_role"], "archived")
        self.assertEqual(memory.run_retention(DEMO_USER, NOW)["archived_ids"], [])

    def test_old_important_memory_stays_retrievable_after_decay_and_archiving(self):
        self.memory.run_retention(DEMO_USER, NOW)
        record = self.records["protected-procedure"]
        result = self.memory.search(DEMO_USER, "发布流程", 20)
        found = next(m for m in result["results"] if m["id"] == record["id"])
        self.assertGreater(found["retrieval"]["score"], 0)
        self.assertGreaterEqual(found["retrieval"]["retention_factor"], .85)

    def test_seeding_is_idempotent_even_after_archive_and_does_not_move_old_clocks(self):
        self.memory.run_retention(DEMO_USER, NOW)
        before = self.memory.list_memories(DEMO_USER, True)
        evidence = {m["id"]: self.memory.evidence(DEMO_USER, m["id"]) for m in before}
        result = seed_examples(self.memory, reference_time=NOW + timedelta(days=30))
        self.assertEqual(result["created_cases"], [])
        self.assertEqual(self.memory.list_memories(DEMO_USER, True), before)
        self.assertEqual({m["id"]: self.memory.evidence(DEMO_USER, m["id"]) for m in before}, evidence)

    def test_demo_refuses_real_user_namespaces(self):
        with self.assertRaisesRegex(ValueError, "专用测试空间"):
            seed_examples(self.memory, user="alice", reference_time=NOW)
        self.assertEqual(self.memory.list_memories("alice", True), [])

    def test_examples_and_switch_survive_reopening_typed_database(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "retention.db"
            with Memory(path) as memory:
                seed_examples(memory, reference_time=NOW)
                memory.retention.set_enabled(DEMO_USER, False)
                before = memory.list_memories(DEMO_USER, True)
            with Memory(path) as reopened:
                self.assertEqual(reopened.list_memories(DEMO_USER, True), before)
                self.assertFalse(reopened.retention.is_enabled(DEMO_USER))
                self.assertEqual(reopened.run_retention(DEMO_USER, NOW)["archived_ids"], [])
                reopened.retention.set_enabled(DEMO_USER, True)
                self.assertTrue(reopened.run_retention(DEMO_USER, NOW)["archived_ids"])


if __name__ == "__main__":
    unittest.main()
