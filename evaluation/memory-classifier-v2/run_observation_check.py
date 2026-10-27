"""Live production extraction + isolated in-memory writes, before/after prompts."""

import argparse
import hashlib
import json
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableLambda

from cognitive_memory import Memory
from cognitive_memory.architecture_models import Observation
from conversation_agent.llm import LLMSettings, analyze_observation
from conversation_agent.prompts import OBSERVATION_ANALYSIS_PROMPT

ROOT = Path(__file__).parent
# The unchanged prefix is exactly the pre-refactor production prompt.
OLD_PROMPT = OBSERVATION_ANALYSIS_PROMPT.split("\n内容边界：", 1)[0].rstrip()
CASES = [
    (
        "S1",
        "我在厦门读的初中。",
        {"semantic": True, "episode": False, "proposal": False},
    ),
    ("S2", "我吃面习惯加醋。", {"semantic": True, "episode": False, "proposal": False}),
    (
        "S3",
        "我知道换灯泡要先断电。",
        {"semantic": True, "episode": False, "proposal": False},
    ),
    (
        "S4",
        "我哥煎饼会先摊面糊再打鸡蛋。",
        {"semantic": True, "episode": False, "proposal": False},
    ),
    ("S5", "我会打乒乓球。", {"semantic": True, "episode": False, "proposal": False}),
    (
        "E1",
        "今天我坐船去鼓浪屿，回程下起了雨。",
        {"semantic": False, "episode": True, "proposal": False},
    ),
    (
        "E2",
        "刚才装书架，我把一块木板装反了。",
        {"semantic": False, "episode": True, "proposal": False},
    ),
    (
        "E3",
        "昨天下午，我和同事在公司门口拍了张合照。",
        {"semantic": False, "episode": True, "proposal": False},
    ),
    (
        "E4",
        "上周末我给朋友做饭，锅底烧糊了。",
        {"semantic": False, "episode": True, "proposal": False},
    ),
    (
        "W1",
        "这次回复只用英文。",
        {"semantic": False, "episode": False, "proposal": False, "working": True},
    ),
    (
        "W2",
        "这道题先别给答案，只给我一个提示。",
        {"semantic": False, "episode": False, "proposal": False, "working": True},
    ),
    (
        "S6",
        "以后默认用西班牙语回复我。",
        {"semantic": True, "episode": False, "proposal": False},
    ),
    (
        "P1",
        "请登记一个把重复空格合并的文本清理工具，先作为待验证的能力。",
        {"semantic": False, "episode": False, "proposal": True},
    ),
    (
        "M1",
        "我平时喝美式，昨天试了拿铁。这次帮我比较两种咖啡的价格。",
        {"semantic": True, "episode": True, "proposal": False, "working": True},
    ),
    (
        "M2",
        "我会折纸，昨天教妹妹折了一只纸鹤。",
        {"semantic": True, "episode": True, "proposal": False},
    ),
    (
        "N1",
        "你觉得我该买哪款相机？",
        {"semantic": False, "episode": False, "proposal": False},
    ),
]


class PromptVersionModel:
    """Run the same production function, swapping only its system prompt prefix."""

    def __init__(self, model, version):
        self.model, self.version = model, version

    def messages(self, messages):
        if self.version == "current":
            return messages
        return [
            SystemMessage(
                content=m.content.replace(OBSERVATION_ANALYSIS_PROMPT, OLD_PROMPT)
            )
            if isinstance(m, SystemMessage)
            else m
            for m in messages
        ]

    def with_structured_output(self, *args, **kwargs):
        runnable = self.model.with_structured_output(*args, **kwargs)
        return RunnableLambda(lambda messages: runnable.invoke(self.messages(messages)))

    def invoke(self, messages):
        return self.model.invoke(self.messages(messages))


