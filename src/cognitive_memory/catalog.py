"""One read model over typed objects; policy rows are storage projections, not a legacy store."""

import json
from collections import Counter
from datetime import datetime

from .retrieval.lexical import cosine_similarity, normalize_text
from .storage.architecture import stable_id
from .provenance import source_message_context

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

    def _policy_records(self, user):
        # No 1000-row API cap here: aggregate counts must cover the whole user.
        return [
            self.storage._row_to_dict(row)
            for row in self.storage._conn.execute(
                "SELECT * FROM memories WHERE user_id=?", (user,)
            )
        ]

    def _rows(self, user):
        records = self._policy_records(user)
        objects = {r["id"]: (table, r) for table in MODULE_TYPES for r in self.architecture.repo.rows(table, user) if "id" in r}
        result = [{**row, "storage_kind": "typed", "can_delete": True,
            "module": objects[row["id"]][0], "native_status": objects[row["id"]][1].get("status"),
            "source_refs": objects[row["id"]][1].get("source_refs", [])} for row in records if row["id"] in objects]
        represented = {row["id"] for row in result}
        for module, kind in MODULE_TYPES.items():
            for row in self.architecture.repo.rows(module, user):
                if row.get("id") in represented:
                    continue
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
                        "can_delete": True,
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
            # These relations retain original policy provenance, even for v2
            # sources whose missing thread was once filled with "manual".
            links = {
                link["to"]: link
                for link in self.architecture.repo.rows("memory_links", user)
                if link.get("relation") == "policy_evidence"
                and link.get("from") == memory_id
            }
            items = []
            for s in sources:
                if not s:
                    continue
                thread, message = source_message_context(s)
                link = links.get(s["id"])
                if link and "client" in (s.get("metadata") or {}):
                    thread, message = link.get("thread_id"), link.get("message_id")
                items.append({
                    "id": s["id"],
                    "content": s["content"],
                    "source": s["source_kind"],
                    "thread_id": thread,
                    "message_id": message,
                    "source_event_id": s["source_event_id"],
                    "created_at": s["recorded_at"],
                    "legacy": bool(link.get("legacy")) if link else False,
                })
            return {
                "memory_id": memory_id,
                "items": items,
                "total_count": len(items),
                "evidence_count": record["evidence_count"],
                "legacy_gap": max(0, record["evidence_count"] - len(items)),
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

    def retrieve(self, user, thread, task, query, *, modules=("semantic",), scope="user"):
        """Read the four-module store using the original policy ranker."""
        user = normalize_text(user) or "demo-user"
        return self.architecture.retrieve(user, thread, task, query, modules=modules, scope=scope)
