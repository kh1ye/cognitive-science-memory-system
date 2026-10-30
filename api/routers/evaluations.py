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