def predict(job):
    version, case_id, example, expected = job
    started = time.monotonic()
    base = {"version": version, "id": case_id, "example": example, "expected": expected}
    try:
        model = PromptVersionModel(LLMSettings.from_env().create_model(), version)
        analysis = analyze_observation(
            model, "user_id=eval-user\n" + example, source_content=example
        )
        actual = {
            "semantic": bool(analysis.semantic_candidates),
            "episode": bool(analysis.episode_candidates),
            "proposal": bool(analysis.procedure_proposals),
            "working": any(
                bool(v)
                for v in analysis.working_state_patch.model_dump(
                    exclude_none=True
                ).values()
            ),
        }
        mismatches = [k for k, v in expected.items() if actual[k] != v]
        # A fresh private DB per sample exercises real source/evidence/write validation.
        with Memory(":memory:") as memory:
            result = memory.architecture.observe(
                Observation(
                    user_id="eval-user",
                    thread_id="boundary-eval",
                    task_id=case_id,
                    source_event_id=f"{version}-{case_id}",
                    content=example,
                ),
                analysis,
            )
            operation_statuses = [op["status"] for op in result["operations"]]
            persisted_counts = {
                "semantic": len(
                    memory.architecture.repo.rows("semantic_assertions", "eval-user")
                ),
                "episode": len(
                    memory.architecture.repo.rows("episode_events", "eval-user")
                ),
                "proposal": len(
                    memory.architecture.repo.rows("procedure_versions", "eval-user")
                ),
            }
            enabled_procedures = sum(
                p["status"] == "enabled"
                for p in memory.architecture.repo.rows(
                    "procedure_versions", "eval-user"
                )
            )
        candidate_count = (
            len(analysis.semantic_candidates)
            + len(analysis.episode_candidates)
            + len(analysis.procedure_proposals)
        )
        write_ok = (
            len(operation_statuses) == candidate_count
            and all(status == "succeeded" for status in operation_statuses)
            and all(bool(persisted_counts[k]) == actual[k] for k in persisted_counts)
            and enabled_procedures == 0
        )
        return {
            **base,
            "status": "ok",
            "actual": actual,
            "mismatches": mismatches,
            "analysis": analysis.model_dump(),
            "operation_statuses": operation_statuses,
            "persisted_counts": persisted_counts,
            "enabled_procedures": enabled_procedures,
            "write_ok": write_ok,
            "contract_match": not mismatches and write_ok,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
    except Exception as error:  # noqa: BLE001 -- record per-sample failure without provider secrets
        return {
            **base,
            "status": "error",
            "contract_match": False,
            "error_type": type(error).__name__,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--versions",
        nargs="+",
        choices=["baseline", "current"],
        default=["baseline", "current"],
    )
    args = parser.parse_args()
    settings = LLMSettings.from_env()
    stamp = datetime.now(timezone(timedelta(hours=8)))
    output = ROOT / "observation-results" / stamp.strftime("%Y%m%d-%H%M%S")
    output.mkdir(parents=True, exist_ok=False)
    plan = {
        "started_at": stamp.isoformat(),
        "model": settings.model,
        "cases": CASES,
        "prompt_hashes": {
            "baseline": hashlib.sha256(OLD_PROMPT.encode()).hexdigest(),
            "current": hashlib.sha256(OBSERVATION_ANALYSIS_PROMPT.encode()).hexdigest(),
        },
        "seed": 20261027,
        "workers": 2,
        "analyses": len(CASES) * len(args.versions),
        "scoring": "Exact boolean candidate presence for specified fields, plus every emitted write succeeds; unspecified working changes allowed",
        "limitations": "作者定义的16条小规模定向检查，不是四类单标签分类分数；复用实际函数的格式恢复策略，单次分析可能有格式恢复调用。",
    }
    (output / "plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
    )
    (output / "frozen-manifest.json").write_text(
        json.dumps(
            {
                "fixed_before_calls": True,
                "plan_sha256": hashlib.sha256(
                    (output / "plan.json").read_bytes()
                ).hexdigest(),
            },
            indent=2,
        )
        + "\n"
    )
    for version, prompt in [
        ("baseline", OLD_PROMPT),
        ("current", OBSERVATION_ANALYSIS_PROMPT),
    ]:
        (output / f"prompt-{version}.txt").write_text(prompt + "\n")
    jobs = [(version, *case) for version in args.versions for case in CASES]
    random.Random(plan["seed"]).shuffle(jobs)
    rows = []
    print(f"Output: {output.resolve()}", flush=True)
    with (
        (output / "predictions.jsonl").open("w") as file,
        ThreadPoolExecutor(max_workers=2) as pool,
    ):
        futures = [pool.submit(predict, job) for job in jobs]
        for future in as_completed(futures):
            row = future.result()
            rows.append(row)
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
            file.flush()
            if len(rows) % 8 == 0:
                print(
                    json.dumps(
                        {
                            "completed": len(rows),
                            "errors": sum(r["status"] == "error" for r in rows),
                        }
                    ),
                    flush=True,
                )
    summary = {"model": settings.model, "attempted": len(rows), "results": {}}
    for version in args.versions:
        cell = [r for r in rows if r["version"] == version]
        summary["results"][version] = {
            "attempted": len(cell),
            "contract_matches": sum(r["contract_match"] for r in cell),
            "errors": sum(r["status"] == "error" for r in cell),
            "mismatch_ids": [r["id"] for r in cell if not r["contract_match"]],
        }
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    )
    (ROOT / "observation-results/latest.json").write_text(
        json.dumps({"output": str(output.resolve())}, indent=2) + "\n"
    )
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
