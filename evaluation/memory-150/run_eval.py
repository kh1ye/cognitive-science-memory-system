import hashlib, json, time, os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from cognitive_memory import Memory
from conversation_agent import ConversationAgent
from conversation_agent.llm import LLMSettings
from conversation_agent.memory_concepts import (
    classify_memory_concept,
    CONCEPT_PROMPT_V2,
)
from conversation_agent.prompts import OBSERVATION_ANALYSIS_PROMPT

ROOT = Path(__file__).resolve().parent
stamp = time.strftime("%Y%m%d-%H%M%S")
out = Path(os.environ["EVALUATION_OUTPUT_DIR"]) if os.environ.get("EVALUATION_OUTPUT_DIR") else ROOT / "results" / stamp
out.mkdir(parents=True)
raw = (ROOT / "cases.json").read_bytes()
cases = json.loads(raw)["cases"]
(out / "manifest.json").write_text(
    json.dumps(
        {
            "dataset_sha256": hashlib.sha256(raw).hexdigest(),
            "model": LLMSettings.from_env().model,
            "concept_prompt_sha256": hashlib.sha256(
                CONCEPT_PROMPT_V2.encode()
            ).hexdigest(),
            "observation_prompt_sha256": hashlib.sha256(
                OBSERVATION_ANALYSIS_PROMPT.encode()
            ).hexdigest(),
            "code_commit": __import__("subprocess")
            .check_output(["git", "rev-parse", "HEAD"], text=True)
            .strip(),
            "working_tree_modified": True,
            "workers": 4,
        },
        indent=2,
    )
)
manifest = json.loads((out / "manifest.json").read_text())
manifest["source_sha256"] = {
    f: hashlib.sha256(Path(f).read_bytes()).hexdigest()
    for f in [
        "src/cognitive_memory/value.py",
        "src/cognitive_memory/architecture.py",
        "src/conversation_agent/graph.py",
    ]
}
(out / "manifest.json").write_text(json.dumps(manifest, indent=2))
(out / "context-only-policy.txt").write_text(
    Path("src/cognitive_memory/value.py").read_text()
)
(out / "concept-prompt.txt").write_text(CONCEPT_PROMPT_V2)
(out / "observation-prompt.txt").write_text(OBSERVATION_ANALYSIS_PROMPT)


def evaluate(case):
    r = dict(case)
    start = time.monotonic()
    try:
        model = LLMSettings.from_env().create_model()
        if case["category"] != "low_value":
            prediction, usage = classify_memory_concept(model, case["example"])
            r.update(
                actual=prediction.label,
                reason=prediction.reason,
                correct=prediction.label == case["expected"],
                usage=usage,
            )
        else:
            with Memory() as memory:
                agent = ConversationAgent(memory, ":memory:", model=model)
                try:
                    reply = agent.chat(
                        "qa-" + case["id"].lower(), "chat", case["example"]
                    )
                    modules = {
                        t: memory.architecture.repo.rows(t, "qa-" + case["id"].lower())
                        for t in [
                            "semantic_assertions",
                            "episode_events",
                            "procedure_versions",
                            "working_states",
                            "source_records",
                        ]
                    }
                    learned = sum(
                        len(modules[t])
                        for t in ["semantic_assertions", "episode_events"]
                    ) + sum(
                        bool(p.get("source_refs"))
                        for p in modules["procedure_versions"]
                    )
                    transcript = agent.get_session("qa-" + case["id"].lower(), "chat")
                    context_saved = case["example"] in str(transcript) and bool(
                        modules["working_states"]
                    )
                    source_body_saved = any(
                        s.get("content") for s in modules["source_records"]
                    )
                    r["strict_context_only"] = (
                        learned == 0 and context_saved and not source_body_saved
                    )
                    r.update(
                        actual="context_only"
                        if learned == 0 and context_saved
                        else "long_term_write"
                        if learned
                        else "context_missing",
                        correct=learned == 0 and context_saved,
                        reason=f"长期用户对象{learned}；上下文保留{context_saved}；来源正文落库{source_body_saved}",
                        learned_count=learned,
                        context_saved=context_saved,
                        source_body_saved=source_body_saved,
                        reply=reply,
                        objects=modules,
                    )
                finally:
                    agent.close()
        r["status"] = "ok"
    except Exception as error:
        r.update(
            actual="error",
            correct=False,
            status="error",
            error_type=type(error).__name__,
        )
    r["elapsed_seconds"] = round(time.monotonic() - start, 3)
    return r


