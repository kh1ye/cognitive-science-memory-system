"""Adapter to Cognitive Memory: no alternate storage or state machine."""

import unicodedata

from cognitive_memory import Memory
from cognitive_memory.keys import canonicalize_memory_key
from cognitive_memory.retrieval.lexical import normalize_text

from .state import MemoryExtraction


def source_span(content: str, message: str) -> str | None:
    """Recover original evidence despite whitespace, casing or punctuation changes."""
    if content in message:
        return content

    def canonical(text):
        chars, positions = [], []
        for i, char in enumerate(text):
            for value in unicodedata.normalize("NFKC", char).casefold():
                if not value.isspace() and not unicodedata.category(value).startswith(
                    "P"
                ):
                    chars.append(value)
                    positions.append(i)
        return "".join(chars), positions

    needle, _ = canonical(content.rstrip("。！？.!?"))
    haystack, positions = canonical(message)
    start = haystack.find(needle) if needle else -1
    if start < 0:
        return None
    return message[positions[start] : positions[start + len(needle) - 1] + 1]


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
        self, user_id: str, message: str, extraction: MemoryExtraction, thread_id: str,
        message_id: str | None = None,
    ):
        if not self.allows_extraction(message):
            return []
        results = []
        seen = set()
        for candidate in extraction.memories:
            content = source_span(candidate.content, message)
            if content is None:
                results.append(
                    {
                        "decision": "SKIPPED",
                        "reason": "no_source_evidence",
                        "memory_id": None,
                    }
                )
                continue
            if content in seen:
                continue
            seen.add(content)
            tags = list(candidate.tags)
            if candidate.sensitive:
                tags.append("sensitive")
            result = self.engine.add_memory(
                {
                    "user_id": user_id,
                    "content": content,
                    "memory_key": canonicalize_memory_key(candidate.memory_key),
                    "memory_value": candidate.memory_value,
                    "memory_type": candidate.memory_type,
                    "tags": tags,
                    "importance": candidate.importance,
                    "confidence": candidate.confidence,
                    "consent": False,
                    "source": "conversation_agent",
                    "metadata": {"thread_id": thread_id, "message_id": message_id, "extraction": "llm"},
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
