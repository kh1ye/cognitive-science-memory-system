"""Memory records, audit history, and retention maintenance."""

from typing import Literal

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from ..dependencies import MemoryDependency
from ..schemas import MemoryRequest, NamespaceRequest

router = APIRouter(prefix="/api", tags=["memories"])


@router.get("/memories")
def memories(
    memory: MemoryDependency,
    user_id: str = "demo-user",
    include_archived: bool = False,
    limit: int = Query(200, ge=1, le=1000),
    view: Literal["legacy", "all"] = "legacy",
):
    return {
        "items": (
            memory.catalog.list
            if view == "all" and memory.catalog is not None
            else memory.list_memories
        )(user_id, include_archived=include_archived, limit=limit)
    }


@router.post("/memories", status_code=201)
def add_memory(payload: MemoryRequest, memory: MemoryDependency):
    return memory.add_memory(payload.model_dump(exclude_unset=True))


@router.get("/memories/{memory_id}/evidence")
def evidence(memory_id: str, memory: MemoryDependency, user_id: str = "demo-user"):
    result = memory.evidence(user_id, memory_id)
    if result is None and memory.catalog is not None:
        result = memory.catalog.evidence(user_id, memory_id)
    return (
        result
        if result is not None
        else JSONResponse(
            {"error": "not_found", "message": "记忆不存在"}, status_code=404
        )
    )


@router.get("/memories/{memory_id}")
def get_memory(memory_id: str, memory: MemoryDependency, user_id: str = "demo-user"):
    from cognitive_memory.retrieval.lexical import normalize_text

    with memory.storage.transaction():
        if memory.storage.find_owned(memory_id, normalize_text(user_id) or "demo-user"):
            return memory.storage.get_memory(memory_id)
        if memory.catalog is not None:
            record = memory.catalog.get(user_id, memory_id)
            if record is not None:
                return record
    return JSONResponse(
        {"error": "not_found", "message": "记忆不存在或已删除"}, status_code=404
    )


@router.delete("/memories/{memory_id}")
def delete(memory_id: str, memory: MemoryDependency, user_id: str = "demo-user"):
    if memory.delete_memory(user_id, memory_id):
        return {"deleted": True, "memory_id": memory_id}
    return JSONResponse({"deleted": False, "message": "记忆不存在"}, status_code=404)


@router.get("/audit")
def audit(memory: MemoryDependency, user_id: str = "demo-user"):
    return {"items": memory.list_audit(user_id)}


@router.post("/maintenance/retention")
def retention(memory: MemoryDependency, payload: NamespaceRequest | None = None):
    return memory.run_retention((payload or NamespaceRequest()).user_id)
