"""System health, configuration, and aggregate statistics."""

from fastapi import APIRouter, Request
from cognitive_memory.retrieval.lexical import normalize_text

from ..dependencies import MemoryDependency
from ..settings import SERVICE_NAME

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health():
    return {"status": "ok", "service": SERVICE_NAME, "version": "1.0.0"}


@router.get("/overview")
def overview(request: Request, memory: MemoryDependency, user_id: str = "demo-user"):
    user_id = normalize_text(user_id) or "demo-user"
    result = memory.overview(user_id)
    with memory.storage.transaction():
        for event in result["recent_activity"]:
            event["related_memory"] = None
            memory_id = event.get("memory_id")
            if (
                event["event_type"] != "USER_DELETE"
                and memory_id
                and memory.storage.find_owned(memory_id, user_id)
            ):
                record = memory.storage.get_memory(memory_id)
                if record:
                    event["related_memory"] = {
                        key: record[key]
                        for key in ("id", "content", "memory_type", "state_role")
                    }
    agent = request.app.state.conversation_agent
    for module in result["modules"]:
        if module["name"] == "语言模型":
            if agent.settings.provider not in {"openai", "anthropic"}:
                module["status"] = "unsupported"
                module["description"] = "提供方配置不受支持，请使用 openai 或 anthropic"
            elif agent.configured:
                module["status"] = "configured"
                module["description"] = f"LangChain · {agent.settings.model} · 尚未验证连接"
            else:
                module["status"] = "unconfigured"
                module["description"] = "未配置密钥；记忆管理与本地检索仍可使用"
        elif module["name"] == "向量模型":
            module["status"] = "not_implemented"
            module["description"] = "当前版本使用词法召回，尚未实现向量检索"
    return result


@router.get("/config")
def config(memory: MemoryDependency, user_id: str = "demo-user"):
    return memory.stats(user_id)["config"]


@router.get("/stats")
def stats(memory: MemoryDependency, user_id: str = "demo-user"):
    return memory.stats(user_id)
