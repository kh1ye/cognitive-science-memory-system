"""Adapter to Cognitive Memory: no alternate storage or state machine."""

from cognitive_memory import Memory
from cognitive_memory.retrieval.lexical import normalize_text

from .state import MemoryExtraction


class CognitiveMemory:
    def __init__(self, engine: Memory):
        self.engine = engine

    def retrieve(self, user_id: str, query: str, recent_focus: str = ""):
        result = self.engine.search(user_id, query, top_k=5, recent_focus=recent_focus)
        return [
            {
                "id": row["id"],
                "content": row["content"],
                "memory_type": row["memory_type"],
                "state_role": row["state_role"],
                "score": row["retrieval"]["score"],
            }
            for row in result["results"]
        ]

    def allows_extraction(self, message: str) -> bool:
        return (
            self.engine.encoder.privacy_reason(normalize_text(message), [], False)
            is None
        )

    def write(
        self, user_id: str, message: str, extraction: MemoryExtraction, thread_id: str
    ):
        if not self.allows_extraction(message):
            return []
        results = []
        seen = set()
        for candidate in extraction.memories:
            # Never persist invented/paraphrased content or write the same span twice.
            if candidate.content not in message or candidate.content in seen:
                continue
            seen.add(candidate.content)
            tags = list(candidate.tags)
            if candidate.sensitive:
                tags.append("sensitive")
            result = self.engine.add_memory(
                {
                    "user_id": user_id,
                    "content": candidate.content,
                    "memory_key": candidate.memory_key,
                    "memory_value": candidate.memory_value,
                    "memory_type": candidate.memory_type,
                    "tags": tags,
                    "importance": candidate.importance,
                    "confidence": candidate.confidence,
                    "consent": False,
                    "source": "conversation_agent",
                    "metadata": {"thread_id": thread_id, "extraction": "llm"},
                }
            )
            results.append(
                {
                    "decision": result["decision"],
                    "reason": result.get("reason", ""),
                    "memory_id": (result.get("memory") or {}).get("id"),
                }
            )
        return results
