"""Memory retrieval endpoints."""

from fastapi import APIRouter

from ..dependencies import MemoryDependency
from ..schemas import SearchRequest

router = APIRouter(prefix="/api", tags=["retrieval"])


@router.post("/search")
def search(payload: SearchRequest, memory: MemoryDependency):
    return memory.search(
        payload.user_id,
        payload.query,
        payload.top_k,
        payload.active_goal,
        payload.recent_focus,
    )
