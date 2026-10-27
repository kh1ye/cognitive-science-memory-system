from __future__ import annotations

import math
import re
from typing import Any

from .retrieval.lexical import cosine_similarity, normalize_text
from .storage.base import Storage

PROTECTED_TAGS = {
    "profile",
    "preference",
    "goal",
    "procedure",
    "workflow",
    "safety",
}

CRITICAL_CUES = {
    "过敏",
    "禁止",
    "必须",
    "不能",
    "紧急",
    "截止",
    "风险",
    "安全",
    "allergy",
    "must",
    "cannot",
    "urgent",
    "deadline",
    "risk",
    "safety",
    "forbidden",
}

DO_NOT_STORE_PATTERNS = (
    "不要记住",
    "不要保存",
    "请勿记录",
    "do not remember",
    "don't remember",
    "do not store",
)


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def parse_tags(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        values = re.split(r"[,，;；\s]+", raw)
    elif isinstance(raw, list):
        values = [str(item) for item in raw]
    else:
        values = [str(raw)]
    return sorted({normalize_text(value) for value in values if value.strip()})


class Encoder:
    """Selective encoding, privacy gate, and attention profile scoring."""

    def __init__(self, storage: Storage):
        self.storage = storage

    def privacy_reason(
        self, normalized: str, tags: list[str], consent: bool
    ) -> str | None:
        if any(pattern in normalized for pattern in DO_NOT_STORE_PATTERNS):
            return "do_not_store_instruction"
        if set(tags) & {"sensitive", "private", "敏感", "隐私"} and not consent:
            return "consent_required"
        return None

    def profile_text(self, user_id: str) -> str:
        rows = self.storage.profile_rows(user_id)
        return " ".join(row["content"] for row in rows)

    def attention_profile(
        self,
        user_id: str,
        content: str,
        memory_key: str | None,
        tags: list[str],
        importance: float,
        active_goal: str,
    ) -> tuple[float, float, float, float]:
        normalized = normalize_text(content)
        cue_hit = any(cue in normalized for cue in CRITICAL_CUES)
        saliency = clamp(0.65 * importance + 0.35 * float(cue_hit))
        goal_relevance = cosine_similarity(content, active_goal) if active_goal else 0.5
        if memory_key:
            recurrence = self.storage.count_key_rows(user_id, memory_key)["count"]
            preference_strength = clamp(0.5 + 0.15 * min(recurrence, 3))
        else:
            preference_strength = 0.5
        if set(tags) & {"preference", "偏好"}:
            preference_strength = max(preference_strength, 0.7)
        attention_bias = sigmoid(
            1.2 * saliency + 0.8 * goal_relevance + 0.9 * preference_strength - 1.2
        )
        return (saliency, goal_relevance, preference_strength, attention_bias)

    def write_score(
        self,
        user_id: str,
        content: str,
        tags: list[str],
        importance: float,
        confidence: float,
    ) -> float:
        profile = self.profile_text(user_id)
        overlap = cosine_similarity(content, profile) if profile else 0.0
        profile_bonus = min(0.18, 0.18 * overlap)
        noise = "noise" in tags or "噪声" in tags or confidence < 0.5
        noise_penalty = 0.28 if noise else 0.0
        return clamp(
            0.52 * importance + 0.30 * confidence + profile_bonus - noise_penalty
        )
