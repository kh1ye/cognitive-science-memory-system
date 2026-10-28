"""Auto learning must not promote inferred habits from a stated preference."""

import unittest

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from api.app import create_app


def fact(predicate, evidence="我喜欢早上跑步", epistemic="explicit", status="current"):
    return {
        "subject": "alice",
        "predicate": predicate,
        "value": True,
        "evidence_text": evidence,
        "epistemic_status": epistemic,
        "status": status,
    }


class Model:
    def __init__(self, candidates):
        self.candidates = candidates

    def invoke(self, messages):
        return AIMessage(content="好的")

    def with_structured_output(self, schema, **kwargs):
        return RunnableLambda(
            lambda _: schema.model_validate({"semantic_candidates": self.candidates})
        )


class ExplicitMemoryTests(unittest.TestCase):
    def test_chat_keeps_preference_without_inferred_habit(self):
        inferred = fact(
            "has a regular morning running routine",
            epistemic="inferred",
            status="candidate",
        )
        explicit = fact("prefers running in the morning")
        # Check both positions, so skipping a candidate cannot redirect a retry receipt.
        for candidates in ([inferred, explicit], [explicit, inferred]):
            with (
                self.subTest(candidates=candidates),
                TestClient(create_app(":memory:", chat_model=Model(candidates))) as c,
            ):
                reply = c.post(
                    "/api/chat",
                    json={
                        "user_id": "alice",
                        "thread_id": "running",
                        "message": "我喜欢早上跑步",
                    },
                ).json()
                self.assertEqual(reply["memory_status"], "processed")
                self.assertEqual(len(reply["memory_results"]), 1)
                receipt = reply["memory_results"][0]
                self.assertEqual(receipt["result_status"], "current")
                self.assertEqual(receipt["epistemic_status"], "explicit")
                rows = c.get(
                    "/api/architecture/objects/semantic_assertions?user_id=alice"
                ).json()["items"]
                self.assertEqual(
                    [r["predicate"] for r in rows], ["prefers running in the morning"]
                )
                restored = c.get("/api/sessions/running?user_id=alice").json()[
                    "messages"
                ][-1]
                self.assertEqual(restored["memory_results"], reply["memory_results"])

    def test_only_inference_keeps_context_without_long_term_body(self):
        for epistemic in ("inferred", "supported", "legacy_unverified"):
            with (
                self.subTest(epistemic=epistemic),
                TestClient(
                    create_app(
                        ":memory:",
                        chat_model=Model(
                            [
                                fact(
                                    "regular runner",
                                    epistemic=epistemic,
                                    status="candidate",
                                )
                            ]
                        ),
                    )
                ) as c,
            ):
                reply = c.post(
                    "/api/chat",
                    json={
                        "user_id": "alice",
                        "thread_id": "running",
                        "message": "我喜欢早上跑步",
                    },
                ).json()
                self.assertEqual(reply["memory_status"], "no_new_memory")
                self.assertEqual(reply["memory_results"], [])
                self.assertEqual(
                    c.get(
                        "/api/architecture/objects/semantic_assertions?user_id=alice"
                    ).json()["items"],
                    [],
                )
                sources = c.get(
                    "/api/architecture/objects/source_records?user_id=alice"
                ).json()["items"]
                self.assertTrue(sources)
                self.assertTrue(all(r["content"] is None for r in sources))
                self.assertEqual(
                    reply["working_state"]["observations"][0]["content"],
                    "我喜欢早上跑步",
                )

    def test_observe_api_rejects_inference_and_preserves_retry_identity(self):
        with TestClient(create_app(":memory:")) as c:
            body = {
                "observation": {
                    "user_id": "alice",
                    "thread_id": "running",
                    "task_id": "task",
                    "source_event_id": "one",
                    "content": "我喜欢早上跑步",
                },
                "analysis": {
                    "semantic_candidates": [
                        fact(
                            "regular runner", epistemic="inferred", status="candidate"
                        ),
                        fact("prefers running in the morning"),
                    ]
                },
            }
            first = c.post("/api/architecture/observe", json=body).json()
            replay = c.post("/api/architecture/observe", json=body).json()
            self.assertEqual(first["operations"], replay["operations"])
            self.assertEqual(len(first["operations"]), 1)
            rows = c.get(
                "/api/architecture/objects/semantic_assertions?user_id=alice"
            ).json()["items"]
            self.assertEqual(len(rows), 1)
            self.assertEqual(first["operations"][0]["result_refs"], [rows[0]["id"]])

    def test_explicit_routine_and_two_distinct_facts_still_save(self):
        for message, candidates in (
            ("我每天早上跑步", [fact("daily morning run", evidence="我每天早上跑步")]),
            (
                "我喜欢晨跑，也喜欢游泳",
                [
                    fact("prefers morning run", evidence="我喜欢晨跑"),
                    fact("prefers swimming", evidence="喜欢游泳"),
                ],
            ),
        ):
            with (
                self.subTest(message=message),
                TestClient(create_app(":memory:", chat_model=Model(candidates))) as c,
            ):
                reply = c.post(
                    "/api/chat",
                    json={
                        "user_id": "alice",
                        "thread_id": "running",
                        "message": message,
                    },
                ).json()
                self.assertEqual(len(reply["memory_results"]), len(candidates))
                self.assertTrue(
                    all(r["status"] == "succeeded" for r in reply["memory_results"])
                )

    def test_observe_only_inference_keeps_no_long_term_source_body(self):
        with TestClient(create_app(":memory:")) as c:
            body = {
                "observation": {
                    "user_id": "alice",
                    "thread_id": "running",
                    "task_id": "task",
                    "source_event_id": "only-inference",
                    "content": "我喜欢早上跑步",
                },
                "analysis": {
                    "semantic_candidates": [
                        fact("regular runner", epistemic="inferred", status="candidate")
                    ]
                },
            }
            reply = c.post("/api/architecture/observe", json=body).json()
            self.assertEqual(reply["status"], "no_long_term")
            self.assertEqual(reply["operations"], [])
            self.assertEqual(
                c.get(
                    "/api/architecture/objects/semantic_assertions?user_id=alice"
                ).json()["items"],
                [],
            )
            sources = c.get(
                "/api/architecture/objects/source_records?user_id=alice"
            ).json()["items"]
            self.assertTrue(all(r["content"] is None for r in sources))
