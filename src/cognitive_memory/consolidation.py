from __future__ import annotations

from typing import Any

from .config import MemoryConfig
from .encoding import clamp
from .models import WriteResult, iso_now
from .retrieval.lexical import cosine_similarity, jaccard, normalize_text
from .storage.base import Storage


class Consolidator:
    """Reinforcement, conflict buffering, and evidence-gated state transitions.

    Called inside the transaction owned by Memory.add_memory.
    """

    def __init__(self, storage: Storage, config: MemoryConfig):
        self.storage = storage
        self.config = config

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

    def apply(self, values: dict[str, Any]) -> WriteResult:
        user_id = values["user_id"]
        content = values["content"]
        memory_key = values["memory_key"]
        memory_value = values["memory_value"]
        tags = values["tags"]
        importance = values["importance"]
        confidence = values["confidence"]
        attention_bias = values["attention_bias"]
        metadata = values["metadata"]
        write_score = values["write_score"]
        current_row = None
        if memory_key:
            current_row = self.storage.find_current(user_id, memory_key)
        if current_row:
            current = current_row
            assert current is not None
            old_value = normalize_text(str(current.get("memory_value") or ""))
            new_value = normalize_text(str(memory_value or ""))
            if old_value and new_value and (old_value == new_value):
                new_count = current["evidence_count"] + 1
                self.storage.reinforce_current(
                    new_count,
                    iso_now(),
                    importance,
                    confidence,
                    attention_bias,
                    current["id"],
                )
                self.storage.audit(
                    user_id,
                    "REINFORCE",
                    "新证据与当前状态一致，强化当前记忆。",
                    current["id"],
                    {"evidence_count": new_count},
                )
                return {
                    "decision": "REINFORCED",
                    "reason": "same_key_value",
                    "memory": self.storage.get_memory(current["id"]),
                }
            (cpe, components) = self._prediction_error(
                current, content, memory_value, tags
            )
            if cpe >= self.config.cpe_low_threshold:
                candidate_id = self.storage.insert_memory(
                    {
                        **values,
                        "state_role": "candidate",
                        "parent_id": current["id"],
                        "prediction_error": cpe,
                    }
                )
                candidate_rows = self.storage.find_candidates(
                    user_id, memory_key, memory_value
                )
                evidence_count = len(candidate_rows)
                candidate_values = [
                    row["memory_value"] or row["content"] for row in candidate_rows
                ]
                consistency = (
                    min(
                        cosine_similarity(candidate_values[0], item)
                        for item in candidate_values
                    )
                    if candidate_values
                    else 0.0
                )
                self.storage.audit(
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
                    and (consistency >= self.config.evidence_consistency_threshold)
                ):
                    support_ids = [row["id"] for row in candidate_rows]
                    self.storage.mark_history(iso_now(), current["id"])
                    self.storage.archive_supports(
                        [(iso_now(), support_id) for support_id in support_ids]
                    )
                    consolidated_id = self.storage.insert_memory(
                        {
                            **values,
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
                    self.storage.audit(
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
                    return {
                        "decision": "CONSOLIDATED",
                        "reason": "evidence_gate_passed",
                        "memory": self.storage.get_memory(consolidated_id),
                        "previous_current_id": current["id"],
                        "support_ids": support_ids,
                    }
                return {
                    "decision": "CANDIDATE",
                    "reason": "awaiting_consistent_evidence",
                    "memory": self.storage.get_memory(candidate_id),
                    "gate": {
                        "evidence_count": evidence_count,
                        "minimum_evidence_count": self.config.minimum_evidence_count,
                        "cpe": round(cpe, 4),
                        "commit_threshold": self.config.cpe_commit_threshold,
                        "consistency": round(consistency, 4),
                        "consistency_threshold": self.config.evidence_consistency_threshold,
                    },
                }
        memory_id = self.storage.insert_memory({**values, "state_role": "current"})
        self.storage.audit(
            user_id,
            "WRITE_CURRENT",
            "通过选择性编码门，写入当前长期记忆。",
            memory_id,
            {"write_score": round(write_score, 4)},
        )
        return {
            "decision": "WRITE_CURRENT",
            "reason": "admitted",
            "memory": self.storage.get_memory(memory_id),
        }
