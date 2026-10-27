"""Short-term conversation state and validated long-term memory candidates."""

from typing import Any, Literal

from langgraph.graph import MessagesState
from pydantic import BaseModel, ConfigDict, Field


class MemoryCandidate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    content: str = Field(
        min_length=1, max_length=2000, description="用户本轮原文中的连续片段"
    )
    memory_key: str = Field(
        default="",
        max_length=100,
        description="稳定的主题标识，同一主题始终使用相同标识",
    )
    memory_value: str = Field(default="", max_length=500)
    memory_type: Literal["semantic", "episodic", "procedural"] = "semantic"
    tags: list[str] = Field(default_factory=list, max_length=8)
    importance: float = Field(default=0.7, ge=0, le=1)
    confidence: float = Field(default=0.8, ge=0, le=1)
    sensitive: bool = Field(
        default=False, description="是否包含医疗、证件号码、密码或财务账户等敏感信息"
    )


class MemoryExtraction(BaseModel):
    memories: list[MemoryCandidate] = Field(default_factory=list, max_length=3)


class ConversationState(MessagesState):
    user_id: str
    thread_id: str
    auto_remember: bool
    references: list[dict[str, Any]]
    memory_results: list[dict[str, Any]]
    warnings: list[str]
    memory_status: str
