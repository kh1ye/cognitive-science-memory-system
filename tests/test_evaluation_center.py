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

    def test_uploaded_dataset_runs_into_history_with_mocked_model(self):
        from types import SimpleNamespace

        app = create_app(":memory:")
        settings = LLMSettings(model="mock-classifier", api_key="test-secret")
        prediction = SimpleNamespace(label="semantic", reason="mocked")
        with TestClient(app, client=("127.0.0.1", 50000)) as client:
            app.state.evaluation_center = self.center
            response = client.post("/api/evaluations/uploads", json={"name": "custom.json", "content": json.dumps([
                {"text": "I like tea", "expected": "semantic"},
                {"text": "I walked yesterday", "expected": "episodic"},
            ])})
            self.assertEqual(response.status_code, 201, response.text)
            identifier = response.json()["id"]
            info = next(item for item in client.get("/api/evaluations/datasets").json()["items"] if item["id"] == identifier)
            self.assertEqual(info["source"], "upload")
            self.assertEqual(info["modes"], ["classify"])
            self.assertEqual(info["count"], 2)
            self.assertEqual(client.get("/api/evaluations/runs", params={"dataset": identifier}).json()["items"], [])

            with patch("api.routers.evaluations.LLMSettings.from_env", return_value=settings), \
                    patch.object(LLMSettings, "create_model", return_value=object()), \
                    patch("conversation_agent.memory_concepts.classify_memory_concept",
                          side_effect=[(prediction, {}), RuntimeError("mock failure")]) as classify:
                response = client.post(f"/api/evaluations/uploads/{identifier}/run")
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(classify.call_count, 2)
            report = response.json()
            self.assertEqual(report["planned"], 2)
            self.assertEqual(report["failed"], 1)
            self.assertEqual(report["accuracy"], .5)
            self.assertTrue(report["created_at"])
            self.assertEqual([row["id"] for row in report["results"]], ["case-1", "case-2"])

            runs = client.get("/api/evaluations/runs", params={"dataset": identifier}).json()["items"]
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0]["id"], report["id"])
            self.assertEqual(runs[0]["kind"], "classification")
            self.assertEqual(runs[0]["status"], "partial")
            self.assertEqual((runs[0]["completed"], runs[0]["planned"]), (1, 2))
            detail = client.get(f"/api/evaluations/runs/{report['id']}").json()
            self.assertEqual(detail["metrics"][0]["key"], "Accuracy")
            self.assertEqual(detail["metrics"][0]["value"], .5)
            self.assertEqual(detail["model"], "mock-classifier")
            self.assertNotIn("results", detail["config"])
            predictions = client.get(f"/api/evaluations/runs/{report['id']}/predictions").json()["items"]
            self.assertEqual([row["id"] for row in predictions], ["case-1", "case-2"])
            self.assertEqual(predictions[1]["error"], "模型调用失败")

            rejected = client.post("/api/evaluations/tasks", json={"dataset": identifier, "mode": "check"})
            self.assertEqual(rejected.status_code, 400)
            self.assertEqual(client.post("/api/evaluations/uploads/not-a-uuid/run").status_code, 404)
            self.assertEqual(client.get("/api/evaluations/runs", params={"dataset": "not-a-uuid"}).status_code, 400)

    def test_legacy_uploaded_dataset_and_report_remain_discoverable(self):
        identifier = "a" * 32
        self.put(f"evaluation/uploads/{identifier}/dataset.json", {
            "id": identifier, "name": "legacy.json", "count": 1,
            "cases": [{"text": "I like tea", "expected": "semantic"}],
        })
        self.put(f"evaluation/uploads/{identifier}/results/legacy/report.json", {
            "id": "legacy-report", "dataset": identifier, "model": "legacy-model",
            "planned": 1, "total": 1, "accuracy": 1, "failed": 0,
            "results": [{"text": "I like tea", "expected": "semantic", "actual": "semantic", "correct": True}],
        })
        info = next(item for item in self.center.datasets() if item["id"] == identifier)
        self.assertEqual(info["name"], "legacy.json")
        record = self.center.history(identifier)[0]
        self.assertEqual(record["id"], "legacy-report")
        self.assertEqual(record["status"], "completed")
        detail = self.center.detail(record["id"])
        self.assertEqual(detail["metrics"][0]["value"], 1)
        self.assertNotIn("results", detail["config"])
        self.assertEqual(self.center.flat_predictions(record["id"])[0]["id"], "case-1")


if __name__ == "__main__":
    unittest.main()
