"""Run offline: uv run python scripts/coala_example.py. No API key or user DB touched."""

from cognitive_memory import Memory
from cognitive_memory.architecture_models import (
    EpisodeEvent,
    Observation,
    ObservationAnalysis,
    SemanticAssertion,
)


def main():
    with Memory() as memory:
        a = memory.architecture
        observation = Observation(
            user_id="alice",
            thread_id="example",
            task_id="first",
            source_event_id="user-1",
            content="整理项目说明；以后默认用中文",
            scope="user",
        )
        receipt = a.observe(
            observation,
            ObservationAnalysis(
                working_state_patch={"goals": ["整理项目说明"]},
                episode_candidates=[EpisodeEvent(observation="整理项目说明")],
                semantic_candidates=[
                    SemanticAssertion(
                        subject="alice",
                        predicate="preferred_language",
                        value="中文",
                        evidence_text="以后默认用中文",
                    )
                ],
            ),
        )
        a.install_builtins("alice")
        procedure = next(
            r
            for r in a.retrieve_procedures("alice", "normalize")
            if r["implementation_ref"] == "text.normalize"
        )
        run = a.execute_procedure(
            "alice",
            procedure["id"],
            {"text": " project   notes "},
            run_key="normalize-1",
            thread="example",
            task="first",
        )
        a.update_working_state(
            "alice",
            "example",
            "first",
            {
                "status": "completed",
                "task_state": {"run_id": run["id"], "result": run["result"]},
            },
        )
        reused = a.retrieve(
            "alice", "example", "next", "preferred_language", modules=["semantic"]
        )
        print(
            "学习回执:",
            [(op["target_module"], op["status"]) for op in receipt["operations"]],
        )
        print("程序版本与实际结果:", run["version"], run["status"], run["result"])
        print(
            "后续任务激活:",
            [(ref["module"], ref["record"].get("value")) for ref in reused],
        )
        print(
            "后续任务临时约束:", a.working_state("alice", "example", "next").constraints
        )


if __name__ == "__main__":
    main()
