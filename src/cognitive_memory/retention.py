from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from .config import MemoryConfig
from .models import iso_now, utc_now
from .retrieval.lexical import normalize_text
from .storage.base import Storage


class RetentionManager:
    """Evaluate decay and archive unprotected records."""

    def __init__(self, storage: Storage, config: MemoryConfig):
        self.storage = storage
        self.config = config

    def run_retention(
        self, user_id: str, reference_time: datetime | None = None
    ) -> dict[str, Any]:
        user_id = normalize_text(user_id) or "demo-user"
        now = reference_time or utc_now()
        archived: list[str] = []
        evaluated: list[dict[str, Any]] = []
        with self.storage.transaction():
            rows = self.storage.retention_rows(user_id)
            for row in rows:
                memory = row
                assert memory is not None
                created = datetime.fromisoformat(memory["created_at"])
                age_days = max(0.0, (now - created).total_seconds() / 86400.0)
                retention = memory["write_score"] * math.exp(
                    -self.config.retention_decay * age_days
                )
                should_archive = (
                    not memory["is_protected"]
                    and retention < self.config.retention_threshold
                )
                evaluated.append(
                    {
                        "id": memory["id"],
                        "retention": round(retention, 6),
                        "protected": memory["is_protected"],
                        "archived": should_archive,
                    }
                )
                if should_archive:
                    self.storage.archive_memory(iso_now(), memory["id"])
                    archived.append(memory["id"])
            self.storage.audit(
                user_id,
                "RETENTION",
                f"完成保留度检查，归档 {len(archived)} 条非保护记忆。",
                details={"archived_ids": archived, "evaluated_count": len(evaluated)},
            )
        return {"archived_ids": archived, "evaluated": evaluated}
