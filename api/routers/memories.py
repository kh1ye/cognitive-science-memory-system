"""Memory records, audit history, and retention maintenance."""

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
):
    return {
        "items": memory.list_memories(
            user_id, include_archived=include_archived, limit=limit
        )
    }


@router.post("/memories", status_code=201)
def add_memory(payload: MemoryRequest, memory: MemoryDependency):
    return memory.add_memory(payload.model_dump(exclude_unset=True))


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
