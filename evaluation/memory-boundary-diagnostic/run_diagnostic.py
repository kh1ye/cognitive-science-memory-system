"""Post-hoc same-model diagnostic; never modifies the original scored dataset."""

import hashlib
import json
import random
import runpy
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from conversation_agent.llm import LLMSettings

ROOT = Path(__file__).parent
EVALUATION = ROOT.parent
BASE = runpy.run_path(str(EVALUATION / "project-memory-100/run_concept_eval.py"))
Prediction = BASE["Prediction"]
ORIGINAL_PROMPT = BASE["PROMPT"]
BOUNDARY_NOTE = """
补充统一判据（不是具体样本的答案）：
区分知识的陈述与技能的实施。能说出操作顺序、知道某人的惯常做法，本身只说明陈述性知识；明确表现已掌握并可实施的技能，才按程序性记忆判断。
个人背景或特征不因涉及过去、时间或动作就自动成为情景或程序性记忆。情景记忆的重点是具体的一次经历；背景事实的陈述属于语义记忆。
不要仅凭主题或动词分类。如果整句确有两种合理解释而无法确定重点，允许选unknown。
"""
PARAPHRASES = {
    "N052": "我是在南京上的大学。",
    "N058": "我是在小学开始学游泳的。",
    "N060": "写字我一向用左手。",
    "N063": "这道菜怎么做我知道：鸡蛋先炒，番茄后放。",
    "N064": "折纸鹤先把方纸沿对角线折一下，这一步我还记得。",
    "N073": "我外婆做红烧肉，总是先焯水，再炒糖色。",
}
CONTROLS = ["N001", "N003", "N026", "N027", "N051", "N055", "N076", "N090"]
PROMPTS = {"original": ORIGINAL_PROMPT, "clarified": ORIGINAL_PROMPT + BOUNDARY_NOTE}


def predict(trial):
    started = time.monotonic()
    try:
        model = LLMSettings.from_env().create_model()
        response = model.with_structured_output(Prediction, include_raw=True).invoke([
            SystemMessage(content=PROMPTS[trial["prompt"]]),
            HumanMessage(content=trial["example"]),
        ])
        parsed = response.get("parsed") if isinstance(response, dict) and "parsed" in response else response
        prediction = Prediction.model_validate(parsed)
        raw = response.get("raw") if isinstance(response, dict) else None
        return {**trial, "predicted": prediction.label, "reason": prediction.reason,
                "status": "ok", "reference_match": prediction.label == trial["reference"],
                "usage": getattr(raw, "usage_metadata", None),
                "elapsed_seconds": round(time.monotonic()-started, 3)}
    except Exception as error:
        return {**trial, "predicted": "error", "reason": "", "status": "error",
                "reference_match": False, "error_type": type(error).__name__,
                "http_status": getattr(error, "status_code", None),
                "elapsed_seconds": round(time.monotonic()-started, 3)}


