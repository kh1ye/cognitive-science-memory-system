"""Stable identities for actual source events, not inferred evidence."""

import hashlib
import json
import unicodedata
from uuid import uuid4


def source_id(value):
    return value.strip() if isinstance(value, str) and value.strip() else None


def evidence_origin(values):
    metadata = values.get("metadata") or {}
    message_id = source_id(metadata.get("message_id"))
    event_id = source_id(metadata.get("event_id"))
    if not message_id and not event_id:
        return str(uuid4())
    identity = [
        values["user_id"],
        values["source"],
        source_id(metadata.get("thread_id")),
        message_id,
        event_id,
        values["normalized_content"],
        values.get("memory_key"),
        values.get("memory_value"),
    ]
    return hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


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
