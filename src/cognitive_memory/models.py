from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TypedDict


class MemoryRecord(TypedDict):
    id: str
    user_id: str
    content: str
    normalized_content: str
    memory_key: str | None
    memory_value: str | None
    memory_type: str
    state_role: str
    source: str
    tags: list[str]
    importance: float
    confidence: float
    saliency: float
    goal_relevance: float
    preference_strength: float
    attention_bias: float
    write_score: float
    prediction_error: float
    evidence_count: int
    parent_id: str | None
    support_ids: list[str]
    is_protected: bool
    created_at: str
    updated_at: str
    last_accessed_at: str | None
    metadata: dict[str, Any]


class WriteResult(TypedDict, total=False):
    decision: str
    reason: str
    memory: MemoryRecord | None
    previous_current_id: str
    support_ids: list[str]
    gate: dict[str, Any]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat(timespec="seconds")
