"""Local evaluation registry, archived results and one owned subprocess at a time."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
from uuid import uuid4

from conversation_agent.llm import LLMSettings

QUALITY = [("AFA", "原子事实准确率", "准确性"), ("UMRR", "无依据记忆拒认率", "准确性"),
           ("FSRC", "固定状态回答一致率", "一致性"), ("SCHR", "同时冲突处置率", "一致性"),
           ("TIC", "任务意图回应覆盖率", "相关性"), ("AFP", "回答聚焦精确率", "相关性"),
           ("CVSAR", "当前有效状态采用率", "时效性"), ("CR-AUC", "条件保持曲线面积", "保持性")]


def load(path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return default


class EvaluationCenter:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.lock = threading.RLock()
        self.jobs = {}
        self.process = None

    def datasets(self):
        return [
            {"id": "vatsalabench", "name": "Vatsalabench", "count": 500, "label": "长期记忆 · 六维评测",
             "description": "完整历史回放，检查事实回忆、冲突、更新与长期保持。", "color": "violet",
             "metrics": [q[0] for q in QUALITY] + ["L95", "ATC", "SAF"], "modes": ["check", "full"], "version": "500 samples · handoff v1"},
            {"id": "memory-150", "name": "记忆分类与过滤", "count": 150, "label": "四类概念 · 存储策略",
             "description": "120 条记忆概念分类，30 条低价值输入的真实聊天过滤测试。", "color": "green",
             "metrics": ["分类准确率", "低价值过滤率"], "modes": ["check", "full"], "version": "memory-150-v1"},
            {"id": "concept-100", "name": "记忆概念基础集", "count": 100, "label": "概念识别 · 基础检查",
             "description": "四种记忆各 25 条生活化例子，检查分类边界。", "color": "amber",
             "metrics": ["Accuracy", "Macro F1"], "modes": ["check", "full"], "version": "examples-v3"},
        ]

    def dataset_dir(self, dataset):
        names = {"vatsalabench": "Vatsalabench", "memory-150": "memory-150", "concept-100": "project-memory-100"}
        if dataset not in names:
            raise ValueError("未知数据集")
        return self.root / "evaluation" / names[dataset]

    def _metric_rows(self, values):
        rows = []
        for key, name, dimension in QUALITY:
            if key not in values:
                continue
            item = values[key]
            if not isinstance(item, dict):
                item = {"value": item}
            rows.append({"key": key, "name": name, "dimension": dimension, "unit": "number" if key == "CR-AUC" else "percent", **item})
        return rows

    def _record(self, dataset, folder):
        aggregate = load(folder / "aggregate.json")
        result = load(folder / "results.json")
        summary = load(folder / "summary.json")
        check = load(folder / "preflight.json")
        comparison = load(folder / "comparison.json")
        batch_record = load(folder / "batch.json")
        if not any(x is not None for x in (aggregate, result, summary, check, comparison, batch_record)):
            return None
        relative = folder.relative_to(self.root).as_posix()
        item = {"id": hashlib.sha256(relative.encode()).hexdigest()[:18], "dataset": dataset,
                "name": folder.name, "path": relative, "metrics": [], "kind": "quality", "status": "completed",
                "created_at": datetime.fromtimestamp(folder.stat().st_mtime).astimezone().isoformat(),
                "model": "", "completed": 0, "planned": 0, "review": "unreviewed"}
        stamp = re.search(r"(20\d{6})-(\d{6})", folder.name)
        if stamp:
            item["created_at"] = datetime.strptime("".join(stamp.groups()), "%Y%m%d%H%M%S").isoformat() + "+08:00"
        if aggregate is not None or batch_record is not None:
            batch = batch_record or {}
            aggregate = aggregate or {}
            completed = sum(len(load(folder / e["sample_id"] / "results.json", {}).get("results", [])) == 12 for e in batch.get("selected", []))
            item.update(kind="batch", completed=aggregate.get("scored_samples", completed), planned=aggregate.get("planned_samples", len(batch.get("selected", []))), metrics=self._metric_rows(aggregate.get("quality", {})))
            item["status"] = "partial" if any(r.get("exit_code") for r in batch.get("runs", [])) or item["completed"] < item["planned"] else "completed"
            first = next((load(folder / s["sample_id"] / "results.json", {}) for s in batch.get("selected", []) if (folder / s["sample_id"] / "results.json").exists()), {})
            item["model"] = first.get("requested_model", "")
            audited = [load(p) for p in folder.glob("*/scores.json")]
            item["review"] = "reviewed" if audited and all(x and x.get("manual_audit") for x in audited) else "model"
        elif check is not None:
            item.update(kind="check", completed=check.get("checked_samples", 0), planned=check.get("declared_samples", 0), status="failed" if check.get("samples_with_errors") else "completed")
        elif comparison is not None:
            item.update(kind="comparison", completed=2, planned=2)
        elif result is not None:
            scores = load(folder / "scores.json", {})
            item.update(completed=len(result.get("results", [])), planned=12, model=result.get("requested_model", ""),
                        status="failed" if result.get("status") == "incomplete" else "completed", metrics=self._metric_rows(scores.get("quality", {})))
        elif summary is not None:
            config = load(folder / "manifest.json", {})
            item.update(model=summary.get("model") or config.get("model", ""), completed=summary.get("total", summary.get("attempted", 0)), planned=150 if dataset == "memory-150" else 100)
            item["status"] = "partial" if summary.get("api_errors") else "completed"
            if dataset == "memory-150":
                categories = summary.get("categories", {})
                n = sum(v["total"] for k, v in categories.items() if k != "low_value")
                correct = sum(v["correct"] for k, v in categories.items() if k != "low_value")
                item["metrics"] = [{"key": "分类准确率", "name": "概念分类准确率", "dimension": "分类", "value": correct/n if n else None, "unit": "percent", "valid_n": n},
                    {"key": "低价值过滤率", "name": "低价值输入过滤", "dimension": "过滤", "value": categories.get("low_value", {}).get("accuracy"), "unit": "percent", "valid_n": categories.get("low_value", {}).get("total", 0)}]
            else:
                item["metrics"] = [{"key": "Accuracy", "name": "分类准确率", "dimension": "分类", "value": summary.get("accuracy"), "unit": "percent", "valid_n": item["completed"]},
                    {"key": "Macro F1", "name": "宏平均 F1", "dimension": "分类", "value": summary.get("macro_f1"), "unit": "number", "valid_n": item["completed"]}]
        item["_folder"] = folder
        return item

    def _records(self, dataset=None):
        records = []
        for info in self.datasets():
            if dataset and dataset != info["id"]:
                continue
            root = self.dataset_dir(info["id"]) / "results"
            if not root.exists():
                continue
            for folder in root.iterdir():
                if not folder.is_dir():
                    continue
                candidates = [folder, folder / "run", folder / "batch"] if folder.name.startswith("center-") else [folder]
                for candidate in candidates:
                    item = self._record(info["id"], candidate) if candidate.exists() else None
                    if item:
                        records.append(item)
        return sorted(records, key=lambda x: x["created_at"], reverse=True)

    def history(self, dataset=None):
        return [{k: v for k, v in r.items() if k != "_folder"} for r in self._records(dataset)]

    def _find(self, run_id):
        item = next((r for r in self._records() if r["id"] == run_id), None)
        if item is None:
            raise ValueError("评测记录不存在")
        return item

    def detail(self, run_id):
        item = self._find(run_id)
        folder = item.pop("_folder")
        samples = []
        batch = load(folder / "batch.json", {})
        aggregate = load(folder / "aggregate.json", {})
        if item["kind"] == "batch":
            for entry in batch.get("selected", []):
                sid = entry["sample_id"]
                run = load(folder / sid / "results.json", {})
                scores = load(folder / sid / "scores.json", {})
                samples.append({"id": sid, "completed": len(run.get("results", [])), "planned": 12,
                    "status": "failed" if run.get("status") == "incomplete" else "completed",
                    "error": run.get("error", {}).get("message", ""), "metrics": self._metric_rows(scores.get("quality", {}))})
            resource = aggregate.get("resource", {})
            cohort = resource.get("completed_cohort_only", {})
            item["efficiency"] = {"samples": cohort.get("samples", 0), "planned_samples": item["planned"],
                "L95": resource.get("L95_seconds") if resource.get("L95_seconds") is not None else cohort.get("L95_seconds"),
                "ATC": resource.get("ATC_tokens_per_query") if resource.get("ATC_tokens_per_query") is not None else cohort.get("ATC_tokens_per_query"),
                "SAF": cohort.get("SAF_pooled", resource.get("SAF_pooled")),
                "conditional": resource.get("L95_seconds") is None}
        elif item["dataset"] == "vatsalabench" and item["kind"] == "quality":
            run = load(folder / "results.json", {})
            samples = [{"id": run.get("sample_id", "sample"), "completed": len(run.get("results", [])), "planned": 12,
                        "status": item["status"], "error": run.get("error", {}).get("message", "")}]
        item.update(samples=samples, report=(folder / "report.md").read_text(encoding="utf-8") if (folder / "report.md").exists() else "",
                    config=load(folder / "manifest.json") or load(folder / "metadata.json") or {k: v for k, v in batch.items() if k != "selected"})
        if item["kind"] == "check":
            item["check"] = load(folder / "preflight.json", {})
        return item

    def sample(self, run_id, sample_id):
        item = self._find(run_id)
        folder = item["_folder"]
        if item["kind"] == "batch":
            allowed = {s["sample_id"] for s in load(folder / "batch.json", {}).get("selected", [])}
            if sample_id not in allowed:
                raise ValueError("样本不存在")
            folder = folder / sample_id
        elif item["dataset"] != "vatsalabench":
            raise ValueError("当前记录没有历史回放样本")
        run = load(folder / "results.json", {})
        if run.get("sample_id") != sample_id:
            raise ValueError("样本不存在")
        scores = load(folder / "scores.json", {})
        gold = {}
        source = self.dataset_dir("vatsalabench") / "dataset500_handoff_20261022_v1" / "dataset500_handoff_20261022_v1"
        inventory = load(source / "index.json", {})
        entry = next((s for s in inventory.get("samples", []) if s["sample_id"] == sample_id), None)
        if entry:
            gold = load(source / entry["package_folder"] / "private" / sample_id / "gold.json", {}).get("labels", {})
        judgment = {x["probe_id"]: x for x in scores.get("judgment", {}).get("answers", [])}
        answers = []
        for row in run.get("results", []):
            answers.append({"id": row["probe_id"], "question": row["question"], "answer": row["answer"],
                "gold": row.get("scoring_reference") or gold.get(row["probe_id"]), "verdict": judgment.get(row["probe_id"]),
                "seconds": row.get("seconds"), "references": [{"module": r.get("module"), "content": r.get("content"),
                    "evidence_context": r.get("evidence_context", ""), "id": r.get("id")} for r in row.get("references", [])]})
        return {"id": sample_id, "answers": answers, "error": run.get("error"), "ingestion_count": len(run.get("ingestion", [])),
                "failed_operations": sum(o.get("status") == "failed" for r in run.get("ingestion", []) for o in r["result"]["operations"])}

    def flat_predictions(self, run_id):
        item = self._find(run_id)
        path = item["_folder"] / "predictions.jsonl"
        rows = []
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
        return rows

    def _save_job(self, job):
        path = self.root / job["path"] / "job.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    def job_list(self):
        # Recover historical tasks without assuming an old process is still owned.
        with self.lock:
            result = dict(self.jobs)
            for dataset in self.datasets():
                for path in (self.dataset_dir(dataset["id"]) / "results").glob("center-*/job.json"):
                    stored = load(path)
                    if stored and stored["id"] not in result:
                        if stored["status"] in ("running", "queued"):
                            stored["status"] = "interrupted"
                        result[stored["id"]] = stored
            return sorted([dict(j) for j in result.values()], key=lambda j: j["created_at"], reverse=True)

    def start(self, payload):
        dataset = payload.dataset
        info = next((d for d in self.datasets() if d["id"] == dataset), None)
        if info is None or payload.mode not in info["modes"]:
            raise ValueError("不支持的数据集或评测模式")
        settings = LLMSettings.from_env()
        key = payload.api_key.get_secret_value() or settings.api_key
        if payload.mode != "check" and not key:
            raise ValueError("请填写模型 API Key，或先配置服务端模型")
        configured_url = settings.base_url or ("https://api.anthropic.com" if settings.provider == "anthropic" else "https://api.openai.com/v1")
        if payload.mode != "check" and not payload.api_key.get_secret_value() and (payload.base_url.rstrip("/") != configured_url.rstrip("/") or payload.provider != settings.provider):
            raise ValueError("模型地址与服务端配置不同，请填写该服务对应的 API Key")
        with self.lock:
            if any(j["status"] in ("queued", "running", "cancelling") for j in self.jobs.values()):
                raise ValueError("已有评测正在运行，请完成或取消后再开始")
            jid = "center-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:6]
            folder = self.dataset_dir(dataset) / "results" / jid
            folder.mkdir(parents=True)
            job = {"id": jid, "dataset": dataset, "mode": payload.mode, "count": payload.count if dataset == "vatsalabench" and payload.mode == "full" else info["count"],
                   "status": "queued", "created_at": datetime.now().astimezone().isoformat(), "path": folder.relative_to(self.root).as_posix(),
                   "model": payload.model if payload.mode != "check" else "", "auto_score": payload.auto_score,
                   "message": "等待启动", "exit_code": None}
            self.jobs[jid] = job
            self._save_job(job)
            env = os.environ.copy()
            env.update(LLM_API_KEY=key, LLM_MODEL=payload.model, LLM_BASE_URL=payload.base_url,
                       LLM_PROVIDER=payload.provider, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
            if dataset != "vatsalabench" and "api.deepseek.com" in payload.base_url:
                env["LLM_THINKING"] = "disabled"
            threading.Thread(target=self._worker, args=(jid, env, key), daemon=True).start()
            return dict(job)

    def _run_command(self, jid, args, env, secret):
        job = self.jobs[jid]
        folder = self.root / job["path"]
        with self.lock:
            if job["status"] == "cancelling":
                return -1
            flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
            process = subprocess.Popen([sys.executable, *args], cwd=self.root, env=env, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", **flags)
            self.process = process
        with (folder / "console.txt").open("a", encoding="utf-8") as log:
            for line in process.stdout:
                safe = line.replace(secret, "[REDACTED]") if secret else line
                log.write(safe)
                log.flush()
                with self.lock:
                    job["message"] = safe.strip()[:250]
                    self._save_job(job)
        code = process.wait()
        with self.lock:
            self.process = None
        return code

    def _worker(self, jid, env, secret):
        job = self.jobs[jid]
        folder = self.root / job["path"]
        try:
            with self.lock:
                if job["status"] == "cancelling":
                    job["status"] = "cancelled"
                    return
                job["status"] = "running"
                self._save_job(job)
            if job["mode"] == "check":
                if job["dataset"] == "vatsalabench":
                    command = ["scripts/vatsalabench_preflight.py", "--output", str(folder / "preflight.json")]
                    code = self._run_command(jid, command, env, secret)
                else:
                    cases = load(self.dataset_dir(job["dataset"]) / "cases.json", {}).get("cases", [])
                    valid = bool(cases) and len({c["id"] for c in cases}) == len(cases)
                    (folder / "preflight.json").write_text(json.dumps({"declared_samples": len(cases), "checked_samples": len(cases), "samples_with_errors": 0 if valid else 1}), encoding="utf-8")
                    code = 0 if valid else 1
            elif job["dataset"] == "vatsalabench":
                code = self._run_command(jid, ["-m", "scripts.vatsalabench_batch", "--count", str(job["count"]), "--output", str(folder / "batch")], env, secret)
                if code == 0 and job["auto_score"] and job["status"] != "cancelling":
                    code = self._run_command(jid, ["-m", "scripts.vatsalabench_score", str(folder / "batch")], env, secret)
            elif job["dataset"] == "memory-150":
                env["EVALUATION_OUTPUT_DIR"] = str(folder / "run")
                code = self._run_command(jid, ["evaluation/memory-150/run_eval.py"], env, secret)
            else:
                code = self._run_command(jid, ["evaluation/project-memory-100/run_concept_eval.py", "--output", str(folder / "run")], env, secret)
            with self.lock:
                job["exit_code"] = code
                job["status"] = "cancelled" if job["status"] == "cancelling" else "completed" if code == 0 else "failed"
                batch = load(folder / "batch" / "batch.json", {})
                if job["status"] == "completed" and any(r.get("exit_code") for r in batch.get("runs", [])):
                    job["status"] = "partial"
                if job["status"] == "completed":
                    check = load(folder / "preflight.json", {})
                    if check:
                        job["count"] = check.get("checked_samples", job["count"])
                        job["message"] = f"数据检查完成 · {job['count']} 条样本"
                    else:
                        job["message"] = "评测完成，结果已归档"
                elif job["status"] == "partial":
                    job["message"] = "评测部分完成，请查看未完成样本"
        except Exception as error:
            with self.lock:
                job["status"] = "failed"
                job["message"] = str(error).replace(secret, "[REDACTED]") if secret else str(error)
        finally:
            with self.lock:
                job["finished_at"] = datetime.now().astimezone().isoformat()
                self._save_job(job)

    def cancel(self, jid):
        with self.lock:
            job = self.jobs.get(jid)
            if not job or job["status"] not in ("running", "queued"):
                raise ValueError("没有可取消的任务")
            job["status"] = "cancelling"
            self._save_job(job)
            process = self.process
        if process and process.poll() is None:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                os.killpg(process.pid, signal.SIGTERM)
        return dict(job)

    def job_detail(self, jid):
        job = next((j for j in self.job_list() if j["id"] == jid), None)
        if not job:
            raise ValueError("任务不存在")
        folder = self.root / job["path"]
        log = folder / "console.txt"
        lines = log.read_text(encoding="utf-8").splitlines()[-100:] if log.exists() else []
        progress = []
        for path in (folder / "batch").glob("*/results.json"):
            run = load(path, {})
            progress.append({"sample_id": run.get("sample_id"), "ingested": len(run.get("ingestion", [])), "answered": len(run.get("results", [])), "status": run.get("status")})
        return {**job, "log": "\n".join(lines), "progress": progress}

    def close(self):
        for jid, job in list(self.jobs.items()):
            if job["status"] in ("queued", "running"):
                self.cancel(jid)
