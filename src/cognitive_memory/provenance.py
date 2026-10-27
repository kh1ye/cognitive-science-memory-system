"""Stable identities for actual source events, not inferred evidence."""
import hashlib
import json
from uuid import uuid4


def source_id(value):
    return value.strip() if isinstance(value, str) and value.strip() else None


def evidence_origin(values):
    metadata = values.get("metadata") or {}
    message_id = source_id(metadata.get("message_id"))
    event_id = source_id(metadata.get("event_id"))
    if not message_id and not event_id:
        return str(uuid4())
    identity = [values["user_id"], values["source"], source_id(metadata.get("thread_id")),
                message_id, event_id, values["normalized_content"],
                values.get("memory_key"), values.get("memory_value")]
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
