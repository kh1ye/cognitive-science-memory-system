"""Development evaluation endpoints; launch/cancel only from local clients."""
from typing import Literal
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, SecretStr, field_validator

from conversation_agent.llm import LLMSettings

router = APIRouter(prefix="/api/evaluations", tags=["evaluation"])


class TaskRequest(BaseModel):
    dataset: Literal["vatsalabench", "memory-150", "concept-100"]
    mode: Literal["check", "full"] = "check"
    count: int = Field(default=1, ge=1, le=5)
    model: str = Field(default="deepseek-v4-flash", min_length=1, max_length=120)
    base_url: str = "https://api.deepseek.com"
    provider: Literal["openai", "anthropic"] = "openai"
    api_key: SecretStr = SecretStr("")
    auto_score: bool = True

    @field_validator("base_url")
    @classmethod
    def valid_url(cls, value):
        parsed = urlparse(value)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("请输入有效的模型服务地址")
        return value


def center(request):
    return request.app.state.evaluation_center


def require_local(request):
    if request.client is None or request.client.host not in ("127.0.0.1", "::1"):
        raise HTTPException(403, "评测任务只能从本机启动或取消")


@router.get("/datasets")
def datasets(request: Request):
    settings = LLMSettings.from_env()
    return {"items": center(request).datasets(), "model_configured": bool(settings.api_key), "configured_model": settings.model,
            "configured_provider": settings.provider, "configured_base_url": settings.base_url or ("https://api.anthropic.com" if settings.provider == "anthropic" else "https://api.openai.com/v1")}


@router.get("/runs")
def history(request: Request, dataset: str | None = None):
    if dataset:
        center(request).dataset_dir(dataset)
    return {"items": center(request).history(dataset)}


@router.get("/runs/{run_id}")
def detail(run_id: str, request: Request):
    return center(request).detail(run_id)


@router.get("/runs/{run_id}/samples/{sample_id}")
def sample(run_id: str, sample_id: str, request: Request):
    return center(request).sample(run_id, sample_id)


@router.get("/runs/{run_id}/predictions")
def predictions(run_id: str, request: Request):
    return {"items": center(request).flat_predictions(run_id)}


@router.get("/tasks")
def tasks(request: Request):
    return {"items": center(request).job_list()}


@router.post("/tasks", status_code=202)
def start(payload: TaskRequest, request: Request):
    require_local(request)
    return center(request).start(payload)


@router.get("/tasks/{job_id}")
def task(job_id: str, request: Request):
    return center(request).job_detail(job_id)


@router.post("/tasks/{job_id}/cancel")
def cancel(job_id: str, request: Request):
    require_local(request)
    return center(request).cancel(job_id)


class UploadedDataset(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    content: str = Field(max_length=1000000)


@router.post("/uploads", status_code=201)
def upload_dataset(payload: UploadedDataset, request: Request):
    import json
    from uuid import uuid4
    from datetime import datetime, timezone
    try:
        try:
            raw = json.loads(payload.content)
        except ValueError:
            raw = [json.loads(line) for line in payload.content.splitlines() if line.strip()]
        cases = raw.get("cases") if isinstance(raw, dict) else raw
        if not isinstance(cases, list) or not 1 <= len(cases) <= 500:
            raise ValueError("请提供 1～500 条样本")
        normalized = []
        for i, item in enumerate(cases):
            if not isinstance(item, dict):
                raise ValueError(f"第 {i+1} 条必须是对象")
            text = item.get("text", item.get("example"))
            expected = item.get("expected", item.get("label"))
            if not isinstance(text, str) or not 1 <= len(text.strip()) <= 10000:
                raise ValueError(f"第 {i+1} 条 text 无效")
            if expected not in ("working", "episodic", "semantic", "procedural", "unknown"):
                raise ValueError(f"第 {i+1} 条 expected 必须是支持的记忆类型")
            normalized.append({"text": text.strip(), "expected": expected})
    except (ValueError, TypeError) as error:
        raise HTTPException(422, str(error))
    identifier = uuid4().hex
    folder = center(request).root / "evaluation" / "uploads" / identifier
    folder.mkdir(parents=True)
    record = {"id": identifier, "name": payload.name, "count": len(normalized), "cases": normalized,
              "created_at": datetime.now(timezone.utc).isoformat()}
    (folder / "dataset.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"id": identifier, "name": payload.name, "count": len(normalized)}


@router.post("/uploads/{identifier}/run")
def run_uploaded(identifier: str, request: Request):
    require_local(request)
    import json, re, time
    from uuid import uuid4
    from conversation_agent.memory_concepts import classify_memory_concept
    if not re.fullmatch(r"[a-f0-9]{32}", identifier):
        raise HTTPException(404, "数据集不存在")
    folder = center(request).root / "evaluation" / "uploads" / identifier
    if not (folder / "dataset.json").exists():
        raise HTTPException(404, "数据集不存在")
    settings = LLMSettings.from_env()
    if not settings.api_key:
        raise HTTPException(422, "请先配置评测模型密钥")
    dataset = json.loads((folder / "dataset.json").read_text(encoding="utf-8"))
    model = settings.create_model()
    results = []
    # First version caps each explicit run to 20 samples, preserving original order.
    for case in dataset["cases"][:20]:
        start = time.monotonic()
        try:
            prediction, usage = classify_memory_concept(model, case["text"])
            results.append({**case, "actual": prediction.label, "reason": prediction.reason,
                            "correct": prediction.label == case["expected"], "seconds": time.monotonic()-start})
        except Exception:
            results.append({**case, "actual": None, "correct": False, "error": "模型调用失败"})
    report = {"id": uuid4().hex, "dataset": identifier, "model": settings.model, "planned": len(results),
              "total": dataset["count"], "accuracy": sum(r["correct"] for r in results)/len(results),
              "failed": sum("error" in r for r in results), "results": results}
    output = folder / "results" / report["id"]
    output.mkdir(parents=True)
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
