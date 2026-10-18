"""System health, configuration, and aggregate statistics."""

from fastapi import APIRouter

from ..dependencies import MemoryDependency
from ..settings import SERVICE_NAME

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health():
    return {"status": "ok", "service": SERVICE_NAME, "version": "1.0.0"}


@router.get("/overview")
def overview(memory: MemoryDependency, user_id: str = "demo-user"):
    return memory.overview(user_id)


@router.get("/config")
def config(memory: MemoryDependency, user_id: str = "demo-user"):
    return memory.stats(user_id)["config"]


@router.get("/stats")
def stats(memory: MemoryDependency, user_id: str = "demo-user"):
    return memory.stats(user_id)
