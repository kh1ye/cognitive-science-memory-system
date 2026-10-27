from __future__ import annotations

from typing import Any

from ..config import MemoryConfig
from ..models import iso_now
from ..storage.base import Storage
from .lexical import cosine_similarity, normalize_text


class Retriever:
    """Lexical recall with attention, context, and state-role ranking."""

    def __init__(self, storage: Storage, config: MemoryConfig):
        self.storage = storage
        self.config = config

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
        dynamic_state = " ".join(
            part for part in (query, active_goal, recent_focus) if part
        )
        history_intent = any(
            word in normalize_text(query)
            for word in ("之前", "过去", "历史", "以前", "原来", "history")
        )
        with self.storage.transaction():
            rows = self.storage.retrievable_rows(user_id)
            scored: list[dict[str, Any]] = []
            for row in rows:
                memory = row
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
                    role_factor = {
                        "history": 1.25,
                        "current": 1.0,
                        "candidate": 0.55,
                        "working": 0.45,
                    }.get(role, 0.5)
                else:
                    role_factor = {
                        "current": 1.18,
                        "history": 0.62,
                        "candidate": 0.58,
                        "working": 0.45,
                    }.get(role, 0.5)
                attention_factor = (
                    1.0 + self.config.retrieval_lambda_bias * memory["attention_bias"]
                )
                context_factor = (
                    1.0 + self.config.retrieval_delta_context * context_match
                )
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
            self.storage.touch_memories([(now, result["id"]) for result in results])
            self.storage.audit(
                user_id,
                "RETRIEVE",
                f"完成注意力调制检索，返回 {len(results)} 条证据。",
                details={
                    "query": query,
                    "result_ids": [item["id"] for item in results],
                },
            )
            preferred_role = "history" if history_intent else "current"
            preferred_results = [item for item in results if item["state_role"] == preferred_role]
            if not results:
                answer = "证据不足：当前长期记忆中没有找到可支持回答的记录。"
            else:
                chosen = preferred_results
                if chosen:
                    prefix = "基于历史记忆：" if history_intent else "基于当前有效记忆："
                    answer = prefix + "；".join(item["content"] for item in chosen[:3])
                else:
                    labels = {"candidate": "未确认候选", "history": "历史记录", "working": "工作层记录", "current": "当前记录"}
                    answer = "缺少所查询状态的确认依据，仅找到参考信息：" + "；".join(
                        f"【{labels.get(item['state_role'], item['state_role'])}】{item['content']}"
                        for item in results[:3]
                    )
            return {
                "query": query,
                "answer": answer,
                "grounded": bool(results) and bool(preferred_results),
                "has_results": bool(results),
                "answer_status": "confirmed_history" if results and preferred_results and history_intent else "confirmed_current" if results and preferred_results else "reference_only" if results else "insufficient_evidence",
                "results": results,
                "policy": {
                    "semantic_gate": True,
                    "attention_modulation": True,
                    "history_intent": history_intent,
                },
            }
