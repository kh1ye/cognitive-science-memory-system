"""Offline cognitive long-term memory core used by the demo product.

The implementation intentionally has no third-party runtime dependency.  It
combines three paper-inspired ideas in a bounded, inspectable MVP:

* Melo: selective admission, typed memory, feedback and retention lifecycle.
* AB-Mem: persistent attention profile plus query-time attention matching.
* AxoMem: candidate evidence and evidence-gated consolidation.

It is a demonstrator, not a drop-in reproduction of any paper's experiments.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
import threading
import uuid
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


MEMORY_TYPES = {"working", "episodic", "semantic", "procedural"}
STATE_ROLES = {"working", "current", "candidate", "history", "archived"}
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


@dataclass(frozen=True)
class MemoryConfig:
    write_threshold: float = 0.42
    cpe_low_threshold: float = 0.55
    cpe_commit_threshold: float = 0.70
    evidence_consistency_threshold: float = 0.60
    minimum_evidence_count: int = 2
    retention_threshold: float = 0.30
    retention_decay: float = 0.04
    retrieval_lambda_bias: float = 0.65
    retrieval_delta_context: float = 0.45


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat(timespec="seconds")


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _latin_words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_+#.-]+", text.lower())


def _cjk_chars(text: str) -> list[str]:
    return re.findall(r"[\u3400-\u9fff]", text)


def token_counter(text: str) -> Counter[str]:
    """Return a deterministic bilingual lexical representation.

    Character unigrams/bigrams make Chinese retrieval useful without a model;
    Latin words preserve common technical terms.  This is deliberately a
    replaceable local baseline rather than a semantic embedding.
    """

    normalized = normalize_text(text)
    words = _latin_words(normalized)
    chars = _cjk_chars(normalized)
    tokens: list[str] = [f"w:{word}" for word in words]
    tokens.extend(f"c:{char}" for char in chars)
    tokens.extend(f"g:{chars[i]}{chars[i + 1]}" for i in range(len(chars) - 1))
    return Counter(tokens)


def cosine_similarity(left: str, right: str) -> float:
    a = token_counter(left)
    b = token_counter(right)
    if not a or not b:
        return 0.0
    dot = sum(value * b.get(key, 0) for key, value in a.items())
    norm_a = math.sqrt(sum(value * value for value in a.values()))
    norm_b = math.sqrt(sum(value * value for value in b.values()))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


def jaccard(left: Iterable[str], right: Iterable[str]) -> float:
    a, b = set(left), set(right)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


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


def infer_memory_type(tags: list[str], requested: str | None) -> str:
    if requested in MEMORY_TYPES:
        return requested
    tag_set = set(tags)
    if tag_set & {"procedure", "workflow", "流程", "工作流"}:
        return "procedural"
    if tag_set & {"profile", "preference", "goal", "fact", "画像", "偏好", "目标"}:
        return "semantic"
    if tag_set & {"event", "timeline", "tool", "事件", "时间线", "工具"}:
        return "episodic"
    return "semantic"


class MemoryService:
    """SQLite-backed memory service with deterministic, auditable operators."""

    def __init__(self, db_path: str | Path = ":memory:", config: MemoryConfig | None = None):
        self.config = config or MemoryConfig()
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

    def _audit(
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

    def _get_memory(self, memory_id: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
        return self._row_to_dict(row)

    def _insert_memory(self, values: dict[str, Any]) -> str:
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
                "support_ids_json": json.dumps(values.get("support_ids", []), ensure_ascii=False),
                "is_protected": int(values.get("is_protected", False)),
                "created_at": now,
                "updated_at": values.get("updated_at") or now,
                "last_accessed_at": values.get("last_accessed_at"),
                "metadata_json": json.dumps(values.get("metadata", {}), ensure_ascii=False, sort_keys=True),
            },
        )
        return memory_id

    def _profile_text(self, user_id: str) -> str:
        rows = self._conn.execute(
            """
            SELECT content FROM memories
            WHERE user_id = ? AND state_role = 'current'
              AND (tags_json LIKE '%profile%' OR tags_json LIKE '%preference%'
                   OR tags_json LIKE '%goal%' OR tags_json LIKE '%画像%'
                   OR tags_json LIKE '%偏好%' OR tags_json LIKE '%目标%')
            """,
            (user_id,),
        ).fetchall()
        return " ".join(row["content"] for row in rows)

    def _attention_profile(
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
            recurrence = self._conn.execute(
                """
                SELECT COUNT(*) AS count FROM memories
                WHERE user_id = ? AND memory_key = ? AND state_role != 'archived'
                """,
                (user_id, memory_key),
            ).fetchone()["count"]
            preference_strength = clamp(0.5 + 0.15 * min(recurrence, 3))
        else:
            preference_strength = 0.5

        if set(tags) & {"preference", "偏好"}:
            preference_strength = max(preference_strength, 0.7)

        attention_bias = sigmoid(
            1.2 * saliency + 0.8 * goal_relevance + 0.9 * preference_strength - 1.2
        )
        return saliency, goal_relevance, preference_strength, attention_bias

    def _write_score(
        self,
        user_id: str,
        content: str,
        tags: list[str],
        importance: float,
        confidence: float,
    ) -> float:
        profile = self._profile_text(user_id)
        overlap = cosine_similarity(content, profile) if profile else 0.0
        profile_bonus = min(0.18, 0.18 * overlap)
        noise = "noise" in tags or "噪声" in tags or confidence < 0.5
        noise_penalty = 0.28 if noise else 0.0
        return clamp(0.52 * importance + 0.30 * confidence + profile_bonus - noise_penalty)

    def _prediction_error(
        self,
        current: dict[str, Any],
        content: str,
        memory_value: str | None,
        tags: list[str],
    ) -> tuple[float, dict[str, float]]:
        old_comparison = current.get("memory_value") or current["content"]
        new_comparison = memory_value or content
        semantic_discrepancy = 1.0 - cosine_similarity(old_comparison, new_comparison)
        context_discrepancy = 0.0 if current.get("memory_key") else 0.5
        keyword_discrepancy = 1.0 - jaccard(current["tags"], tags)
        if normalize_text(old_comparison) != normalize_text(new_comparison):
            keyword_discrepancy = max(keyword_discrepancy, 0.75)
        cpe = clamp(
            0.55 * semantic_discrepancy
            + 0.15 * context_discrepancy
            + 0.30 * keyword_discrepancy
        )
        return cpe, {
            "semantic_discrepancy": round(semantic_discrepancy, 4),
            "context_discrepancy": round(context_discrepancy, 4),
            "keyword_discrepancy": round(keyword_discrepancy, 4),
        }

    def add_memory(self, payload: dict[str, Any]) -> dict[str, Any]:
        user_id = normalize_text(str(payload.get("user_id", "demo-user"))) or "demo-user"
        content = str(payload.get("content", "")).strip()
        if not content:
            raise ValueError("content 不能为空")

        tags = parse_tags(payload.get("tags"))
        source = normalize_text(str(payload.get("source", "user"))) or "user"
        consent = bool(payload.get("consent", False))
        normalized = normalize_text(content)
        memory_key = normalize_text(str(payload.get("memory_key", ""))) or None
        memory_value = str(payload.get("memory_value", "")).strip() or None
        importance = clamp(float(payload.get("importance", 0.7)))
        confidence = clamp(float(payload.get("confidence", 0.8)))
        active_goal = str(payload.get("active_goal", "")).strip()
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}

        with self._lock:
            if any(pattern in normalized for pattern in DO_NOT_STORE_PATTERNS):
                self._audit(user_id, "DROP_PRIVACY", "命中用户不记忆指令，未写入持久记忆。")
                self._conn.commit()
                return {"decision": "DROP", "reason": "do_not_store_instruction", "memory": None}

            if set(tags) & {"sensitive", "private", "敏感", "隐私"} and not consent:
                self._audit(user_id, "DROP_PRIVACY", "敏感信息缺少明确同意，未写入持久记忆。")
                self._conn.commit()
                return {"decision": "DROP", "reason": "consent_required", "memory": None}

            duplicate = self._conn.execute(
                """
                SELECT * FROM memories
                WHERE user_id = ? AND normalized_content = ? AND state_role != 'archived'
                ORDER BY created_at DESC LIMIT 1
                """,
                (user_id, normalized),
            ).fetchone()
            if duplicate:
                count = duplicate["evidence_count"] + 1
                self._conn.execute(
                    """
                    UPDATE memories SET evidence_count = ?, updated_at = ?,
                        importance = MAX(importance, ?), confidence = MAX(confidence, ?)
                    WHERE id = ?
                    """,
                    (count, iso_now(), importance, confidence, duplicate["id"]),
                )
                self._audit(
                    user_id,
                    "REINFORCE",
                    "检测到相同记忆，增加证据计数而不是重复写入。",
                    duplicate["id"],
                    {"evidence_count": count},
                )
                self._conn.commit()
                return {
                    "decision": "REINFORCED",
                    "reason": "exact_duplicate",
                    "memory": self._get_memory(duplicate["id"]),
                }

            memory_type = infer_memory_type(tags, payload.get("memory_type"))
            saliency, goal_relevance, preference_strength, attention_bias = self._attention_profile(
                user_id, content, memory_key, tags, importance, active_goal
            )
            write_score = self._write_score(user_id, content, tags, importance, confidence)
            is_protected = bool(set(tags) & PROTECTED_TAGS or memory_type == "procedural")

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
            }

            if memory_type == "working" or write_score < self.config.write_threshold:
                memory_id = self._insert_memory({**base_values, "state_role": "working"})
                reason = "explicit_working_memory" if memory_type == "working" else "below_write_threshold"
                self._audit(
                    user_id,
                    "KEEP_SESSION_ONLY",
                    "显式工作记忆或写入分数低于阈值，仅保留在工作层。",
                    memory_id,
                    {
                        "write_score": write_score,
                        "threshold": self.config.write_threshold,
                        "reason": reason,
                    },
                )
                self._conn.commit()
                return {
                    "decision": "KEEP_SESSION_ONLY",
                    "reason": reason,
                    "memory": self._get_memory(memory_id),
                }

            current_row = None
            if memory_key:
                current_row = self._conn.execute(
                    """
                    SELECT * FROM memories
                    WHERE user_id = ? AND memory_key = ? AND state_role = 'current'
                    ORDER BY updated_at DESC LIMIT 1
                    """,
                    (user_id, memory_key),
                ).fetchone()

            if current_row:
                current = self._row_to_dict(current_row)
                assert current is not None
                old_value = normalize_text(str(current.get("memory_value") or ""))
                new_value = normalize_text(str(memory_value or ""))
                if old_value and new_value and old_value == new_value:
                    new_count = current["evidence_count"] + 1
                    self._conn.execute(
                        """
                        UPDATE memories SET evidence_count = ?, updated_at = ?,
                            importance = MAX(importance, ?), confidence = MAX(confidence, ?),
                            attention_bias = MAX(attention_bias, ?)
                        WHERE id = ?
                        """,
                        (
                            new_count,
                            iso_now(),
                            importance,
                            confidence,
                            attention_bias,
                            current["id"],
                        ),
                    )
                    self._audit(
                        user_id,
                        "REINFORCE",
                        "新证据与当前状态一致，强化当前记忆。",
                        current["id"],
                        {"evidence_count": new_count},
                    )
                    self._conn.commit()
                    return {
                        "decision": "REINFORCED",
                        "reason": "same_key_value",
                        "memory": self._get_memory(current["id"]),
                    }

                cpe, components = self._prediction_error(current, content, memory_value, tags)
                if cpe >= self.config.cpe_low_threshold:
                    candidate_id = self._insert_memory(
                        {
                            **base_values,
                            "state_role": "candidate",
                            "parent_id": current["id"],
                            "prediction_error": cpe,
                        }
                    )
                    candidate_rows = self._conn.execute(
                        """
                        SELECT * FROM memories
                        WHERE user_id = ? AND memory_key = ? AND state_role = 'candidate'
                          AND LOWER(COALESCE(memory_value, '')) = LOWER(COALESCE(?, ''))
                        ORDER BY created_at ASC
                        """,
                        (user_id, memory_key, memory_value),
                    ).fetchall()
                    evidence_count = len(candidate_rows)
                    candidate_values = [row["memory_value"] or row["content"] for row in candidate_rows]
                    consistency = (
                        min(cosine_similarity(candidate_values[0], item) for item in candidate_values)
                        if candidate_values
                        else 0.0
                    )
                    self._audit(
                        user_id,
                        "CANDIDATE",
                        "检测到与当前状态不一致的证据，先进入候选缓冲区。",
                        candidate_id,
                        {
                            "cpe": round(cpe, 4),
                            "components": components,
                            "evidence_count": evidence_count,
                            "consistency": round(consistency, 4),
                        },
                    )

                    if (
                        evidence_count >= self.config.minimum_evidence_count
                        and cpe >= self.config.cpe_commit_threshold
                        and consistency >= self.config.evidence_consistency_threshold
                    ):
                        support_ids = [row["id"] for row in candidate_rows]
                        self._conn.execute(
                            "UPDATE memories SET state_role = 'history', updated_at = ? WHERE id = ?",
                            (iso_now(), current["id"]),
                        )
                        self._conn.executemany(
                            "UPDATE memories SET state_role = 'archived', updated_at = ? WHERE id = ?",
                            [(iso_now(), support_id) for support_id in support_ids],
                        )
                        consolidated_id = self._insert_memory(
                            {
                                **base_values,
                                "state_role": "current",
                                "parent_id": current["id"],
                                "support_ids": support_ids,
                                "prediction_error": cpe,
                                "evidence_count": evidence_count,
                                "metadata": {
                                    **metadata,
                                    "consolidated": True,
                                    "cpe_components": components,
                                    "consistency": consistency,
                                },
                            }
                        )
                        self._audit(
                            user_id,
                            "CONSOLIDATE",
                            "候选证据达到数量、误差和一致性阈值：旧状态转为历史，新状态提交为当前。",
                            consolidated_id,
                            {
                                "previous_current_id": current["id"],
                                "support_ids": support_ids,
                                "evidence_count": evidence_count,
                                "cpe": round(cpe, 4),
                                "consistency": round(consistency, 4),
                            },
                        )
                        self._conn.commit()
                        return {
                            "decision": "CONSOLIDATED",
                            "reason": "evidence_gate_passed",
                            "memory": self._get_memory(consolidated_id),
                            "previous_current_id": current["id"],
                            "support_ids": support_ids,
                        }

                    self._conn.commit()
                    return {
                        "decision": "CANDIDATE",
                        "reason": "awaiting_consistent_evidence",
                        "memory": self._get_memory(candidate_id),
                        "gate": {
                            "evidence_count": evidence_count,
                            "minimum_evidence_count": self.config.minimum_evidence_count,
                            "cpe": round(cpe, 4),
                            "commit_threshold": self.config.cpe_commit_threshold,
                            "consistency": round(consistency, 4),
                            "consistency_threshold": self.config.evidence_consistency_threshold,
                        },
                    }

            memory_id = self._insert_memory({**base_values, "state_role": "current"})
            self._audit(
                user_id,
                "WRITE_CURRENT",
                "通过选择性编码门，写入当前长期记忆。",
                memory_id,
                {"write_score": round(write_score, 4)},
            )
            self._conn.commit()
            return {"decision": "WRITE_CURRENT", "reason": "admitted", "memory": self._get_memory(memory_id)}

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
            return [self._row_to_dict(row) for row in self._conn.execute(query, params).fetchall()]  # type: ignore[list-item]

    def search(
        self,
        user_id: str,
        query: str,
        top_k: int = 5,
        active_goal: str = "",
        recent_focus: str = "",
    ) -> dict[str, Any]:
        user_id = normalize_text(user_id) or "demo-user"
        query = query.strip()
        if not query:
            raise ValueError("query 不能为空")
        dynamic_state = " ".join(part for part in (query, active_goal, recent_focus) if part)
        history_intent = any(word in normalize_text(query) for word in ("之前", "过去", "历史", "以前", "原来", "history"))

        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM memories
                WHERE user_id = ? AND state_role IN ('current', 'candidate', 'history', 'working')
                """,
                (user_id,),
            ).fetchall()
            scored: list[dict[str, Any]] = []
            for row in rows:
                memory = self._row_to_dict(row)
                assert memory is not None
                comparison_text = " ".join(
                    filter(
                        None,
                        [
                            memory["content"],
                            memory.get("memory_key") or "",
                            memory.get("memory_value") or "",
                            " ".join(memory["tags"]),
                        ],
                    )
                )
                base_relevance = cosine_similarity(query, comparison_text)
                context_match = cosine_similarity(dynamic_state, comparison_text)
                if base_relevance < 0.025:
                    continue

                role = memory["state_role"]
                if history_intent:
                    role_factor = {"history": 1.25, "current": 1.0, "candidate": 0.55, "working": 0.45}.get(role, 0.5)
                else:
                    role_factor = {"current": 1.18, "history": 0.62, "candidate": 0.58, "working": 0.45}.get(role, 0.5)

                attention_factor = 1.0 + self.config.retrieval_lambda_bias * memory["attention_bias"]
                context_factor = 1.0 + self.config.retrieval_delta_context * context_match
                score = base_relevance * attention_factor * context_factor * role_factor
                if "noise" in memory["tags"] or "噪声" in memory["tags"]:
                    score *= 0.4

                scored.append(
                    {
                        **memory,
                        "retrieval": {
                            "score": round(score, 6),
                            "base_relevance": round(base_relevance, 6),
                            "attention_bias": round(memory["attention_bias"], 6),
                            "context_match": round(context_match, 6),
                            "role_factor": role_factor,
                        },
                    }
                )

            scored.sort(key=lambda item: item["retrieval"]["score"], reverse=True)
            results = scored[: max(1, min(int(top_k), 20))]
            now = iso_now()
            self._conn.executemany(
                "UPDATE memories SET last_accessed_at = ? WHERE id = ?",
                [(now, result["id"]) for result in results],
            )
            self._audit(
                user_id,
                "RETRIEVE",
                f"完成注意力调制检索，返回 {len(results)} 条证据。",
                details={"query": query, "result_ids": [item["id"] for item in results]},
            )
            self._conn.commit()

            if not results:
                answer = "证据不足：当前长期记忆中没有找到可支持回答的记录。"
            else:
                preferred_role = "history" if history_intent else "current"
                preferred_results = [item for item in results if item["state_role"] == preferred_role]
                chosen = preferred_results or results
                answer = "基于当前记忆：" + "；".join(item["content"] for item in chosen[:3])

            return {
                "query": query,
                "answer": answer,
                "grounded": bool(results),
                "results": results,
                "policy": {
                    "semantic_gate": True,
                    "attention_modulation": True,
                    "history_intent": history_intent,
                },
            }

    def run_retention(self, user_id: str, reference_time: datetime | None = None) -> dict[str, Any]:
        user_id = normalize_text(user_id) or "demo-user"
        now = reference_time or utc_now()
        archived: list[str] = []
        evaluated: list[dict[str, Any]] = []
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM memories
                WHERE user_id = ? AND state_role IN ('current', 'candidate', 'working', 'history')
                """,
                (user_id,),
            ).fetchall()
            for row in rows:
                memory = self._row_to_dict(row)
                assert memory is not None
                created = datetime.fromisoformat(memory["created_at"])
                age_days = max(0.0, (now - created).total_seconds() / 86400.0)
                retention = memory["write_score"] * math.exp(-self.config.retention_decay * age_days)
                should_archive = not memory["is_protected"] and retention < self.config.retention_threshold
                evaluated.append(
                    {
                        "id": memory["id"],
                        "retention": round(retention, 6),
                        "protected": memory["is_protected"],
                        "archived": should_archive,
                    }
                )
                if should_archive:
                    self._conn.execute(
                        "UPDATE memories SET state_role = 'archived', updated_at = ? WHERE id = ?",
                        (iso_now(), memory["id"]),
                    )
                    archived.append(memory["id"])
            self._audit(
                user_id,
                "RETENTION",
                f"完成保留度检查，归档 {len(archived)} 条非保护记忆。",
                details={"archived_ids": archived, "evaluated_count": len(evaluated)},
            )
            self._conn.commit()
        return {"archived_ids": archived, "evaluated": evaluated}

    def delete_memory(self, user_id: str, memory_id: str) -> bool:
        user_id = normalize_text(user_id) or "demo-user"
        with self._lock:
            row = self._conn.execute(
                "SELECT id FROM memories WHERE id = ? AND user_id = ?", (memory_id, user_id)
            ).fetchone()
            if not row:
                return False
            self._conn.execute("DELETE FROM memories WHERE id = ? AND user_id = ?", (memory_id, user_id))
            self._audit(
                user_id,
                "USER_DELETE",
                "用户主动删除记忆；正文已物理删除，审计仅保留记录 ID。",
                memory_id,
            )
            self._conn.commit()
            return True

    def list_audit(self, user_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM audit_events WHERE user_id = ?
                ORDER BY created_at DESC, rowid DESC LIMIT ?
                """,
                (normalize_text(user_id) or "demo-user", max(1, min(limit, 500))),
            ).fetchall()
            items: list[dict[str, Any]] = []
            for row in rows:
                item = dict(row)
                item["details"] = json.loads(item.pop("details_json"))
                items.append(item)
            return items

    def stats(self, user_id: str) -> dict[str, Any]:
        user_id = normalize_text(user_id) or "demo-user"
        with self._lock:
            role_rows = self._conn.execute(
                "SELECT state_role, COUNT(*) AS count FROM memories WHERE user_id = ? GROUP BY state_role",
                (user_id,),
            ).fetchall()
            type_rows = self._conn.execute(
                "SELECT memory_type, COUNT(*) AS count FROM memories WHERE user_id = ? GROUP BY memory_type",
                (user_id,),
            ).fetchall()
            audit_count = self._conn.execute(
                "SELECT COUNT(*) AS count FROM audit_events WHERE user_id = ?", (user_id,)
            ).fetchone()["count"]
            active_count = self._conn.execute(
                "SELECT COUNT(*) AS count FROM memories WHERE user_id = ? AND state_role != 'archived'",
                (user_id,),
            ).fetchone()["count"]
        return {
            "active_count": active_count,
            "by_role": {row["state_role"]: row["count"] for row in role_rows},
            "by_type": {row["memory_type"]: row["count"] for row in type_rows},
            "audit_count": audit_count,
            "config": asdict(self.config),
        }

    def reset_user(self, user_id: str) -> None:
        """Reset only one explicitly selected demo namespace."""

        user_id = normalize_text(user_id) or "demo-user"
        with self._lock:
            self._conn.execute("DELETE FROM memories WHERE user_id = ?", (user_id,))
            self._conn.execute("DELETE FROM audit_events WHERE user_id = ?", (user_id,))
            self._conn.commit()

    def seed_demo(self, user_id: str = "demo-user") -> list[dict[str, Any]]:
        self.reset_user(user_id)
        events = [
            {
                "content": "用户长期编程偏好是 Python。",
                "memory_key": "coding_language",
                "memory_value": "Python",
                "memory_type": "semantic",
                "source": "user",
                "tags": ["profile", "preference"],
                "importance": 0.86,
                "confidence": 0.95,
            },
            {
                "content": "用户对花生严重过敏，规划餐饮时必须避开花生。",
                "memory_key": "food_allergy",
                "memory_value": "花生",
                "memory_type": "semantic",
                "source": "user",
                "tags": ["profile", "safety"],
                "importance": 1.0,
                "confidence": 0.98,
            },
            {
                "content": "用户最近更倾向使用 Rust 作为主要编程语言。",
                "memory_key": "coding_language",
                "memory_value": "Rust",
                "memory_type": "semantic",
                "source": "user_correction",
                "tags": ["preference", "conflict"],
                "importance": 0.9,
                "confidence": 0.92,
            },
            {
                "content": "用户再次确认未来项目主要使用 Rust。",
                "memory_key": "coding_language",
                "memory_value": "Rust",
                "memory_type": "semantic",
                "source": "user_feedback",
                "tags": ["preference", "conflict"],
                "importance": 0.9,
                "confidence": 0.94,
            },
            {
                "content": "演示流程：先运行测试，再启动服务，最后检查健康接口与浏览器页面。",
                "memory_key": "demo_workflow",
                "memory_value": "test-start-health-ui",
                "memory_type": "procedural",
                "source": "task_success",
                "tags": ["procedure", "workflow"],
                "importance": 0.82,
                "confidence": 0.9,
            },
        ]
        results = []
        for event in events:
            results.append(self.add_memory({"user_id": user_id, **event}))
        return results

