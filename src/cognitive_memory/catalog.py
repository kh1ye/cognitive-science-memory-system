"""One read model over typed objects and compatibility records; no dual writes."""

import json
from collections import Counter
from datetime import datetime

from .retrieval.lexical import cosine_similarity, normalize_text
from .storage.architecture import stable_id

MODULE_TYPES = {
    "working_states": "working",
    "episode_events": "episodic",
    "semantic_assertions": "semantic",
    "semantic_documents": "semantic",
    "procedure_versions": "procedural",
}


def timestamp(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (AttributeError, TypeError, ValueError):
        return 0


class MemoryCatalog:
    def __init__(self, memory):
        self.memory = memory
        self.storage = memory.storage
        self.architecture = memory.architecture

    def _legacy(self, user):
        # No 1000-row API cap here: aggregate counts must cover the whole user.
        return [
            self.storage._row_to_dict(row)
            for row in self.storage._conn.execute(
                "SELECT * FROM memories WHERE user_id=?", (user,)
            )
        ]

    def _migration_ids(self):
        return {
            r["legacy_id"]
            for r in self.storage._conn.execute(
                "SELECT legacy_id FROM legacy_memory_map"
            )
        }

    def _rows(self, user):
        legacy = self._legacy(user)
        migrated = self._migration_ids()
        result = [
            {
                **row,
                "storage_kind": "legacy",
                "can_delete": True,
                "migration_unverified": row["id"] in migrated,
            }
            for row in legacy
        ]
        for module, kind in MODULE_TYPES.items():
            for row in self.architecture.repo.rows(module, user):
                # Quarantined migration copies are represented by their original
                # compatibility row, including after that original is deleted.
                if (
                    row.get("status") == "legacy_unverified"
                    and row.get("version") == "legacy"
                ):
                    continue
                status = row.get("status", "current")
                role = {
                    "disputed": "candidate",
                    "legacy_unverified": "candidate",
                    "enabled": "current",
                    "configured": "current",
                    "draft": "candidate",
                    "validated": "candidate",
                    "disabled": "history",
                }.get(status, status)
                if module == "working_states":
                    role = "archived" if status == "completed" else "working"
                if role not in (
                    "current",
                    "candidate",
                    "history",
                    "working",
                    "archived",
                ):
                    role = "current"
                created = row.get("created_at") or row.get("recorded_at")
                updated = row.get("updated_at") or row.get("recorded_at") or created
                content = (
                    row.get("evidence_text")
                    or row.get("observation")
                    or row.get("content")
                    or row.get("description")
                )
                if module == "working_states":
                    content = json.dumps(
                        {
                            "task_id": row["task_id"],
                            "goals": row.get("goals", []),
                            "constraints": row.get("constraints", []),
                            "task_state": row.get("task_state", {}),
                        },
                        ensure_ascii=False,
                    )
                result.append(
                    {
                        "id": row.get("id")
                        or stable_id(user, row["thread_id"], row["task_id"]),
                        "user_id": user,
                        "content": content or "",
                        "memory_type": kind,
                        "state_role": role,
                        "native_status": status,
                        "storage_kind": "typed",
                        "module": module,
                        "can_delete": False,
                        "source": "typed_memory",
                        "memory_key": row.get("predicate")
                        or row.get("document_id")
                        or "",
                        "memory_value": row.get("value", ""),
                        "tags": [],
                        "evidence_count": len(
                            set(row.get("evidence_ids") or row.get("source_refs", []))
                        ),
                        "source_refs": row.get("source_refs", []),
                        "version": row.get("version"),
                        "created_at": created,
                        "updated_at": updated,
                        "last_accessed_at": None,
                        "importance": None,
                        "write_score": None,
                        "confidence": row.get("confidence"),
                        "is_protected": False,
                        "parent_id": None,
                        "support_ids": [],
                    }
                )
        return sorted(
            result,
            key=lambda r: (timestamp(r.get("updated_at")), r["id"]),
            reverse=True,
        )

    def list(self, user, *, include_archived=False, limit=200):
        user = normalize_text(user) or "demo-user"
        with self.storage._lock:
            rows = self._rows(user)
            return [
                r for r in rows if include_archived or r["state_role"] != "archived"
            ][: max(1, min(limit, 1000))]

    def stats(self, user):
        user = normalize_text(user) or "demo-user"
        with self.storage._lock:
            rows = self._rows(user)
            return {
                "active_count": sum(r["state_role"] != "archived" for r in rows),
                "total_count": len(rows),
                "by_role": dict(Counter(r["state_role"] for r in rows)),
                "by_type": dict(Counter(r["memory_type"] for r in rows)),
                "by_storage": dict(Counter(r["storage_kind"] for r in rows)),
                "audit_count": self.storage.audit_count(user)["count"]
                + len(self.architecture.repo.rows("learning_operations", user)),
            }

    def get(self, user, memory_id):
        user = normalize_text(user) or "demo-user"
        with self.storage._lock:
            return next((r for r in self._rows(user) if r["id"] == memory_id), None)

    def evidence(self, user, memory_id):
        user = normalize_text(user) or "demo-user"
        with self.storage._lock:
            record = self.get(user, memory_id)
            if record is None or record["storage_kind"] != "typed":
                return None
            sources = [
                self.architecture.repo.get("source_records", user, ref)
                for ref in record["source_refs"]
            ]
            items = [
                {
                    "id": s["id"],
                    "content": s["content"],
                    "source": s["source_kind"],
                    "thread_id": s["thread_id"],
                    "message_id": s["source_event_id"],
                    "created_at": s["recorded_at"],
                    "legacy": False,
                }
                for s in sources
                if s
            ]
            return {
                "memory_id": memory_id,
                "items": items,
                "total_count": len(items),
                "evidence_count": record["evidence_count"],
                "legacy_gap": 0,
            }

    def activity(self, user, limit=8):
        user = normalize_text(user) or "demo-user"
        with self.storage._lock:
            catalog = {r["id"]: r for r in self._rows(user)}
            events = self.storage.audit_rows(user, limit)
            for operation in self.architecture.repo.rows("learning_operations", user):
                source = next(
                    (
                        self.architecture.repo.get("source_records", user, ref)
                        for ref in operation.get("source_refs", [])
                        if ref
                    ),
                    None,
                )
                if source is None:
                    continue
                events.append(
                    {
                        "id": operation["id"],
                        "event_type": "TYPED_LEARNING",
                        "created_at": source["recorded_at"],
                        "message": "记忆写入成功"
                        if operation["status"] == "succeeded"
                        else "记忆写入失败",
                        "memory_id": next(iter(operation.get("result_refs", [])), None),
                        "details": {
                            "target_module": operation["target_module"],
                            "status": operation["status"],
                        },
                    }
                )
            for event in events:
                record = (
                    catalog.get(event.get("memory_id"))
                    if event["event_type"] != "USER_DELETE"
                    else None
                )
                event["related_memory"] = (
                    {
                        k: record[k]
                        for k in ("id", "content", "memory_type", "state_role")
                    }
                    if record
                    else None
                )
            return sorted(
                events, key=lambda e: timestamp(e.get("created_at")), reverse=True
            )[:limit]

    def retrieve(
        self, user, thread, task, query, *, modules=("semantic",), scope="user"
    ):
        """Activate compatible knowledge alongside native objects, without copying it.

        Old flow text is knowledge, never an executable procedure. Old working
        records are not restored into a different task. Migrated/unverified data
        stays explicitly unverified in context, rather than becoming trusted facts.
        """
        user = normalize_text(user) or "demo-user"
        typed = self.architecture.retrieve(
            user, thread, task, query, modules=modules, scope=scope
        )
        with self.storage._lock:
            legacy, migrated = self._legacy(user), self._migration_ids()
        history = any(
            word in normalize_text(query)
            for word in ("以前", "过去", "历史", "原来", "之前", "history")
        )
        additions = []
        for row in legacy:
            kind = row["memory_type"]
            module = "semantic" if kind == "procedural" else kind
            if module not in modules or module not in ("semantic", "episodic"):
                continue
            if row["state_role"] not in (
                ("current", "history") if history else ("current",)
            ):
                continue
            if row.get("metadata", {}).get("scope", "user") != scope:
                continue
            score = cosine_similarity(
                query,
                " ".join(
                    [
                        row["content"],
                        row.get("memory_key") or "",
                        row.get("memory_value") or "",
                    ]
                ),
            )
            if score <= 0:
                continue
            unverified = row["id"] in migrated
            record = {
                **row,
                "epistemic_status": "legacy_unverified"
                if unverified
                else "user_report",
            }
            if unverified:
                record.update(
                    legacy_state_role=row["state_role"], state_role="candidate"
                )
            additions.append(
                {
                    "module": module,
                    "memory_id": row["id"],
                    "id": row["id"],
                    "version": None,
                    "source_refs": [],
                    "purpose": query,
                    "record": record,
                    "memory_type": module,
                    "content": row["content"],
                    "storage_kind": "legacy",
                    "state_role": "candidate" if unverified else row["state_role"],
                    "epistemic_status": "legacy_unverified"
                    if unverified
                    else "user_report",
                    "score": score,
                }
            )
        result = []
        for module in modules:
            pool = [r for r in [*typed, *additions] if r["module"] == module]
            if module != "working":
                pool.sort(
                    key=lambda r: cosine_similarity(query, r.get("content", "")),
                    reverse=True,
                )
            result.extend(pool[:5])
        if additions:
            self.architecture.update_working_state(
                user, thread, task, {"active_knowledge": result}
            )
        return result
