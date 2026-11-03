from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import MemoryConfig
from .models import utc_now
from .retrieval.lexical import normalize_text
from .storage.base import Storage


class RetentionManager:
    """Ebbinghaus decay and confirmation reinforcement on existing policy records.

    Stability and elapsed time use days. Unmodified/legacy records derive their
    own stability lazily; confirmation persists it in the existing metadata JSON.
    Reads and unrelated lifecycle updates never reset the forgetting clock.
    """

    def __init__(self, storage: Storage, config: MemoryConfig):
        self.storage = storage
        self.config = config

    @staticmethod
    def _time(value: str | datetime) -> datetime:
        stamp = datetime.fromisoformat(value) if isinstance(value, str) else value
        if not isinstance(stamp, datetime):
            raise ValueError("Expected an ISO timestamp or datetime")
        return stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp

    def _initial_stability(self, memory: dict[str, Any]) -> float:
        # Keep retention_decay as the baseline inverse stability for compatibility.
        # A zero rate disables decay; persisted stability itself stays finite.
        base = (
            1.0 / self.config.retention_decay
            if self.config.retention_decay > 0
            else 25.0
        )
        return base * (0.5 + 0.5 * memory["importance"])

    def state(
        self, memory: dict[str, Any], reference_time: datetime | None = None
    ) -> dict[str, Any]:
        now = self._time(reference_time or utc_now())
        saved = memory.get("metadata", {}).get("retention", {})
        if not isinstance(saved, dict):
            saved = {}
        stability = saved.get("stability_days")
        if (
            not isinstance(stability, (int, float))
            or not math.isfinite(stability)
            or stability <= 0
        ):
            stability = self._initial_stability(memory) * max(1, memory["evidence_count"])
        anchor = self._time(memory["created_at"])
        if saved.get("last_reinforced_at"):
            try:
                anchor = self._time(saved["last_reinforced_at"])
            except (TypeError, ValueError):
                pass
        age_days = max(0.0, (now - anchor).total_seconds() / 86400.0)
        probability = (
            math.exp(-age_days / stability)
            if self.config.retention_decay > 0
            else 1.0
        )
        score = memory["write_score"] * probability
        forget_at = None
        if self.config.retention_threshold > 0 and self.config.retention_decay > 0:
            days = (
                stability * math.log(memory["write_score"] / self.config.retention_threshold)
                if memory["write_score"] > self.config.retention_threshold
                else 0.0
            )
            try:
                forget_at = (anchor + timedelta(days=days)).isoformat()
            except OverflowError:
                pass  # The threshold lies outside datetime's representable range.
        return {
            "retention": score,
            "retention_probability": probability,
            "stability_days": stability,
            "last_reinforced_at": anchor.isoformat(),
            "forget_at": forget_at,
            "elapsed_days": age_days,
            "initial_stability_days": self._initial_stability(memory),
        }

    def is_enabled(self, user_id: str) -> bool:
        return self.storage.get_retention_enabled(normalize_text(user_id) or "demo-user")

    def set_enabled(self, user_id: str, enabled: bool) -> dict[str, Any]:
        user_id = normalize_text(user_id) or "demo-user"
        with self.storage.transaction():
            self.storage.set_retention_enabled(user_id, enabled)
            self.storage.audit(
                user_id, "RETENTION_SETTING",
                "开启记忆遗忘。" if enabled else "关闭记忆遗忘。",
                details={"enabled": enabled},
            )
        return {"user_id": user_id, "enabled": enabled}

    def is_protected(self, memory: dict[str, Any]) -> bool:
        return bool(
            memory["is_protected"]
            or memory["importance"] >= self.config.retention_importance_threshold
        )

    def overview(self, user_id: str, limit: int = 200) -> dict[str, Any]:
        """Read-only curve parameters and archive preview, using the policy calculator."""
        user_id = normalize_text(user_id) or "demo-user"
        now = utc_now()
        with self.storage.transaction():
            enabled = self.is_enabled(user_id)
            items = []
            for memory in self.storage.retention_rows(user_id):
                state = self.state(memory, now)
                protected = self.is_protected(memory)
                items.append({
                    **memory, **state, "protected": protected,
                    "archive_eligible": (
                        not protected
                        and state["retention"] < self.config.retention_threshold
                    ),
                })
        items.sort(key=lambda item: (item["retention_probability"], item["id"]))
        count = len(items)
        return {
            "user_id": user_id,
            "enabled": enabled,
            "evaluated_at": now.isoformat(),
            "threshold": self.config.retention_threshold,
            "retrieval_weight": self.config.retrieval_retention_weight,
            "summary": {
                "total": count,
                "protected": sum(m["protected"] for m in items),
                "archive_eligible": sum(m["archive_eligible"] for m in items),
                "average_retention": (
                    sum(m["retention_probability"] for m in items) / count
                    if count else None
                ),
            },
            "items": items[:limit],
            "truncated": count > limit,
        }

    def reinforce(
        self, memory: dict[str, Any], reference_time: datetime | None = None
    ) -> None:
        """Called with the pre-confirmation record inside the write transaction."""
        now = self._time(reference_time or utc_now())
        stability = self.state(memory, now)["stability_days"]
        metadata = {
            **memory.get("metadata", {}),
            "retention": {
                "stability_days": stability + self._initial_stability(memory),
                "last_reinforced_at": now.isoformat(),
            },
        }
        self.storage.update_retention(memory["id"], metadata)

    def run_retention(
        self, user_id: str, reference_time: datetime | None = None
    ) -> dict[str, Any]:
        user_id = normalize_text(user_id) or "demo-user"
        now = self._time(reference_time or utc_now())
        archived: list[str] = []
        evaluated: list[dict[str, Any]] = []
        with self.storage.transaction():
            if not self.is_enabled(user_id):
                return {"enabled": False, "archived_ids": [], "evaluated": [], "reason": "retention_disabled"}
            rows = self.storage.retention_rows(user_id)
            for row in rows:
                memory = row
                assert memory is not None
                state = self.state(memory, now)
                protected = self.is_protected(memory)
                should_archive = (
                    not protected
                    and state["retention"] < self.config.retention_threshold
                )
                evaluated.append(
                    {
                        "id": memory["id"],
                        **state,
                        "retention": round(state["retention"], 6),
                        "retention_probability": round(state["retention_probability"], 6),
                        "protected": protected,
                        "archived": should_archive,
                    }
                )
                if should_archive:
                    self.storage.archive_memory(now.isoformat(), memory["id"])
                    archived.append(memory["id"])
            self.storage.audit(
                user_id,
                "RETENTION",
                f"完成保留度检查，归档 {len(archived)} 条非保护记忆。",
                details={"archived_ids": archived, "evaluated_count": len(evaluated)},
            )
        return {"archived_ids": archived, "evaluated": evaluated}
