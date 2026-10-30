import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.app import create_app
from api.evaluation_center import EvaluationCenter
from api.routers.evaluations import TaskRequest
from conversation_agent.llm import LLMSettings


class EvaluationCenterTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.center = EvaluationCenter(self.root)
        self.addCleanup(self.center.close)

    def put(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_history_preserves_partial_coverage_and_conditional_efficiency(self):
        folder = "evaluation/Vatsalabench/results/expansion-20261030-120000"
        self.put(folder + "/aggregate.json", {"scored_samples": 1, "planned_samples": 2,
            "quality": {"AFA": {"value": .25, "valid_n": 1, "planned_n": 2}},
            "resource": {"L95_seconds": None, "completed_cohort_only": {"samples": 1, "L95_seconds": 3.0, "ATC_tokens_per_query": 100, "SAF_pooled": 2}}})
        self.put(folder + "/batch.json", {"selected": [{"sample_id": "one"}, {"sample_id": "two"}], "runs": [{"exit_code": 1}]})
        self.put(folder + "/one/results.json", {"sample_id": "one", "requested_model": "test-model", "results": [{"probe_id": "BASE-1", "question": "where?", "answer": "Oslo", "scoring_reference": {"expected": "Oslo"}, "references": []}]})
        self.put(folder + "/one/scores.json", {"manual_audit": {}, "judgment": {"answers": [{"probe_id": "BASE-1", "correct": 1}]}})
        record = self.center.history()[0]
        self.assertEqual(record["status"], "partial")
        self.assertEqual(record["model"], "test-model")
        detail = self.center.detail(record["id"])
        self.assertEqual(detail["metrics"][0]["planned_n"], 2)
        self.assertTrue(detail["efficiency"]["conditional"])
        self.assertEqual(detail["efficiency"]["L95"], 3)
        self.assertEqual(self.center.sample(record["id"], "one")["answers"][0]["gold"]["expected"], "Oslo")
        with self.assertRaises(ValueError):
            self.center.sample(record["id"], "../outside")
        with self.assertRaises(ValueError):
            self.center.detail("../../.env")

    def test_local_check_is_persisted_without_credentials_or_memory_writes(self):
        self.put("evaluation/memory-150/cases.json", {"cases": [{"id": "one"}, {"id": "two"}]})
        app = create_app(":memory:")
        with TestClient(app, client=("127.0.0.1", 50000)) as client:
            app.state.evaluation_center = self.center
            response = client.post("/api/evaluations/tasks", json={"dataset": "memory-150", "mode": "check", "api_key": "ephemeral-test-secret"})
            self.assertEqual(response.status_code, 202, response.text)
            jid = response.json()["id"]
            for _ in range(100):
                job = client.get(f"/api/evaluations/tasks/{jid}").json()
                if job["status"] not in ("queued", "running"):
                    break
                time.sleep(.01)
            self.assertEqual(job["status"], "completed")
            saved = list(self.root.rglob("job.json"))[0].read_text(encoding="utf-8")
            self.assertNotIn("ephemeral-test-secret", saved)
            self.assertNotIn("api_key", saved)
            self.assertEqual(app.state.memory.catalog.list("demo-user"), [])
            runs = client.get("/api/evaluations/runs?dataset=memory-150").json()["items"]
            self.assertEqual(runs[0]["kind"], "check")

    def test_remote_clients_cannot_launch_processes(self):
        with TestClient(create_app(":memory:"), client=("192.0.2.7", 50000)) as client:
            response = client.post("/api/evaluations/tasks", json={"dataset": "vatsalabench", "mode": "check"})
            self.assertEqual(response.status_code, 403)

    def test_server_key_cannot_be_forwarded_to_a_different_provider(self):
        settings = LLMSettings(model="model", api_key="server-secret", base_url="https://original.example")
        with patch("api.evaluation_center.LLMSettings.from_env", return_value=settings):
            with self.assertRaisesRegex(ValueError, "地址"):
                self.center.start(TaskRequest(dataset="vatsalabench", mode="full", base_url="https://different.example"))
        self.assertEqual(self.center.jobs, {})


if __name__ == "__main__":
    unittest.main()
