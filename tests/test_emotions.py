"""Emotion is a grounded, expiring interaction hint, never durable memory."""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from api.app import create_app
from cognitive_memory import Memory
from cognitive_memory.architecture_models import EmotionAssessment, ObservationAnalysis
from cognitive_memory.profile import UserProfile
from conversation_agent import ConversationAgent
from conversation_agent.emotions import EMOJIS, EMOTION_TTL
from conversation_agent.prompts import DIALOGUE_PROMPT, OBSERVATION_ANALYSIS_PROMPT
from tests.test_conversation_agent import LocalModel, candidate


class EmotionTests(unittest.TestCase):
    def setUp(self):
        self.memory = Memory(":memory:")
        self.addCleanup(self.memory.close)
        self.model = LocalModel()
        self.agent = ConversationAgent(self.memory, ":memory:", model=self.model)
        self.addCleanup(self.agent.close)
        self.now = 1000.
        self.agent._emotion_clock = lambda: self.now

    def assessment(self, label="happy", confidence=.92, text="我今天真开心", self_state=True):
        self.model.extraction = {"emotion": {"label": label, "confidence": confidence,
            "is_user_state": self_state, "evidence_text": text}}

    def chat(self, message="我今天真开心", **kwargs):
        return self.agent.chat("alice", "one", message, **kwargs)

    def test_all_eight_states_and_one_shared_analysis_call(self):
        for index, (label, emoji) in enumerate(EMOJIS.items()):
            with self.subTest(label=label):
                self.assessment(label=label)
                result = self.agent.chat("alice", f"state-{index}", "我今天真开心")
                self.assertEqual(result["emotion"]["label"], label)
                self.assertEqual(result["emotion"]["emoji"], emoji)
                self.assertEqual(result["emotion"]["confidence"], .92)
        self.assertEqual(len(self.model.extraction_calls), 8)
        self.assertEqual(len(self.model.calls), 8)

    def test_default_and_low_confidence_maintain_then_expire(self):
        self.assessment(confidence=.5)
        self.assertEqual(self.chat()["emotion"]["label"], "neutral")
        self.assessment()
        self.assertEqual(self.chat()["emotion"]["label"], "happy")
        self.now += 100
        self.assessment("sad", .6, "我可能有些低落")
        uncertain = self.chat("我可能有些低落")["emotion"]
        self.assertEqual(uncertain["label"], "happy")
        self.assertEqual(uncertain["ttl_seconds"], EMOTION_TTL - 100)
        self.now += EMOTION_TTL
        self.assertEqual(self.chat("我可能有些低落")["emotion"]["label"], "neutral")

    def test_quotes_hypotheticals_negation_and_other_people_do_not_switch(self):
        for text in ('他说“我今天真开心”', "如果我很焦虑怎么办", "他很难过", "我不难过", "翻译：我很开心"):
            with self.subTest(text=text):
                self.assessment("sad", .99, text, self_state=False)
                self.assertEqual(self.chat(text)["emotion"]["label"], "neutral")
        for phrase in ("引用", "假设", "他人", "否定", "不做关键词匹配", "不是用户性格"):
            self.assertIn(phrase, OBSERVATION_ANALYSIS_PROMPT + DIALOGUE_PROMPT)

    def test_invented_or_history_only_emotion_evidence_is_rejected(self):
        self.assessment(text="我今天真开心")
        result = self.chat("请介绍 Python")
        self.assertEqual(result["emotion"]["label"], "neutral")
        self.model.extraction = {}
        self.chat("我今天真开心")
        self.assessment("sad", .99, "我昨天难过")
        self.assertEqual(self.chat("现在请写代码")["emotion"]["label"], "neutral")

    def test_auto_remember_off_still_detects_but_drops_all_memory_candidates(self):
        self.assessment("tired", text="我有点累了")
        self.model.extraction["semantic_candidates"] = [candidate("我有点累了")]
        result = self.chat("我有点累了", auto_remember=False)
        self.assertEqual(result["emotion"]["emoji"], "😴")
        self.assertEqual(result["memory_status"], "disabled")
        self.assertEqual(UserProfile.read(self.memory, "alice").items, [])
        self.assertEqual(self.memory.architecture.repo.rows("semantic_assertions", "alice"), [])
        self.assertEqual(self.memory.architecture.repo.rows("episode_events", "alice"), [])
        self.assertIn("本次仅判断 emotion", self.model.extraction_calls[0][0].content)

    def test_emotion_topic_is_not_a_personality_memory(self):
        self.assessment()
        self.model.extraction["semantic_candidates"] = [{**candidate("我今天真开心"), "predicate": "current_mood", "value": "happy"}]
        self.assertEqual(self.chat()["emotion"]["label"], "happy")
        self.assertEqual(UserProfile.read(self.memory, "alice").items, [])
        self.assertEqual(self.memory.architecture.repo.rows("semantic_assertions", "alice"), [])

    def test_users_threads_tasks_are_isolated(self):
        self.assessment()
        self.chat()
        self.model.extraction = {}
        self.assertEqual(self.agent.chat("bob", "one", "你好")["emotion"]["label"], "neutral")
        self.assertEqual(self.agent.chat("alice", "two", "你好")["emotion"]["label"], "neutral")
        self.assertEqual(self.chat("你好")["emotion"]["label"], "happy")
        self.assertEqual(self.chat("你好", task_id="new-task")["emotion"]["label"], "neutral")

    def test_failure_preserves_reply_and_existing_emotion(self):
        self.assessment()
        self.chat()
        self.model.fail_extraction = True
        result = self.chat("请继续", auto_remember=False)
        self.assertIn("回答", result["answer"])
        self.assertEqual(result["emotion"]["label"], "happy")
        self.assertEqual(result["memory_status"], "disabled")
        self.assertEqual(result["warnings"], [])
        self.now += EMOTION_TTL + 1
        self.assertEqual(self.chat("请继续", auto_remember=False)["emotion"]["label"], "neutral")

    def test_invalid_assessment_does_not_discard_valid_memory_analysis(self):
        self.model.extraction = {"emotion": {"label": "invalid", "confidence": 2},
            "semantic_candidates": [candidate("我喜欢 Python")]}
        result = self.chat("我喜欢 Python")
        self.assertEqual(result["emotion"]["label"], "neutral")
        self.assertEqual(result["memory_results"][0]["status"], "succeeded")
        self.assertEqual(result["warnings"], [])

    def test_emotion_never_enters_snapshots_pending_writes_or_memory_receipts(self):
        self.assessment("anxious", text="我现在有些紧张")
        result = self.chat("我现在有些紧张")
        self.assertEqual(result["emotion"]["label"], "anxious")
        config = self.agent._config("alice", "one")
        for snapshot in self.agent.checkpointer.list(config):
            self.assertNotIn("emotion", snapshot.checkpoint["channel_values"])
            self.assertNotIn("anxious", str(snapshot.metadata))
            self.assertFalse(any(channel == "emotion" for _, channel, _ in (snapshot.pending_writes or [])))
        for table in ("checkpoints", "writes"):
            rows = self.agent._conn.execute(f"SELECT * FROM {table}").fetchall()
            self.assertNotIn(b"anxious", b"".join(value for row in rows for value in row if isinstance(value, bytes)))
        session = self.agent.get_session("alice", "one")
        self.assertNotIn("emotion", session)
        self.assertNotIn("emotion", str(self.memory.architecture.repo.rows("learning_operations", "alice")))
        self.assertNotIn("emotion", str(self.memory.architecture.working_state("alice", "one", "one").model_dump()))

    def test_no_persist_is_fully_ephemeral_and_does_not_change_existing_emotion(self):
        self.assessment()
        self.chat()
        counts = [self.agent._conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("checkpoints", "writes", "conversation_threads")]
        memory_changes = self.memory.storage._conn.total_changes
        self.assessment("sad", text="我现在很低落")
        result = self.chat("我现在很低落", retention_policy="no_persist")
        self.assertEqual(result["emotion"]["emoji"], "😔")
        self.assertEqual(result["working_state"], None)
        self.assertEqual(memory_changes, self.memory.storage._conn.total_changes)
        self.assertEqual(counts, [self.agent._conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("checkpoints", "writes", "conversation_threads")])
        self.model.extraction = {}
        self.assertEqual(self.chat("继续")["emotion"]["label"], "happy")

    def test_analysis_schema_exposes_emotion_but_serialization_excludes_it(self):
        analysis = ObservationAnalysis(emotion=EmotionAssessment(label="happy", confidence=.92))
        self.assertIn("emotion", ObservationAnalysis.model_json_schema()["properties"])
        self.assertNotIn("emotion", analysis.model_dump())
        self.assertNotIn("emotion", json.loads(analysis.model_dump_json()))

    def test_recent_context_and_tone_are_supplied_without_extra_model(self):
        self.assessment("tired", text="我今天累坏了")
        self.chat("我今天累坏了")
        payload = json.loads(self.model.calls[-1][0].content[len(DIALOGUE_PROMPT):])
        self.assertEqual(payload["current_emotion"]["label"], "tired")
        self.model.extraction = {}
        self.chat("好多了，请继续")
        self.assertIn("我今天累坏了", self.model.extraction_calls[-1][1].content)
        self.assertEqual(len(self.model.extraction_calls), 2)
        self.assertEqual(len(self.model.calls), 2)

    def test_delete_and_restart_clear_emotion(self):
        self.assessment()
        self.chat()
        self.agent.delete_session("alice", "one")
        self.model.extraction = {}
        self.assertEqual(self.chat("你好")["emotion"]["label"], "neutral")

    def test_restart_restores_chat_but_not_emotion(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "sessions.db"
            first = ConversationAgent(self.memory, path, model=self.model)
            self.assessment("happy", text="我今天真开心")
            try:
                self.assertEqual(first.chat("alice", "restart", "我今天真开心")["emotion"]["label"], "happy")
            finally:
                first.close()
            self.model.extraction = {}
            second = ConversationAgent(self.memory, path, model=self.model)
            try:
                result = second.chat("alice", "restart", "你好", auto_remember=False)
                self.assertEqual(result["emotion"]["label"], "neutral")
                self.assertEqual(len(second.get_session("alice", "restart")["messages"]), 4)
            finally:
                second.close()

    def test_chat_and_session_expose_live_emotion_without_persisting_it(self):
        self.assessment()
        with TestClient(create_app(service=self.memory, chat_model=self.model)) as client:
            result = client.post("/api/chat", json={"user_id": "alice", "thread_id": "api", "message": "我今天真开心", "auto_remember": False})
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(result.json()["emotion"]["emoji"], "😄")
            restored = client.get("/api/sessions/api?user_id=alice").json()
            self.assertNotIn("emotion", restored)
            self.assertEqual(restored["current_emotion"]["label"], "happy")
