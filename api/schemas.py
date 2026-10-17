"""Request schemas for validation and generated OpenAPI documentation."""

from typing import Any

from pydantic import BaseModel, ConfigDict


class NamespaceRequest(BaseModel):
    user_id: str = "demo-user"


class MemoryRequest(NamespaceRequest):
    model_config = ConfigDict(extra="allow")

    content: str = ""
    memory_key: str = ""
    memory_value: str = ""
    memory_type: str | None = None
    source: str = "user"
    tags: str | list[Any] | None = None
    importance: float = 0.7
    confidence: float = 0.8
    consent: bool = False
    active_goal: str = ""
    metadata: dict[str, Any] | None = None


class SearchRequest(NamespaceRequest):
    query: str = ""
    top_k: int = 5
    active_goal: str = ""
    recent_focus: str = ""