def main():
    data_bytes = (EVALUATION / "project-memory-challenge-100/cases.json").read_bytes()
    data = json.loads(data_bytes)
    assert data["version"] == "natural-v2"
    cases = {c["id"]: c for c in data["cases"]}
    prior = json.loads((EVALUATION / "project-memory-challenge-100/results/20261027-230557/summary.json").read_text())
    assert hashlib.sha256(data_bytes).hexdigest() == prior["dataset_sha256"]
    assert set(prior["wrong_ids"]) == set(PARAPHRASES)
    assert hashlib.sha256(ORIGINAL_PROMPT.encode()).hexdigest() == prior["prompt_sha256"]
    trials = []
    for prompt in PROMPTS:
        for case_id in [*PARAPHRASES, *CONTROLS]:
            for repeat in range(1, 4):
                trials.append({"trial_id": f"{prompt}-original-{case_id}-{repeat}",
                               "case_id": case_id, "subset": "disputed" if case_id in PARAPHRASES else "control",
                               "prompt": prompt, "wording": "original", "repeat": repeat,
                               "example": cases[case_id]["example"], "reference": cases[case_id]["memory_type"]})
    for case_id, example in PARAPHRASES.items():
        for repeat in range(1, 4):
            trials.append({"trial_id": f"original-paraphrase-{case_id}-{repeat}", "case_id": case_id,
                           "subset": "disputed", "prompt": "original", "wording": "paraphrase", "repeat": repeat,
                           "example": example, "reference": cases[case_id]["memory_type"]})
    assert len(trials) == len({t["trial_id"] for t in trials}) == 102
    settings = LLMSettings.from_env()
    if not settings.api_key:
        raise SystemExit("No API key configured")
    stamp = datetime.now(timezone(timedelta(hours=8)))
    output = ROOT / "results" / stamp.strftime("%Y%m%d-%H%M%S")
    output.mkdir(parents=True, exist_ok=False)
    plan = {"started_at": stamp.isoformat(), "provider": settings.provider, "model": settings.model,
            "dataset_version": data["version"], "dataset_sha256": prior["dataset_sha256"],
            "prompt_sha256": {k: hashlib.sha256(v.encode()).hexdigest() for k,v in PROMPTS.items()},
            "seed": 20261027, "workers": 4, "temperature": "provider_default", "trials": trials,
            "purpose": "post_hoc_same_model_boundary_diagnostic", "repeats": 3,
            "limitations": ["依据已知6条分歧设计的事后诊断，不是新留出集，也不能作为通用准确率。",
                            "补充判据针对已知边界，是提示干预；改写可能改变重点，无法完全隔离因果。",
                            "没有另一供应商模型、独立专家金标准或盲法裁决。",
                            "参考标签仅用于描述一致率；N058等存在合理解释空间。",
                            "默认温度未显式固定，每条独立调用；SDK可能重试传输。"]}
    (output / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n")
    for name, prompt in PROMPTS.items():
        (output / f"prompt-{name}.txt").write_text(prompt + "\n")
    manifest = {"plan_sha256": hashlib.sha256((output / "plan.json").read_bytes()).hexdigest(),
                "fixed_before_calls": True, "trial_count": len(trials)}
    (output / "frozen-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    random.Random(plan["seed"]).shuffle(trials)
    print(f"Output: {output.resolve()}", flush=True)
    started = time.monotonic()
    rows = []
    with (output / "predictions.jsonl").open("w") as file, ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(predict, trial) for trial in trials]
        for future in as_completed(futures):
            row = future.result()
            rows.append(row)
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
            file.flush()
            if len(rows) % 10 == 0:
                print(json.dumps({"completed": len(rows), "errors": sum(r["status"] == "error" for r in rows)}), flush=True)
    cells = defaultdict(list)
    for row in rows:
        cells[(row["subset"], row["prompt"], row["wording"])].append(row)
    aggregates = []
    for (subset, prompt, wording), cell in sorted(cells.items()):
        aggregates.append({"subset": subset, "prompt": prompt, "wording": wording, "calls": len(cell),
                           "reference_matches": sum(r["reference_match"] for r in cell),
                           "label_counts": dict(Counter(r["predicted"] for r in cell))})
    per_case = {}
    for case_id in [*PARAPHRASES, *CONTROLS]:
        per_case[case_id] = {"example": cases[case_id]["example"], "reference": cases[case_id]["memory_type"],
                             "paraphrase": PARAPHRASES.get(case_id), "conditions": {}}
        for prompt, wording in [("original", "original"), ("original", "paraphrase"), ("clarified", "original")]:
            cell = sorted([r for r in rows if r["case_id"] == case_id and r["prompt"] == prompt and r["wording"] == wording], key=lambda r:r["repeat"])
            if cell:
                per_case[case_id]["conditions"][f"{prompt}/{wording}"] = {"predictions": [r["predicted"] for r in cell], "reference_matches": sum(r["reference_match"] for r in cell)}
    summary = {"status": "completed", "model": settings.model, "attempted": len(rows),
               "api_errors": sum(r["status"] == "error" for r in rows),
               "elapsed_seconds": round(time.monotonic()-started, 3), "aggregates": aggregates,
               "per_case": per_case, "limitations": plan["limitations"]}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    names = BASE["NAMES"]
    lines = ["# 六条记忆分类分歧：事后对照诊断", "", f"模型：{settings.model}；调用：{len(rows)}次；错误：{summary['api_errors']}次。", "",
             "同一模型、同一输出格式；原样本3次、语序改写3次、补充边界判据3次。另有8条已答对样本，在两种提示下各3次作对照。", "",
             "这是对已知错误的定向诊断，补充提示与改写均在看到错误后设计；不得据此宣称通用性能提高。参考标签并非独立金标准。", "",
             "|样本组|提示|措辞|与参考标签一致/调用数|", "|---|---|---|---:|"]
    for cell in aggregates:
        lines.append(f"|{cell['subset']}|{cell['prompt']}|{cell['wording']}|{cell['reference_matches']}/{cell['calls']}|")
    lines += ["", "## 逐条分布", "", "|编号|原句|参考|原提示3次|语序改写3次|补充判据3次|", "|---|---|---|---|---|---|"]
    for case_id, result in per_case.items():
        conditions = result["conditions"]
        values = []
        for condition in ["original/original", "original/paraphrase", "clarified/original"]:
            predictions = conditions.get(condition, {}).get("predictions", [])
            values.append("、".join(names[p] for p in predictions) if predictions else "未设置")
        lines.append(f"|{case_id}|{result['example']}|{names[result['reference']]}|{'|'.join(values)}|")
    lines += ["", "## 改写原文", ""]
    for case_id, paraphrase in PARAPHRASES.items():
        lines.append(f"- {case_id}：{paraphrase}")
    lines += ["", "## 限制", "", *[f"- {limitation}" for limitation in plan["limitations"]], "",
              "全部原始逐次预测与简短依据见 predictions.jsonl；实验计划、提示和哈希均在调用前保存。"]
    (output / "report.md").write_text("\n".join(lines) + "\n")
    (ROOT / "results/latest.json").write_text(json.dumps({"output": str(output.resolve())}, indent=2) + "\n")
    print(json.dumps({"attempted": len(rows), "errors": summary["api_errors"], "aggregates": aggregates,
                      "report": str((output / "report.md").resolve())}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
