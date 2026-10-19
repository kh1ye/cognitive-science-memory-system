import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.app import create_app
from conversation_agent.llm import LLMSettings
from conversation_agent.state import MemoryCandidate, MemoryExtraction


class EvolutionTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app(":memory:", demo_token=""))
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def write(self, content, **values):
        response = self.client.post("/api/evolution", json={
            "user_id": "evolution-user", "content": content,
            "memory_key": "drink_preference", "memory_value": "咖啡",
            "tags": ["preference"], **values,
        })
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_write_returns_real_record_and_only_request_events(self):
        self.client.post("/api/memories", json={"content": "其他用户的记忆"})
        trace = self.write("我平时最喜欢喝咖啡。")
        self.assertEqual(trace["result"]["decision"], "WRITE_CURRENT")
        record = trace["result"]["memory"]
        records = self.client.get("/api/memories?user_id=evolution-user").json()["items"]
        self.assertEqual(records, [record])
        self.assertEqual([event["event_type"] for event in trace["events"]], ["WRITE_CURRENT"])
        self.assertEqual(trace["events"][0]["memory_id"], record["id"])
        fields = {field["label"]: field["value"] for field in trace["steps"][1]["fields"]}
        self.assertEqual(fields["写入分数"], round(record["write_score"], 4))
        self.assertIsNone(trace["previous"])

    def test_conflict_and_consolidation_preserve_existing_rules(self):
        first = self.write("我平时最喜欢喝咖啡。")
        candidate = self.write("我现在改成最喜欢喝茶了。", memory_value="茶")
        self.assertEqual(candidate["result"]["decision"], "CANDIDATE")
        self.assertEqual(candidate["previous"]["id"], first["result"]["memory"]["id"])
        consolidated = self.write("确认一下，我目前最喜欢的饮品是茶。", memory_value="茶")
        self.assertEqual(consolidated["result"]["decision"], "CONSOLIDATED")
        self.assertEqual(consolidated["result"]["memory"]["evidence_count"], 2)
        self.assertEqual([event["event_type"] for event in consolidated["events"]], ["CANDIDATE", "CONSOLIDATE"])
        self.assertEqual(consolidated["previous"]["state_role"], "current")
        records = self.client.get("/api/memories?user_id=evolution-user&include_archived=true").json()["items"]
        old = next(record for record in records if record["id"] == first["result"]["memory"]["id"])
        self.assertEqual(old["state_role"], "history")

    def test_exact_duplicate_skips_scoring_and_does_not_duplicate_records(self):
        self.write("我喜欢咖啡。")
        trace = self.write("我喜欢咖啡。")
        self.assertEqual(trace["result"]["decision"], "REINFORCED")
        self.assertEqual(trace["steps"][1]["status"], "skipped")
        self.assertEqual(trace["steps"][1]["fields"], [])
        self.assertEqual(trace["previous"]["evidence_count"], 1)
        self.assertEqual(trace["result"]["memory"]["evidence_count"], 2)
        self.assertEqual(len(self.client.get("/api/memories?user_id=evolution-user").json()["items"]), 1)

    def test_privacy_gate_blocks_body_and_only_returns_privacy_event(self):
        for values in ({"content": "不要记住这条信息"}, {"content": "私人信息", "tags": ["sensitive"]}):
            trace = self.write(**values)
            self.assertEqual(trace["result"]["decision"], "DROP")
            self.assertIsNone(trace["result"]["memory"])
            self.assertEqual(trace["steps"][1]["status"], "blocked")
            self.assertEqual(trace["steps"][2]["status"], "skipped")
            self.assertEqual([event["event_type"] for event in trace["events"]], ["DROP_PRIVACY"])
        self.assertEqual(self.client.get("/api/memories?user_id=evolution-user").json()["items"], [])

    def test_same_value_reinforcement_reports_this_runs_scores_not_old_record_scores(self):
        first = self.write("我平时喜欢咖啡。")
        trace = self.write("我的饮品偏好还是咖啡。", importance=0.9, confidence=0.9)
        self.assertEqual(trace["result"]["reason"], "same_key_value")
        fields = {field["label"]: field["value"] for field in trace["steps"][1]["fields"]}
        self.assertGreater(fields["写入分数"], first["result"]["memory"]["write_score"])
        self.assertEqual(trace["result"]["memory"]["write_score"], first["result"]["memory"]["write_score"])

    def test_low_score_stays_in_persistent_working_layer(self):
        trace = self.write("临时内容", tags=["noise"], importance=0.1, confidence=0.2)
        self.assertEqual(trace["result"]["decision"], "KEEP_SESSION_ONLY")
        self.assertEqual(trace["result"]["memory"]["state_role"], "working")
        self.assertEqual(trace["steps"][2]["status"], "skipped")
        self.assertEqual(len(self.client.get("/api/memories?user_id=evolution-user").json()["items"]), 1)

    def test_invalid_input_does_not_write(self):
        response = self.client.post("/api/evolution", json={"content": " "})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get("/api/memories").json()["items"], [])

    def test_other_user_is_not_used_for_comparison(self):
        self.write("我喜欢咖啡。")
        trace = self.write("我喜欢茶。", user_id="another-user", memory_value="茶")
        self.assertEqual(trace["result"]["decision"], "WRITE_CURRENT")
        self.assertIsNone(trace["previous"])


class NaturalEvolutionTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app(":memory:", demo_token=""))
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.agent = self.client.app.state.conversation_agent
        self.agent.settings = LLMSettings(api_key="")

    def analyze(self, content, **values):
        return self.client.post("/api/evolution/analyze", json={
            "content": content, "user_id": "natural-user", **values,
        })

    def records(self):
        return self.client.get("/api/memories?user_id=natural-user&include_archived=true").json()["items"]

    def test_one_input_extracts_encodes_and_stores_without_manual_parameters(self):
        response = self.analyze("我喜欢喝茶。")
        self.assertEqual(response.status_code, 201)
        report = response.json()
        self.assertEqual(report["extraction"]["method"], "local_rules")
        self.assertEqual(report["extraction"]["candidates"][0]["memory_value"], "茶")
        self.assertEqual(len(report["traces"]), 1)
        self.assertEqual(report["traces"][0]["result"]["decision"], "WRITE_CURRENT")
        self.assertEqual(self.records()[0]["id"], report["traces"][0]["result"]["memory"]["id"])

    def test_one_conflict_does_not_generate_extra_evidence(self):
        self.analyze("我喜欢喝咖啡。")
        report = self.analyze("我现在更喜欢喝茶。").json()
        trace = report["traces"][0]
        self.assertEqual(trace["result"]["decision"], "CANDIDATE")
        self.assertEqual(trace["result"]["gate"]["evidence_count"], 1)
        self.assertEqual(trace["previous"]["memory_value"], "咖啡")
        self.assertEqual(len(self.records()), 2)
        self.assertEqual(sum(record["state_role"] == "current" for record in self.records()), 1)

    def test_separate_real_input_can_consolidate(self):
        self.analyze("我喜欢喝咖啡。")
        self.analyze("我现在更喜欢喝茶。")
        report = self.analyze("我目前最喜欢喝茶。").json()
        self.assertEqual(report["traces"][0]["result"]["decision"], "CONSOLIDATED")
        self.assertEqual(report["traces"][0]["result"]["memory"]["evidence_count"], 2)

    def test_unrecognized_quoted_hypothetical_or_question_does_not_write(self):
        for content in ("今天天气怎么样？", "假如我喜欢喝茶。", "他说我喜欢喝茶。", "我喜欢喝茶？", "我不喜欢喝茶。"):
            with self.subTest(content=content):
                report = self.analyze(content).json()
                self.assertEqual(report["outcome"], "no_new_memory")
                self.assertEqual(report["traces"], [])
        self.assertEqual(self.records(), [])

    def test_privacy_stops_before_model_call(self):
        self.agent._model = object()
        with patch("api.routers.evolution.extract_memories") as extract:
            report = self.analyze("不要记住，我喜欢喝茶。").json()
        extract.assert_not_called()
        self.assertEqual(report["outcome"], "privacy_blocked")
        self.assertEqual(report["traces"][0]["result"]["decision"], "DROP")
        self.assertEqual(self.records(), [])

    def test_model_extraction_uses_evidence_and_rejects_invented_candidates(self):
        self.agent._model = object()
        extraction = MemoryExtraction(memories=[
            MemoryCandidate(content="我喜欢用 Python。", memory_key="preferred_programming_language", memory_value="Python", tags=["preference"]),
            MemoryCandidate(content="我住在北京", memory_key="city", memory_value="北京"),
        ])
        with patch("api.routers.evolution.extract_memories", return_value=extraction) as extract:
            report = self.analyze("我喜欢用Python").json()
        extract.assert_called_once()
        self.assertEqual(report["extraction"]["method"], "model")
        self.assertEqual(report["extraction"]["rejected_count"], 1)
        self.assertEqual(len(report["traces"]), 1)
        self.assertEqual(self.records()[0]["content"], "我喜欢用Python")

    def test_sensitive_candidate_does_not_get_automatic_consent(self):
        self.agent._model = object()
        extraction = MemoryExtraction(memories=[MemoryCandidate(content="我的私人健康信息", sensitive=True)])
        with patch("api.routers.evolution.extract_memories", return_value=extraction):
            report = self.analyze("我的私人健康信息").json()
        self.assertEqual(report["traces"][0]["result"]["reason"], "consent_required")
        self.assertEqual(self.records(), [])

    def test_failed_model_does_not_write_or_expose_provider_details(self):
        self.agent._model = object()
        with patch("api.routers.evolution.extract_memories", side_effect=RuntimeError("secret-provider-detail")):
            response = self.analyze("我喜欢喝茶。")
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("secret-provider-detail", response.text)
        self.assertEqual(self.records(), [])

    def test_invalid_input_and_manual_overrides_are_rejected(self):
        for values in ({"content": " "}, {"content": "我喜欢喝茶。", "consent": True}, {"content": "我喜欢喝茶。", "memory_key": "injected"}):
            response = self.client.post("/api/evolution/analyze", json=values)
            self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
