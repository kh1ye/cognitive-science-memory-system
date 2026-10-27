"""Interleaved baseline/v2 calls; labels and prompt hashes fixed before calls."""

import hashlib
import json
import random
import runpy
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

from conversation_agent.llm import LLMSettings
from conversation_agent.memory_concepts import CONCEPT_PROMPTS

ROOT = Path(__file__).parent
EVALUATION = ROOT.parent
EVALUATOR = runpy.run_path(str(EVALUATION / "project-memory-100/run_concept_eval.py"))


def main():
    datasets = {}
    hashes = {}
    for path in [
        EVALUATION / "project-memory-challenge-100/cases.json",
        ROOT / "holdout.json",
    ]:
        raw = path.read_bytes()
        dataset = json.loads(raw)
        datasets[dataset["version"]] = dataset
        hashes[dataset["version"]] = hashlib.sha256(raw).hexdigest()
    previous = json.loads(
        (
            EVALUATION
            / "project-memory-challenge-100/results/20261027-230557/summary.json"
        ).read_text()
    )
    assert hashes["natural-v2"] == previous["dataset_sha256"]
    assert (
        hashlib.sha256(CONCEPT_PROMPTS["baseline"].encode()).hexdigest()
        == previous["prompt_sha256"]
    )
    all_examples = [c["example"] for d in datasets.values() for c in d["cases"]]
    assert len(set(all_examples)) == len(all_examples) == 132
    for dataset in datasets.values():
        assert (
            len(set(Counter(c["memory_type"] for c in dataset["cases"]).values())) == 1
        )
    jobs = [
        (dataset["version"], version, case)
        for dataset in datasets.values()
        for version in CONCEPT_PROMPTS
        for case in dataset["cases"]
    ]
    settings = LLMSettings.from_env()
    stamp = datetime.now(timezone(timedelta(hours=8)))
    output = ROOT / "results" / stamp.strftime("%Y%m%d-%H%M%S")
    output.mkdir(parents=True, exist_ok=False)
    plan = {
        "started_at": stamp.isoformat(),
        "model": settings.model,
        "provider": settings.provider,
        "dataset_hashes": hashes,
        "prompt_hashes": {
            v: hashlib.sha256(p.encode()).hexdigest()
            for v, p in CONCEPT_PROMPTS.items()
        },
        "seed": 20261027,
        "workers": 4,
        "temperature": "provider_default",
        "calls": len(jobs),
        "method": "One independent call per sample and version, interleaved; no answer-based retries",
        "limitations": [
            "旧100条属于已知调试数据；新32条也由同一作者在看过错误后编写，不是外部独立基准。",
            "保留全部参考标签，包括已知有歧义的N058；unknown和调用失败均不计为符合参考。",
            "模型默认采样参数未变；两臂新调用均计分，不挑选既有较低的基线结果。",
        ],
        "datasets": datasets,
    }
    (output / "plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
    )
    for version, prompt in CONCEPT_PROMPTS.items():
        (output / f"prompt-{version}.txt").write_text(prompt + "\n")
    (output / "frozen-manifest.json").write_text(
        json.dumps(
            {
                "plan_sha256": hashlib.sha256(
                    (output / "plan.json").read_bytes()
                ).hexdigest(),
                "fixed_before_calls": True,
            },
            indent=2,
        )
        + "\n"
    )
    random.Random(plan["seed"]).shuffle(jobs)
    rows = []
    started = time.monotonic()
    print(f"Output: {output.resolve()}", flush=True)

    def predict(job):
        dataset_version, prompt_version, case = job
        return {
            **EVALUATOR["predict"](case, prompt_version),
            "dataset_version": dataset_version,
            "prompt_version": prompt_version,
        }

    with (
        (output / "predictions.jsonl").open("w") as file,
        ThreadPoolExecutor(max_workers=4) as pool,
    ):
        futures = [pool.submit(predict, job) for job in jobs]
        for future in as_completed(futures):
            row = future.result()
            rows.append(row)
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
            file.flush()
            if len(rows) % 25 == 0:
                print(
                    json.dumps(
                        {
                            "completed": len(rows),
                            "errors": sum(r["status"] == "error" for r in rows),
                        }
                    ),
                    flush=True,
                )
    summary = {
        "model": settings.model,
        "attempted": len(rows),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "results": {},
    }
    lines = [
        "# 概念分类代码修订：相同数据的交错对照",
        "",
        f"模型：{settings.model}；共{len(rows)}次独立调用。",
        "",
        "|数据|提示版本|与参考一致/总数|Macro-F1|调用失败|",
        "|---|---|---:|---:|---:|",
    ]
    for dataset in datasets.values():
        for version in CONCEPT_PROMPTS:
            cell = [
                r
                for r in rows
                if r["dataset_version"] == dataset["version"]
                and r["prompt_version"] == version
            ]
            stats = EVALUATOR["summarize"](
                cell,
                {
                    "model": settings.model,
                    "prompt_version": version,
                    "dataset_version": dataset["version"],
                },
            )
            key = f"{dataset['version']}/{version}"
            summary["results"][key] = stats
            lines.append(
                f"|{dataset['version']}|{version}|{stats['correct']}/{stats['attempted']}|{stats['macro_f1']:.3f}|{stats['api_errors']}|"
            )
            detail = output / key
            detail.mkdir(parents=True)
            stats["started_at"] = stamp.isoformat()
            EVALUATOR["render"](cell, stats, detail)
    lines += [
        "",
        "## 逐条比较",
        "",
        "|数据/编号|原句|参考|基线|修订|",
        "|---|---|---|---|---|",
    ]
    lookup = {(r["dataset_version"], r["id"], r["prompt_version"]): r for r in rows}
    for dataset in datasets.values():
        for case in dataset["cases"]:
            predictions = [
                lookup[(dataset["version"], case["id"], v)]["predicted"]
                for v in CONCEPT_PROMPTS
            ]
            lines.append(
                f"|{dataset['version']}/{case['id']}|{case['example']}|{case['memory_type']}|{'|'.join(predictions)}|"
            )
    lines += [
        "",
        "## 限制",
        "",
        *[f"- {item}" for item in plan["limitations"]],
        "",
        "此处只测项目可复用概念分类函数；实际输入分流的多目标候选与写入须另行测试。所有输入与参考标签未在调用后更改。",
    ]
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    )
    (output / "report.md").write_text("\n".join(lines) + "\n")
    (ROOT / "results/latest.json").write_text(
        json.dumps({"output": str(output.resolve())}, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "attempted": len(rows),
                "results": {
                    k: {
                        f: v[f]
                        for f in ["correct", "attempted", "api_errors", "wrong_ids"]
                    }
                    for k, v in summary["results"].items()
                },
                "report": str((output / "report.md").resolve()),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
