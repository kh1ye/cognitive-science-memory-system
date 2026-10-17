from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from ..models import MemoryRecord, iso_now
from ..retrieval.lexical import normalize_text


class SQLiteStorage:
    """SQLite record repository; schema and JSON serialization remain compatible."""

    def __init__(self, db_path: str | Path = ":memory:"):
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._create_schema()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _create_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                content TEXT NOT NULL,
                normalized_content TEXT NOT NULL,
                memory_key TEXT,
                memory_value TEXT,
                memory_type TEXT NOT NULL,
                state_role TEXT NOT NULL,
                source TEXT NOT NULL,
                tags_json TEXT NOT NULL,
                importance REAL NOT NULL,
                confidence REAL NOT NULL,
                saliency REAL NOT NULL,
                goal_relevance REAL NOT NULL,
                preference_strength REAL NOT NULL,
                attention_bias REAL NOT NULL,
                write_score REAL NOT NULL,
                prediction_error REAL NOT NULL DEFAULT 0,
                evidence_count INTEGER NOT NULL DEFAULT 1,
                parent_id TEXT,
                support_ids_json TEXT NOT NULL DEFAULT '[]',
                is_protected INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_accessed_at TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE INDEX IF NOT EXISTS idx_memories_user_role
                ON memories(user_id, state_role);
            CREATE INDEX IF NOT EXISTS idx_memories_user_key
                ON memories(user_id, memory_key, state_role);

            CREATE TABLE IF NOT EXISTS audit_events (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                memory_id TEXT,
                message TEXT NOT NULL,
                details_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_audit_user_time
                ON audit_events(user_id, created_at DESC);
            """
        )
        self._conn.commit()

    def audit(
        self,
        user_id: str,
        event_type: str,
        message: str,
        memory_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO audit_events
                (id, user_id, event_type, memory_id, message, details_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                user_id,
                event_type,
                memory_id,
                message,
                json.dumps(details or {}, ensure_ascii=False, sort_keys=True),
                iso_now(),
            ),
        )

    def _row_to_dict(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        item = dict(row)
        item["tags"] = json.loads(item.pop("tags_json"))
        item["support_ids"] = json.loads(item.pop("support_ids_json"))
        item["metadata"] = json.loads(item.pop("metadata_json"))
        item["is_protected"] = bool(item["is_protected"])
        return item

    def get_memory(self, memory_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM memories WHERE id = ?", (memory_id,)
        ).fetchone()
        return self._row_to_dict(row)

    def insert_memory(self, values: dict[str, Any]) -> str:
        memory_id = values.get("id") or str(uuid.uuid4())
        now = values.get("created_at") or iso_now()
        self._conn.execute(
            """
            INSERT INTO memories (
                id, user_id, content, normalized_content, memory_key, memory_value,
                memory_type, state_role, source, tags_json, importance, confidence,
                saliency, goal_relevance, preference_strength, attention_bias,
                write_score, prediction_error, evidence_count, parent_id,
                support_ids_json, is_protected, created_at, updated_at,
                last_accessed_at, metadata_json
            ) VALUES (
                :id, :user_id, :content, :normalized_content, :memory_key, :memory_value,
                :memory_type, :state_role, :source, :tags_json, :importance, :confidence,
                :saliency, :goal_relevance, :preference_strength, :attention_bias,
                :write_score, :prediction_error, :evidence_count, :parent_id,
                :support_ids_json, :is_protected, :created_at, :updated_at,
                :last_accessed_at, :metadata_json
            )
            """,
            {
                "id": memory_id,
                "user_id": values["user_id"],
                "content": values["content"],
                "normalized_content": values["normalized_content"],
                "memory_key": values.get("memory_key"),
                "memory_value": values.get("memory_value"),
                "memory_type": values["memory_type"],
                "state_role": values["state_role"],
                "source": values["source"],
                "tags_json": json.dumps(values["tags"], ensure_ascii=False),
                "importance": values["importance"],
                "confidence": values["confidence"],
                "saliency": values["saliency"],
                "goal_relevance": values["goal_relevance"],
                "preference_strength": values["preference_strength"],
                "attention_bias": values["attention_bias"],
                "write_score": values["write_score"],
                "prediction_error": values.get("prediction_error", 0.0),
                "evidence_count": values.get("evidence_count", 1),
                "parent_id": values.get("parent_id"),
                "support_ids_json": json.dumps(
                    values.get("support_ids", []), ensure_ascii=False
                ),
                "is_protected": int(values.get("is_protected", False)),
                "created_at": now,
                "updated_at": values.get("updated_at") or now,
                "last_accessed_at": values.get("last_accessed_at"),
                "metadata_json": json.dumps(
                    values.get("metadata", {}), ensure_ascii=False, sort_keys=True
                ),
            },
        )
        return memory_id

    def list_memories(
        self,
        user_id: str = "demo-user",
        include_archived: bool = False,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        with self._lock:
            query = "SELECT * FROM memories WHERE user_id = ?"
            params: list[Any] = [normalize_text(user_id)]
            if not include_archived:
                query += " AND state_role != 'archived'"
            query += " ORDER BY updated_at DESC LIMIT ?"
            params.append(max(1, min(limit, 1000)))
            return [
                self._row_to_dict(row)
                for row in self._conn.execute(query, params).fetchall()
            ]

    def profile_rows(self, user_id: str) -> list[dict[str, Any]]:
        params = (user_id,)
        return [
            dict(row)
            for row in self._conn.execute(
                """
        SELECT content FROM memories
        WHERE user_id = ? AND state_role = 'current'
          AND (tags_json LIKE '%profile%' OR tags_json LIKE '%preference%'
               OR tags_json LIKE '%goal%' OR tags_json LIKE '%画像%'
               OR tags_json LIKE '%偏好%' OR tags_json LIKE '%目标%')
        """,
                params,
            ).fetchall()
        ]

    def count_key_rows(self, user_id: str, memory_key: str) -> dict[str, int]:
        params = (user_id, memory_key)
        return (
            dict(row)
            if (
                row := self._conn.execute(
                    """
            SELECT COUNT(*) AS count FROM memories
            WHERE user_id = ? AND memory_key = ? AND state_role != 'archived'
            """,
                    params,
                ).fetchone()
            )
            is not None
            else None
        )

    def find_duplicate(self, user_id: str, normalized: str) -> MemoryRecord | None:
        params = (user_id, normalized)
        return self._row_to_dict(
            self._conn.execute(
                """
            SELECT * FROM memories
            WHERE user_id = ? AND normalized_content = ? AND state_role != 'archived'
            ORDER BY created_at DESC LIMIT 1
            """,
                params,
            ).fetchone()
        )

    def reinforce_duplicate(
        self,
        count: int,
        updated_at: str,
        importance: float,
        confidence: float,
        memory_id: str,
    ) -> None:
        params = (count, updated_at, importance, confidence, memory_id)
        self._conn.execute(
            """
                UPDATE memories SET evidence_count = ?, updated_at = ?,
                    importance = MAX(importance, ?), confidence = MAX(confidence, ?)
                WHERE id = ?
                """,
            params,
        )

    def find_current(self, user_id: str, memory_key: str) -> MemoryRecord | None:
        params = (user_id, memory_key)
        return self._row_to_dict(
            self._conn.execute(
                """
                SELECT * FROM memories
                WHERE user_id = ? AND memory_key = ? AND state_role = 'current'
                ORDER BY updated_at DESC LIMIT 1
                """,
                params,
            ).fetchone()
        )

    def reinforce_current(
        self,
        count: int,
        updated_at: str,
        importance: float,
        confidence: float,
        attention_bias: float,
        memory_id: str,
    ) -> None:
        params = (count, updated_at, importance, confidence, attention_bias, memory_id)
        self._conn.execute(
            """
                    UPDATE memories SET evidence_count = ?, updated_at = ?,
                        importance = MAX(importance, ?), confidence = MAX(confidence, ?),
                        attention_bias = MAX(attention_bias, ?)
                    WHERE id = ?
                    """,
            params,
        )

    def find_candidates(
        self, user_id: str, memory_key: str, memory_value: str | None
    ) -> list[MemoryRecord]:
        params = (user_id, memory_key, memory_value)
        return [
            self._row_to_dict(row)
            for row in self._conn.execute(
                """
                    SELECT * FROM memories
                    WHERE user_id = ? AND memory_key = ? AND state_role = 'candidate'
                      AND LOWER(COALESCE(memory_value, '')) = LOWER(COALESCE(?, ''))
                    ORDER BY created_at ASC
                    """,
                params,
            ).fetchall()
        ]

    def mark_history(self, updated_at: str, memory_id: str) -> None:
        params = (updated_at, memory_id)
        self._conn.execute(
            "UPDATE memories SET state_role = 'history', updated_at = ? WHERE id = ?",
            params,
        )

    def archive_supports(self, updates: list[tuple[str, str]]) -> None:
        params = updates
        self._conn.executemany(
            "UPDATE memories SET state_role = 'archived', updated_at = ? WHERE id = ?",
            params,
        )

    def retrievable_rows(self, user_id: str) -> list[MemoryRecord]:
        params = (user_id,)
        return [
            self._row_to_dict(row)
            for row in self._conn.execute(
                """
            SELECT * FROM memories
            WHERE user_id = ? AND state_role IN ('current', 'candidate', 'history', 'working')
            """,
                params,
            ).fetchall()
        ]

    def touch_memories(self, updates: list[tuple[str, str]]) -> None:
        params = updates
        self._conn.executemany(
            "UPDATE memories SET last_accessed_at = ? WHERE id = ?", params
        )

    def retention_rows(self, user_id: str) -> list[MemoryRecord]:
        params = (user_id,)
        return [
            self._row_to_dict(row)
            for row in self._conn.execute(
                """
            SELECT * FROM memories
            WHERE user_id = ? AND state_role IN ('current', 'candidate', 'working', 'history')
            """,
                params,
            ).fetchall()
        ]

    def archive_memory(self, updated_at: str, memory_id: str) -> None:
        params = (updated_at, memory_id)
        self._conn.execute(
            "UPDATE memories SET state_role = 'archived', updated_at = ? WHERE id = ?",
            params,
        )

    def find_owned(self, memory_id: str, user_id: str) -> dict[str, Any] | None:
        params = (memory_id, user_id)
        return (
            dict(row)
            if (
                row := self._conn.execute(
                    "SELECT id FROM memories WHERE id = ? AND user_id = ?", params
                ).fetchone()
            )
            is not None
            else None
        )

    def delete_owned(self, memory_id: str, user_id: str) -> None:
        params = (memory_id, user_id)
        self._conn.execute("DELETE FROM memories WHERE id = ? AND user_id = ?", params)

    def audit_rows(self, user_id: str, limit: int) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM audit_events WHERE user_id = ? "
            "ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["details"] = json.loads(item.pop("details_json"))
            items.append(item)
        return items

    def role_counts(self, user_id: str) -> list[dict[str, Any]]:
        params = (user_id,)
        return [
            dict(row)
            for row in self._conn.execute(
                "SELECT state_role, COUNT(*) AS count FROM memories WHERE user_id = ? GROUP BY state_role",
                params,
            ).fetchall()
        ]

    def type_counts(self, user_id: str) -> list[dict[str, Any]]:
        params = (user_id,)
        return [
            dict(row)
            for row in self._conn.execute(
                "SELECT memory_type, COUNT(*) AS count FROM memories WHERE user_id = ? GROUP BY memory_type",
                params,
            ).fetchall()
        ]

    def audit_count(self, user_id: str) -> dict[str, int]:
        params = (user_id,)
        return (
            dict(row)
            if (
                row := self._conn.execute(
                    "SELECT COUNT(*) AS count FROM audit_events WHERE user_id = ?",
                    params,
                ).fetchone()
            )
            is not None
            else None
        )

    def active_count(self, user_id: str) -> dict[str, int]:
        params = (user_id,)
        return (
            dict(row)
            if (
                row := self._conn.execute(
                    "SELECT COUNT(*) AS count FROM memories WHERE user_id = ? AND state_role != 'archived'",
                    params,
                ).fetchone()
            )
            is not None
            else None
        )

    def clear_memories(self, user_id: str) -> None:
        params = (user_id,)
        self._conn.execute("DELETE FROM memories WHERE user_id = ?", params)

    def clear_audit(self, user_id: str) -> None:
        params = (user_id,)
        self._conn.execute("DELETE FROM audit_events WHERE user_id = ?", params)

    @contextmanager
    def transaction(self):
        """Serialize one complete operation, committing or rolling back together."""
        with self._lock:
            with self._conn:
                yield