import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--reuse-concepts", type=Path)
args = parser.parse_args()
rows = []
if args.reuse_concepts:
    rows = [
        json.loads(line)
        for line in args.reuse_concepts.read_text().splitlines()
        if json.loads(line)["category"] != "low_value"
    ]
    assert len(rows) == 120
    cases = [c for c in cases if c["category"] == "low_value"]
    manifest = json.loads((out / "manifest.json").read_text())
    manifest["reused_concept_results"] = str(args.reuse_concepts)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
with (
    (out / "predictions.jsonl").open("w") as f,
    ThreadPoolExecutor(max_workers=4) as pool,
):
    for existing in rows:
        f.write(json.dumps(existing, ensure_ascii=False) + "\n")
    for future in as_completed([pool.submit(evaluate, c) for c in cases]):
        r = future.result()
        rows.append(r)
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
        f.flush()
        progress = {
            "completed": len(rows),
            "errors": sum(x["status"] == "error" for x in rows),
        }
        (out / "progress.json").write_text(json.dumps(progress))
        if len(rows) % 10 == 0:
            print(json.dumps(progress), flush=True)
summary = {
    "total": len(rows),
    "api_errors": sum(r["status"] == "error" for r in rows),
    "categories": {},
}
for kind in ["working", "episodic", "semantic", "procedural", "low_value"]:
    group = [r for r in rows if r["category"] == kind]
    summary["categories"][kind] = {
        "total": len(group),
        "correct": sum(r["correct"] for r in group),
        "accuracy": sum(r["correct"] for r in group) / len(group),
        "wrong_ids": [r["id"] for r in group if not r["correct"]],
    }
summary["strict_context_only_passed"] = sum(
    r.get("strict_context_only", False) for r in rows
)
summary["low_value_source_body_saved_ids"] = [
    r["id"] for r in rows if r.get("source_body_saved")
]
(out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
(ROOT / "latest.json").write_text(json.dumps({"output": str(out)}, ensure_ascii=False))
names = {
    "working": "工作记忆",
    "episodic": "情景记忆",
    "semantic": "语义记忆",
    "procedural": "程序记忆",
    "low_value": "低价值信息",
    "context_only": "仅上下文",
    "error": "调用失败",
}
lines = [
    "# 150条实测结果",
    "",
    "前120条为概念分类，后30条为真实聊天存储测试，不把两种指标合并成一个分类准确率。",
    "",
    "|类别|总数|正确|准确率|",
    "|---|---:|---:|---:|",
]
for k, v in summary["categories"].items():
    lines.append(f"|{names[k]}|{v['total']}|{v['correct']}|{v['accuracy']:.2%}|")
lines += [
    "",
    f"API失败：{summary['api_errors']}。低价值输入仍在source_records保留正文的样本：{summary['low_value_source_body_saved_ids']}。会话和工作状态本来就持久化SQLite，并非自动到期。",
    "",
    "|编号|测试样例|预期|实际|正确与否|",
    "|---|---|---|---|---|",
]
for r in sorted(rows, key=lambda r: r["id"]):
    lines.append(
        f"|{r['id']}|{r['example']}|{names.get(r['expected'], r['expected'])}|{names.get(r['actual'], r['actual'])}|{'正确' if r['correct'] else '错误'}|"
    )
(out / "report.md").write_text("\n".join(lines) + "\n")
print(
    json.dumps({"output": str(out), "summary": summary}, ensure_ascii=False), flush=True
)
