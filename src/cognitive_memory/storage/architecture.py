"""Versioned SQLite migration and typed-object repository, sharing the existing connection."""

import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from ..models import iso_now

TABLES = {
    "working_states",
    "episodes",
    "episode_events",
    "semantic_assertions",
    "semantic_documents",
    "procedures",
    "procedure_versions",
    "procedure_runs",
    "source_records",
    "memory_links",
    "learning_operations",
}


class ArchitectureRepository:
    def __init__(self, storage):
        self.storage = storage
        self.conn = storage._conn
        self.migrate()

    def migrate(self):
        with self.storage._lock:
            exists = self.conn.execute(
                "SELECT 1 FROM sqlite_master WHERE name='architecture_migrations'"
            ).fetchone()
            if (
                exists
                and self.conn.execute(
                    "SELECT 1 FROM architecture_migrations WHERE version=1"
                ).fetchone()
            ):
                return
            if self.storage.db_path != ":memory:":
                backup = Path(self.storage.db_path + ".pre-coala-v1.bak")
                if backup.exists():
                    raise ValueError(
                        f"Migration backup already exists: {backup}; verify/rename before retry"
                    )
                with closing(sqlite3.connect(backup)) as target:
                    self.conn.backup(target)
            with self.storage.transaction():
                self.conn.execute(
                    "CREATE TABLE IF NOT EXISTS architecture_migrations(version INTEGER PRIMARY KEY, applied_at TEXT)"
                )
                # Each module has its own table and contract. Indexed ownership/scope are outside payload JSON.
                for table in sorted(TABLES):
                    self.conn.execute(
                        f"CREATE TABLE {table}(id TEXT PRIMARY KEY, user_id TEXT NOT NULL, scope TEXT NOT NULL, data TEXT NOT NULL)"
                    )
                    self.conn.execute(
                        f"CREATE INDEX idx_{table}_owner ON {table}(user_id, scope)"
                    )
                self.conn.execute(
                    "CREATE TABLE legacy_memory_map(legacy_id TEXT PRIMARY KEY, target_table TEXT, target_id TEXT)"
                )
                for row in self.storage.list_memories_all_for_migration():
                    kind = row["memory_type"]
                    target = {
                        "episodic": "episode_events",
                        "procedural": "procedure_versions",
                    }.get(kind, "semantic_documents")
                    if kind == "working":
                        target = "semantic_documents"  # quarantined, never restored into an unrelated task
                    data = {
                        "id": row["id"],
                        "content": row["content"],
                        "status": "legacy_unverified",
                        "legacy_type": kind,
                        "recorded_at": row["created_at"],
                        "source_refs": [],
                        "occurred_at": None,
                        "version": "legacy",
                        "implementation_ref": None,
                    }
                    self.put(target, row["user_id"], row["id"], data, scope="legacy")
                    self.conn.execute(
                        "INSERT INTO legacy_memory_map VALUES (?, ?, ?)",
                        (row["id"], target, row["id"]),
                    )
                self.conn.execute(
                    "INSERT INTO architecture_migrations VALUES (1, ?)", (iso_now(),)
                )

    def begin_learning_item(self):
        self.conn.execute("SAVEPOINT learning_item")

    def release_learning_item(self):
        self.conn.execute("RELEASE learning_item")

    def rollback_learning_item(self):
        self.conn.execute("ROLLBACK TO learning_item")

    def rows(self, table, user_id, scope=None):
        if table not in TABLES:
            raise ValueError("Unknown module")
        sql, args = f"SELECT data FROM {table} WHERE user_id=?", [user_id]
        if scope is not None:
            sql += " AND scope=?"
            args.append(scope)
        with self.storage._lock:
            return [json.loads(row[0]) for row in self.conn.execute(sql, args)]

    def get(self, table, user_id, object_id):
        if table not in TABLES:
            raise ValueError("Unknown module")
        with self.storage._lock:
            row = self.conn.execute(
                f"SELECT data FROM {table} WHERE user_id=? AND id=?",
                (user_id, object_id),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, table, user_id, object_id, data, scope=None):
        if table not in TABLES:
            raise ValueError("Unknown module")
        scope = scope or data.get("scope", "user")
        self.conn.execute(
            f"INSERT INTO {table} VALUES (?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET data=excluded.data, scope=excluded.scope WHERE user_id=excluded.user_id",
            (object_id, user_id, scope, json.dumps(data, ensure_ascii=False)),
        )
        return data

    def delete(self, table, user_id, object_id):
        if table not in TABLES:
            raise ValueError("Unknown module")
        self.conn.execute(
            f"DELETE FROM {table} WHERE user_id=? AND id=?", (user_id, object_id)
        )


def stable_id(*parts):
    return hashlib.sha256(
        json.dumps(parts, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
