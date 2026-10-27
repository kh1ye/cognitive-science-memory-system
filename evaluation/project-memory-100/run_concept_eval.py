"""Live evaluation of memory concepts only; no production Memory/DB is opened."""

import argparse
import hashlib
import json
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

from conversation_agent.llm import LLMSettings
from conversation_agent.memory_concepts import (
    BASELINE_PROMPT,
    CONCEPT_PROMPTS,
    DEFAULT_CONCEPT_PROMPT_VERSION,
    MemoryConceptPrediction,
    classify_memory_concept,
)

ROOT = Path(__file__).parent
LABELS = ["working", "episodic", "semantic", "procedural"]
NAMES = {
    "working": "工作记忆",
    "episodic": "情景记忆",
    "semantic": "语义记忆",
    "procedural": "程序性记忆",
    "unknown": "无法判断",
    "error": "调用失败",
}
# Preserve the historical baseline name used by the diagnostic runner.
PROMPT = BASELINE_PROMPT
Prediction = MemoryConceptPrediction


def predict(case, prompt_version=DEFAULT_CONCEPT_PROMPT_VERSION):
    # A fresh, independent call sees the example text only; no ID, gold or explanation.
    started = time.monotonic()
    try:
        model = LLMSettings.from_env().create_model()
        prediction, usage = classify_memory_concept(
            model, case["example"], prompt_version=prompt_version
        )
        return {
            "id": case["id"],
            "example": case["example"],
            "gold": case["memory_type"],
            "predicted": prediction.label,
            "reason": prediction.reason,
            "status": "ok",
            "correct": prediction.label == case["memory_type"],
            "usage": usage,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
    except Exception as error:  # noqa: BLE001 -- keep every failed trial in the denominator
        return {
            "id": case["id"],
            "example": case["example"],
            "gold": case["memory_type"],
            "predicted": "error",
            "reason": "",
            "status": "error",
            "correct": False,
            "error_type": type(error).__name__,
            "http_status": getattr(error, "status_code", None),
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }


def summarize(rows, metadata):
    confusion = {
        label: dict.fromkeys([*LABELS, "unknown", "error"], 0) for label in LABELS
    }
    for row in rows:
        confusion[row["gold"]][row["predicted"]] += 1
    per_class = {}
    for label in LABELS:
        true_positive = sum(
            r["gold"] == label and r["predicted"] == label for r in rows
        )
        support = sum(r["gold"] == label for r in rows)
        predicted = sum(r["predicted"] == label for r in rows)
        precision = true_positive / predicted if predicted else 0.0
        recall = true_positive / support if support else 0.0
        f1 = (
            2 * precision * recall / (precision + recall) if precision + recall else 0.0
        )
        per_class[label] = {
            "support": support,
            "correct": true_positive,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }
    return {
        **metadata,
        "attempted": len(rows),
        "correct": sum(r["correct"] for r in rows),
        "accuracy": sum(r["correct"] for r in rows) / len(rows) if rows else None,
        "api_errors": sum(r["status"] == "error" for r in rows),
        "abstentions": sum(r["predicted"] == "unknown" for r in rows),
        "macro_f1": sum(s["f1"] for s in per_class.values()) / len(LABELS),
        "per_class": per_class,
        "confusion_matrix": confusion,
        "wrong_ids": [
            r["id"] for r in sorted(rows, key=lambda r: r["id"]) if not r["correct"]
        ],
        "measured": "memory_concept_classification",
        "not_measured": [
            "production observation routing",
            "long-term writes",
            "working-state recovery",
            "procedure execution",
        ],
        "limitations": [
            "项目自建、作者给定参考标签，未经独立专家验证；单次采样，不代表复杂对话或通用能力。",
            "四类定义写入固定评测提示，未提供带标签示例或当前样本答案。",
            "模型版本为提供商标识，可能是别名；底层模型权重版本不可验证。",
            "调用项目概念分类函数；实际输入分流使用独立的多目标结构，不由本成绩替代。",
        ],
    }


def render(rows, summary, output):
    lines = [
        f"# 四种记忆概念识别：{summary['attempted']} 条实测",
        "",
        f"模型：`{summary['model']}`；时间：{summary['started_at']}；数据版本：`{summary['dataset_version']}`。",
        "",
        "**范围：独立的概念分类提示，不是生产 observe/聊天分流测试。未写入用户记忆或执行程序。**",
        "",
        f"已测试 {summary['attempted']} 条，与参考标签一致 {summary['correct']} 条，一致率 {summary['accuracy']:.1%}，Macro-F1 {summary['macro_f1']:.3f}。",
        f"调用/格式失败 {summary['api_errors']} 条；无法判断 {summary['abstentions']} 条。失败与弃答均按未正确计入总分。",
        "",
        "|参考类别|一致/总数|Precision|Recall|F1|",
        "|---|---:|---:|---:|---:|",
    ]
    for label, stats in summary["per_class"].items():
        lines.append(
            f"|{NAMES[label]}|{stats['correct']}/{stats['support']}|{stats['precision']:.3f}|{stats['recall']:.3f}|{stats['f1']:.3f}|"
        )
    lines += ["", "## 与参考标签不一致的样本", ""]
    wrong = [r for r in sorted(rows, key=lambda r: r["id"]) if not r["correct"]]
    if not wrong:
        lines.append(
            "本次未出现与参考标签不一致的样本，不能据此推断真实系统四类记忆已经全部正确。"
        )
    for r in wrong:
        lines += [
            f"### {r['id']}",
            "",
            r["example"],
            "",
            f"预期：{NAMES[r['gold']]}；预测：{NAMES[r['predicted']]}。",
            "",
            r["reason"] or r.get("error_type", ""),
            "",
        ]
    lines += [
        "",
        "## 测试方式与限制",
        "",
        "固定种子打乱顺序，逐条独立调用；模型仅看到分类定义和当前句子，看不到分组、编号、原解释或标准答案。标准标签只在响应后用于计分。",
        "每个样本一次结构化模型调用；SDK可能按其配置重试传输。无基于标准答案的重问或挑选结果。",
        "参考标签由作者在测试前确定，未经独立专家验证；现实活动可能涉及多种记忆，不一致样本需要同时复核模型判断和标注歧义。",
        "这轮只检验模型能否区分四个记忆概念。没有验证实际数据库写入、程序注册执行、来源删除或多轮状态管理。",
        "",
        "## 全部逐条结果",
        "",
        "|编号|例子|标准|预测|结果|模型简短依据|",
        "|---|---|---|---|---|---|",
    ]
    for r in sorted(rows, key=lambda r: r["id"]):
        reason = (
            (r["reason"] or r.get("error_type", ""))
            .replace("|", "\\|")
            .replace("\n", " ")
        )
        lines.append(
            f"|{r['id']}|{r['example']}|{NAMES[r['gold']]}|{NAMES[r['predicted']]}|{'正确' if r['correct'] else '未正确'}|{reason}|"
        )
    (output / "report.md").write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dataset", type=Path, default=ROOT / "cases.json")
    parser.add_argument(
        "--prompt-version",
        choices=tuple(CONCEPT_PROMPTS),
        default=DEFAULT_CONCEPT_PROMPT_VERSION,
    )
    args = parser.parse_args()
    data_bytes = args.dataset.read_bytes()
    dataset = json.loads(data_bytes)
    cases = list(dataset["cases"])
    assert cases and {c["memory_type"] for c in cases} <= set(LABELS)
    assert len({c["id"] for c in cases}) == len(cases) and len(
        {c["example"] for c in cases}
    ) == len(cases)
    if args.workers < 1:
        raise SystemExit("--workers must be positive")
    prompt = CONCEPT_PROMPTS[args.prompt_version]
    settings = LLMSettings.from_env()
    if not settings.api_key:
        raise SystemExit("No API key configured")
    stamp = datetime.now(timezone(timedelta(hours=8)))
    output = args.output or args.dataset.resolve().parent / "results" / stamp.strftime(
        "%Y%m%d-%H%M%S"
    )
    output.mkdir(parents=True, exist_ok=False)
    metadata = {
        "started_at": stamp.isoformat(),
        "provider": settings.provider,
        "model": settings.model,
        "dataset_version": dataset["version"],
        "dataset_sha256": hashlib.sha256(data_bytes).hexdigest(),
        "prompt_version": args.prompt_version,
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "seed": 20261027,
        "workers": args.workers,
        "temperature": "provider_default",
        "sdk_max_retries": 1,
        "status": "running",
    }
    (output / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n"
    )
    (output / "prompt.txt").write_text(prompt + "\n")
    random.Random(20261027).shuffle(cases)
    rows = []
    print("Output: " + str(output.resolve()), flush=True)
    started = time.monotonic()
    with (
        (output / "predictions.jsonl").open("w") as file,
        ThreadPoolExecutor(max_workers=args.workers) as pool,
    ):
        futures = [pool.submit(predict, case, args.prompt_version) for case in cases]
        for future in as_completed(futures):
            row = future.result()
            rows.append(row)
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
            file.flush()
            progress = {
                "completed": len(rows),
                "correct": sum(r["correct"] for r in rows),
                "errors": sum(r["status"] == "error" for r in rows),
            }
            (output / "progress.json").write_text(json.dumps(progress) + "\n")
            if len(rows) % 10 == 0 or row["status"] == "error":
                print(json.dumps(progress), flush=True)
    metadata.update(
        status="completed", elapsed_seconds=round(time.monotonic() - started, 3)
    )
    (output / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n"
    )
    summary = summarize(rows, metadata)
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    )
    render(rows, summary, output)
    latest_path = args.dataset.resolve().parent / "results" / "latest.json"
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(
        json.dumps(
            {
                "output": str(output.resolve()),
                "dataset_sha256": metadata["dataset_sha256"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    print(
        json.dumps(
            {
                "attempted": summary["attempted"],
                "correct": summary["correct"],
                "accuracy": summary["accuracy"],
                "api_errors": summary["api_errors"],
                "macro_f1": summary["macro_f1"],
                "wrong_ids": summary["wrong_ids"],
                "report": str((output / "report.md").resolve()),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
