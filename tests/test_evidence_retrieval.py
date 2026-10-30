import unittest

from cognitive_memory import Memory
from cognitive_memory.architecture_models import Observation, ObservationAnalysis, SemanticAssertion, EpisodeEvent
from cognitive_memory.retrieval.evidence import rank


class EvidenceRetrievalTests(unittest.TestCase):
    def test_distinctive_words_outweigh_shared_question_words(self):
        scores = rank("Which silver instrument did I repair?", ["I did say which instrument I did repair", "The silver flute required repair", "instrument repair", "instrument repair"])
        self.assertGreater(scores[1], scores[0])

    def test_hyphens_and_plural_forms_do_not_hide_terms(self):
        self.assertGreater(rank("second-hand instruments", ["second hand instrument"])[0], 0)

    def test_context_resolves_pronouns_without_promoting_source_to_fact(self):
        with Memory() as memory:
            text = "My blue ceramic vase came from a coastal auction. Its maker is Mira Chen."
            observation = Observation(user_id="alice", thread_id="old", task_id="old",
                source_event_id="vase", content=text, scope="project:a")
            memory.architecture.observe(observation, ObservationAnalysis(semantic_candidates=[
                SemanticAssertion(subject="vase", predicate="maker", value="Mira Chen", evidence_text="Its maker is Mira Chen", scope="project:a")]))
            before = memory.architecture.repo.rows("semantic_assertions", "alice")
            found = memory.architecture.retrieve_knowledge("alice", "coastal auction ceramic vase maker", scope="project:a")
            self.assertEqual(len(found), 1)
            self.assertIn("coastal auction", found[0]["_retrieval_context"])
            self.assertEqual(memory.architecture.repo.rows("semantic_assertions", "alice"), before)
            self.assertEqual(memory.architecture.retrieve_knowledge("alice", "vase", scope="project:b"), [])
            self.assertEqual(memory.architecture.retrieve_knowledge("bob", "vase", scope="project:a"), [])

    def test_unrelated_query_does_not_return_arbitrary_records(self):
        with Memory() as memory:
            memory.architecture.observe(Observation(user_id="alice", thread_id="a", task_id="a", source_event_id="a", content="I visited Oslo"),
                ObservationAnalysis(episode_candidates=[EpisodeEvent(observation="I visited Oslo")]))
            self.assertEqual(memory.architecture.retrieve_episodes("alice", "neutrino detector"), [])
            self.assertTrue(memory.architecture.retrieve_episodes("alice", "Oslo"))

    def test_conflicting_report_can_be_recalled_without_asserting_either_value(self):
        with Memory() as memory:
            report = "I received two notices for train Aurora at noon: notice A says platform 2, notice B says platform 4. Neither notice has priority."
            memory.architecture.observe(Observation(user_id="alice", thread_id="reported", task_id="reported",
                source_event_id="notices", content=report), ObservationAnalysis(
                    episode_candidates=[EpisodeEvent(observation=report)]))
            refs = memory.catalog.retrieve("alice", "new", "new", "Aurora platform", modules=("semantic", "episodic"))
            self.assertEqual(len(refs), 1)
            self.assertEqual(refs[0]["memory_type"], "episodic")
            self.assertIn("Neither notice has priority", refs[0]["content"])
            self.assertEqual(memory.architecture.repo.rows("semantic_assertions", "alice"), [])


if __name__ == "__main__":
    unittest.main()
