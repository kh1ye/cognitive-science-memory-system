"""Regression cases from the project audit, using isolated stores only."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from fastapi.testclient import TestClient
from api.app import create_app
from cognitive_memory import Memory
from conversation_agent.memory import CognitiveMemory
from conversation_agent.state import MemoryCandidate, MemoryExtraction


class OptimizationTests(unittest.TestCase):
    def write(self, memory, text, value, key="python_version", **extra):
        return memory.add_memory({"user_id":"alice", "content":text, "memory_key":key,
                                  "memory_value":value, "tags":["preference"], **extra})

    def test_similar_values_stay_pending_then_consolidate_with_real_confirmation(self):
        with Memory() as memory:
            self.write(memory,"项目采用 Python 3.11","Python 3.11")
            result=self.write(memory,"项目现在采用 Python 3.12","Python 3.12")
            self.assertEqual(result["decision"],"CANDIDATE")
            self.assertLess(result["gate"]["cpe"],memory.config.cpe_low_threshold)
            self.assertTrue(result["gate"]["explicit_value_change"])
            self.assertEqual(sum(r["state_role"]=="current" for r in memory.list_memories("alice")),1)
            confirmed=self.write(memory,"确认项目采用 Python 3.12","Python 3.12")
            self.assertEqual(confirmed["decision"],"CONSOLIDATED")
            self.assertEqual([r["memory_value"] for r in memory.list_memories("alice") if r["state_role"]=="current"],["Python 3.12"])
            self.assertEqual(memory.evidence("alice",confirmed["memory"]["id"])["total_count"],2)

    def test_old_statement_is_reconsidered_instead_of_reinforcing_history(self):
        with Memory() as memory:
            for text,value in [("我喜欢喝茶。","茶"),("我现在喜欢喝咖啡。","咖啡"),("我目前最喜欢喝咖啡。","咖啡")]:
                self.write(memory,text,value,"preferred_beverage")
            result=self.write(memory,"我喜欢喝茶。","茶","preferred_beverage")
            self.assertEqual(result["decision"],"CANDIDATE")
            self.assertEqual(result["memory"]["state_role"],"candidate")
            result=self.write(memory,"现在确认喜欢茶。","茶","preferred_beverage")
            self.assertEqual(result["decision"],"CONSOLIDATED")

    def test_replayed_support_message_after_consolidation_does_not_change_current(self):
        with Memory() as memory:
            self.write(memory, "项目采用 Python 3.11", "Python 3.11")
            candidate = {"metadata": {"thread_id": "t", "message_id": "m1"}}
            self.write(memory, "项目现在采用 Python 3.12", "Python 3.12", **candidate)
            current = self.write(memory, "确认项目采用 Python 3.12", "Python 3.12",
                                 metadata={"thread_id": "t", "message_id": "m2"})["memory"]
            audit = memory.list_audit("alice")
            replay = self.write(memory, "项目现在采用 Python 3.12", "Python 3.12", **candidate)
            self.assertEqual(replay["decision"], "UNCHANGED")
            self.assertEqual(replay["memory"]["id"], current["id"])
            self.assertEqual(replay["memory"]["evidence_count"], 2)
            self.assertEqual(memory.evidence("alice", current["id"])["total_count"], 2)
            self.assertEqual(memory.list_audit("alice"), audit)

    def test_ambiguous_topic_input_stays_candidate_without_second_current(self):
        with Memory() as memory:
            self.write(memory, "项目采用 Python", "", key="stack")
            result = self.write(memory, "项目主要采用 Python", "", key="stack")
            self.assertEqual(result["decision"], "CANDIDATE")
            self.assertEqual(result["reason"], "awaiting_clear_topic_value")
            self.assertEqual(result["gate"]["conflict_basis"], "ambiguous_topic_update")
            self.assertEqual(sum(row["state_role"] == "current" for row in memory.list_memories("alice")), 1)

    def test_candidate_only_and_history_only_search_are_labelled_as_reference(self):
        with Memory() as memory:
            self.write(memory,"我喜欢喝茶。","茶","preferred_beverage")
            self.write(memory,"我现在喜欢喝咖啡。","咖啡","preferred_beverage")
            result=memory.search("alice","咖啡")
            self.assertFalse(result["grounded"])
            self.assertTrue(result["has_results"])
            self.assertEqual(result["answer_status"],"reference_only")
            self.assertIn("未确认候选",result["answer"])
            self.write(memory,"再次确认喝咖啡。","咖啡","preferred_beverage")
            old=memory.search("alice","茶")
            self.assertFalse(old["grounded"])
            self.assertIn("历史记录",old["answer"])
            history=memory.search("alice","以前喝茶")
            self.assertTrue(history["grounded"])
            self.assertEqual(history["answer_status"],"confirmed_history")
            self.assertFalse(memory.search("alice","不存在的查询")['has_results'])

    def test_each_reinforcement_keeps_its_source_and_same_message_is_idempotent(self):
        with Memory() as memory:
            adapter=CognitiveMemory(memory)
            for thread,message,text in [("thread-a","message-a","我使用 Python"),("thread-b","message-b","我主要使用 Python")]:
                extraction=MemoryExtraction(memories=[MemoryCandidate(content=text,memory_key="language",memory_value="Python",tags=["preference"])])
                adapter.write("alice",text,extraction,thread,message)
            row=memory.list_memories("alice")[0]
            evidence=memory.evidence("alice",row["id"])
            self.assertEqual({r["thread_id"] for r in evidence["items"]},{"thread-a","thread-b"})
            self.assertEqual(evidence["total_count"],row["evidence_count"])
            replay=adapter.write("alice",text,extraction,thread,message)
            self.assertEqual(replay[0]["decision"],"UNCHANGED")
            self.assertEqual(memory.evidence("alice",row["id"])["total_count"],2)
            self.assertEqual(memory.list_memories("alice")[0]["evidence_count"],2)

    def test_working_duplicate_can_be_promoted_with_stronger_input(self):
        with Memory() as memory:
            weak=self.write(memory,"需要保留的事实","yes",importance=0.1,confidence=0.2,tags=["noise"])
            strong=self.write(memory,"需要保留的事实","yes",importance=0.9,confidence=0.95)
            self.assertEqual(strong["decision"],"WRITE_CURRENT")
            self.assertEqual(memory.storage.get_memory(weak["memory"]["id"])["state_role"],"archived")

    def test_evidence_endpoint_is_scoped_and_deletion_removes_evidence(self):
        with Memory() as memory, TestClient(create_app(service=memory)) as client:
            row=self.write(memory,"保留来源的记录","yes")["memory"]
            path=f"/api/memories/{row['id']}/evidence"
            self.assertEqual(client.get(f"/api/memories/{row['id']}",params={"user_id":"bob"}).status_code,404)
            self.assertEqual(client.get(f"/api/memories/{row['id']}",params={"user_id":"alice"}).json()["id"],row['id'])
            self.assertEqual(client.get(path,params={"user_id":"bob"}).status_code,404)
            self.assertEqual(client.get(path,params={"user_id":"alice"}).json()["total_count"],1)
            memory.delete_memory("alice",row["id"])
            self.assertEqual(memory.storage.evidence_count(row["id"]),0)
            self.assertEqual(client.get(path,params={"user_id":"alice"}).status_code,404)

    def test_legacy_source_is_backfilled_once_without_fabricating_missing_events(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/"memory.db"
            with Memory(path) as memory:
                record=self.write(memory,"历史来源","yes",metadata={"thread_id":"old-thread"})["memory"]
                with memory.storage.transaction():
                    memory.storage._conn.execute("DELETE FROM memory_evidence")
                    memory.storage._conn.execute("UPDATE memories SET evidence_count=4")
            with Memory(path) as memory:
                evidence=memory.evidence("alice",record["id"])
                self.assertEqual(evidence["total_count"],1)
                self.assertEqual(evidence["legacy_gap"],3)
                self.assertTrue(evidence["items"][0]["legacy"])
                self.assertEqual(evidence["items"][0]["thread_id"],"old-thread")
            with Memory(path) as memory:
                self.assertEqual(memory.evidence("alice",record["id"]),evidence)
