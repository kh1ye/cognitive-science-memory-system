from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import MemoryConfig
from .classification import infer_memory_type
from .consolidation import Consolidator
from .encoding import PROTECTED_TAGS, Encoder, clamp, parse_tags
from .keys import canonicalize_memory_key, canonicalize_memory_value
from .models import WriteResult, iso_now
from .provenance import evidence_origin
from .retention import RetentionManager
from .retrieval.lexical import normalize_text
from .retrieval.retriever import Retriever
from .storage.base import Storage
from .storage.sqlite import SQLiteStorage


class Memory:
    """Public memory API. Owns write transactions and coordinates domain rules."""

    def __init__(
        self,
        db_path: str | Path = ":memory:",
        config: MemoryConfig | None = None,
        *,
        storage: Storage | None = None,
    ):
        self.config = config or MemoryConfig()
        self.storage = storage if storage is not None else SQLiteStorage(db_path)
        from .architecture import MemoryArchitecture
        self.architecture = MemoryArchitecture(self.storage) if isinstance(self.storage, SQLiteStorage) else None
        from .catalog import MemoryCatalog
        self.catalog = MemoryCatalog(self) if self.architecture is not None else None
        self.encoder = Encoder(self.storage)
        self.consolidator = Consolidator(self.storage, self.config)
        self.retriever = Retriever(self.storage, self.config)
        self.retention = RetentionManager(self.storage, self.config)

    def close(self) -> None:
        self.storage.close()

    def __enter__(self) -> Memory:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def list_memories(
        self,
        user_id: str = "demo-user",
        include_archived: bool = False,
        limit: int = 200,
    ):
        return self.storage.list_memories(user_id, include_archived, limit)

    def search(
        self,
        user_id: str,
        query: str,
        top_k: int = 5,
        active_goal: str = "",
        recent_focus: str = "",
    ):
        return self.retriever.search(user_id, query, top_k, active_goal, recent_focus)

    def run_retention(self, user_id: str, reference_time: datetime | None = None):
        return self.retention.run_retention(user_id, reference_time)

    def add_memory(self, payload: dict[str, Any]) -> WriteResult:
        """Legacy protocol only. New callers use architecture.observe and typed services.

        This compatibility path intentionally retains the original scoring/state semantics;
        the catalog exposes eligible rows to chat without making them typed assertions.
        Migrated rows remain unverified and working text is never restored across tasks.
        """
        user_id = (
            normalize_text(str(payload.get("user_id", "demo-user"))) or "demo-user"
        )
        content = str(payload.get("content", "")).strip()
        if not content:
            raise ValueError("content 不能为空")
        tags = parse_tags(payload.get("tags"))
        memory_type = infer_memory_type(tags, payload.get("memory_type"))
        source = normalize_text(str(payload.get("source", "user"))) or "user"
        consent = bool(payload.get("consent", False))
        normalized = normalize_text(content)
        memory_key = canonicalize_memory_key(str(payload.get("memory_key", "")))
        memory_value = canonicalize_memory_value(
            memory_key, str(payload.get("memory_value", "")), content
        )
        importance = clamp(float(payload.get("importance", 0.7)))
        confidence = clamp(float(payload.get("confidence", 0.8)))
        active_goal = str(payload.get("active_goal", "")).strip()
        metadata = (
            payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        )
        evidence = {"user_id": user_id, "content": content, "source": source,
                    "normalized_content": normalized, "memory_key": memory_key,
                    "memory_value": memory_value, "metadata": metadata}
        evidence["evidence_origin"] = evidence_origin(evidence)
        with self.storage.transaction():
            privacy_reason = self.encoder.privacy_reason(normalized, tags, consent)
            if privacy_reason:
                message = (
                    "命中用户不记忆指令，未写入持久记忆。"
                    if privacy_reason == "do_not_store_instruction"
                    else "敏感信息缺少明确同意，未写入持久记忆。"
                )
                self.storage.audit(user_id, "DROP_PRIVACY", message)
                return {"decision": "DROP", "reason": privacy_reason, "memory": None}
            replay = self.storage.find_evidence(user_id, evidence["evidence_origin"])
            if replay:
                return {"decision": "UNCHANGED", "reason": "source_event_already_processed", "memory": replay}
            duplicate = self.storage.find_duplicate(user_id, normalized, memory_key, memory_type)
            reusable = duplicate and duplicate["state_role"] == "current"
            if duplicate and duplicate["state_role"] == "working":
                reusable = self.encoder.write_score(user_id, content, tags, importance, confidence) < self.config.write_threshold
            if reusable:
                self.storage.add_evidence(duplicate["id"], evidence)
                count = duplicate["evidence_count"] + 1
                self.storage.reinforce_duplicate(
                    count, iso_now(), importance, confidence, duplicate["id"]
                )
                self.storage.audit(
                    user_id,
                    "REINFORCE",
                    "检测到相同记忆，增加证据计数而不是重复写入。",
                    duplicate["id"],
                    {"evidence_count": count},
                )
                return {
                    "decision": "REINFORCED",
                    "reason": "exact_duplicate",
                    "memory": self.storage.get_memory(duplicate["id"]),
                }
            (saliency, goal_relevance, preference_strength, attention_bias) = (
                self.encoder.attention_profile(
                    user_id, content, memory_key, tags, importance, active_goal
                )
            )
            write_score = self.encoder.write_score(
                user_id, content, tags, importance, confidence
            )
            is_protected = bool(
                set(tags) & PROTECTED_TAGS or memory_type == "procedural"
            )
            base_values: dict[str, Any] = {
                "user_id": user_id,
                "content": content,
                "normalized_content": normalized,
                "memory_key": memory_key,
                "memory_value": memory_value,
                "memory_type": memory_type,
                "source": source,
                "tags": tags,
                "importance": importance,
                "confidence": confidence,
                "saliency": saliency,
                "goal_relevance": goal_relevance,
                "preference_strength": preference_strength,
                "attention_bias": attention_bias,
                "write_score": write_score,
                "is_protected": is_protected,
                "metadata": metadata,
                "evidence_origin": evidence["evidence_origin"],
                "parent_id": duplicate["id"] if duplicate and duplicate["state_role"] == "working" else None,
            }
            if write_score < self.config.write_threshold:
                memory_id = self.storage.insert_memory(
                    {**base_values, "state_role": "working"}
                )
                reason = "below_write_threshold"
                self.storage.audit(
                    user_id,
                    "KEEP_SESSION_ONLY",
                    "写入分数低于阈值，仅保留在工作层；内容类型仍属于三类记忆之一。",
                    memory_id,
                    {
                        "write_score": write_score,
                        "threshold": self.config.write_threshold,
                        "reason": reason,
                    },
                )
                return {
                    "decision": "KEEP_SESSION_ONLY",
                    "reason": reason,
                    "memory": self.storage.get_memory(memory_id),
                }
            result = self.consolidator.apply(base_values)
            if duplicate and duplicate["state_role"] == "working":
                self.storage.archive_supports([(iso_now(), duplicate["id"])])
            return result

    def evidence(self, user_id: str, memory_id: str):
        user_id = normalize_text(user_id) or "demo-user"
        with self.storage.transaction():
            if not self.storage.find_owned(memory_id, user_id):
                return None
            record = self.storage.get_memory(memory_id)
            count = self.storage.evidence_count(memory_id)
            return {"memory_id": memory_id, "items": self.storage.list_evidence(memory_id),
                    "total_count": count, "evidence_count": record["evidence_count"],
                    "legacy_gap": max(0, record["evidence_count"] - count)}

    def delete_memory(self, user_id: str, memory_id: str) -> bool:
        user_id = normalize_text(user_id) or "demo-user"
        with self.storage.transaction():
            row = self.storage.find_owned(memory_id, user_id)
            if not row:
                return False
            self.storage.delete_owned(memory_id, user_id)
            if self.architecture is not None:
                migrated = self.storage._conn.execute(
                    "SELECT target_table, target_id FROM legacy_memory_map WHERE legacy_id=?", (memory_id,)
                ).fetchone()
                if migrated:
                    self.architecture.repo.delete(migrated["target_table"], user_id, migrated["target_id"])
                    self.storage._conn.execute("DELETE FROM legacy_memory_map WHERE legacy_id=?", (memory_id,))
            self.storage.audit(
                user_id,
                "USER_DELETE",
                "用户主动删除记忆；正文已物理删除，审计仅保留记录 ID。",
                memory_id,
            )
            return True

    def list_audit(self, user_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self.storage.transaction():
            rows = self.storage.audit_rows(
                normalize_text(user_id) or "demo-user", max(1, min(limit, 500))
            )
            return rows

    def stats(self, user_id: str) -> dict[str, Any]:
        user_id = normalize_text(user_id) or "demo-user"
        if self.catalog is not None:
            return {**self.catalog.stats(user_id), "config": asdict(self.config)}
        with self.storage.transaction():
            role_rows = self.storage.role_counts(user_id)
            type_rows = self.storage.type_counts(user_id)
            audit_count = self.storage.audit_count(user_id)["count"]
            active_count = self.storage.active_count(user_id)["count"]
        return {
            "active_count": active_count,
            "by_role": {row["state_role"]: row["count"] for row in role_rows},
            "by_type": {row["memory_type"]: row["count"] for row in type_rows},
            "audit_count": audit_count,
            "config": asdict(self.config),
        }

    def overview(self, user_id: str = "demo-user") -> dict[str, Any]:
        stats = self.stats(user_id)
        with self.storage.transaction():
            storage = self.storage.storage_info()
        return {
            **stats,
            "total_count": sum(stats["by_role"].values()),
            "recent_activity": self.catalog.activity(user_id) if self.catalog is not None else self.list_audit(user_id, limit=8),
            "storage": storage,
            "modules": [
                {
                    "name": "选择性编码",
                    "description": "隐私判断与价值筛选",
                    "status": "ready",
                },
                {
                    "name": "证据巩固",
                    "description": "冲突缓冲与状态更新",
                    "status": "ready",
                },
                {
                    "name": "记忆检索",
                    "description": "词法召回与注意力排序",
                    "status": "ready",
                },
                {
                    "name": "遗忘管理",
                    "description": "保留度计算与归档",
                    "status": "ready",
                },
                {
                    "name": "语言模型",
                    "description": "尚未配置模型服务",
                    "status": "unconfigured",
                },
                {
                    "name": "向量模型",
                    "description": "当前使用离线词法检索",
                    "status": "unconfigured",
                },
            ],
        }

    def reset_user(self, user_id: str) -> None:
        """Reset only one explicitly selected demo namespace."""
        user_id = normalize_text(user_id) or "demo-user"
        with self.storage.transaction():
            self.storage.clear_memories(user_id)
            self.storage.clear_audit(user_id)
