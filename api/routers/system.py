"""System health, configuration, and aggregate statistics."""

from fastapi import APIRouter, Request

from ..dependencies import MemoryDependency
from ..settings import SERVICE_NAME

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health():
    return {"status": "ok", "service": SERVICE_NAME, "version": "1.0.0"}


@router.get("/overview")
def overview(request: Request, memory: MemoryDependency, user_id: str = "demo-user"):
    result = memory.overview(user_id)
    agent = request.app.state.conversation_agent
    for module in result["modules"]:
        if module["name"] == "语言模型":
            module["status"] = "ready" if agent.configured else "unconfigured"
            module["description"] = (
                f"LangChain · {agent.settings.model}"
                if agent.configured
                else "请配置 LLM_API_KEY 后重启服务"
            )
    return result


@router.get("/config")
def config(memory: MemoryDependency, user_id: str = "demo-user"):
    return memory.stats(user_id)["config"]


@router.get("/stats")
def stats(memory: MemoryDependency, user_id: str = "demo-user"):
    return memory.stats(user_id)
