from __future__ import annotations

from enum import Enum


class MemoryType(str, Enum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"


class StateRole(str, Enum):
    WORKING = "working"
    CURRENT = "current"
    CANDIDATE = "candidate"
    HISTORY = "history"
    ARCHIVED = "archived"


MEMORY_TYPES = {item.value for item in MemoryType}
STATE_ROLES = {item.value for item in StateRole}
