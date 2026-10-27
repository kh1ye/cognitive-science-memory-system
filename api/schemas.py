"""Request schemas for validation and generated OpenAPI documentation."""

from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator
from cognitive_memory import MemoryType


class NamespaceRequest(BaseModel):
    user_id: str = "demo-user"


class MemoryRequest(NamespaceRequest):
    model_config = ConfigDict(extra="allow")

    content: str = ""
    memory_key: str = ""
    memory_value: str = ""
    memory_type: MemoryType | None = None
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


class SessionRequest(BaseModel):
    user_id: str = Field(default="demo-user", min_length=1, max_length=100)
    thread_id: str = Field(
        default_factory=lambda: str(uuid4()),
        pattern=r"^[A-Za-z0-9_-]{1,100}$",
    )

    @field_validator("user_id")
    @classmethod
    def normalize_user(cls, value):
        value = value.strip().lower()
        if not value:
            raise ValueError("user_id 不能为空")
        return value


class ChatRequest(SessionRequest):
    message: str = Field(min_length=1, max_length=10000)
    auto_remember: bool = True
    task_id: str | None = None
    source_event_id: str | None = None
    retention_policy: Literal["persist", "no_long_term", "no_persist"] = "persist"

    @field_validator("message")
    @classmethod
    def nonempty_message(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("message 不能为空")
        return value
