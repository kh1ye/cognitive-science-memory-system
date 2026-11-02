"""Storage adapter: existing policy records live in the four-module object tables.

The old Storage protocol is retained as SQL views/triggers. It is a projection,
not a second memory store or a replacement for the scoring/update algorithms.
"""

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from ..models import iso_now
from ..provenance import source_message_context
from .architecture import stable_id

RECORD_TABLES = (
    "working_states",
    "episode_events",
    "semantic_assertions",
    "semantic_documents",
    "procedure_versions",
)
COLUMNS = (
    "id",
    "user_id",
    "content",
    "normalized_content",
    "memory_key",
    "memory_value",
    "memory_type",
    "state_role",
    "source",
    "tags_json",
    "importance",
    "confidence",
    "saliency",
    "goal_relevance",
    "preference_strength",
    "attention_bias",
    "write_score",
    "prediction_error",
    "evidence_count",
    "parent_id",
    "support_ids_json",
    "is_protected",
    "created_at",
    "updated_at",
    "last_accessed_at",
    "metadata_json",
)


def enable(storage, repo):
    conn = storage._conn
    storage._typed_context = None
    storage._typed_repo = repo
    storage._typed_enabled = False
    conn.create_function(
        "memory_policy",
        len(COLUMNS),
        lambda *values: json.dumps(dict(zip(COLUMNS, values)), ensure_ascii=False),
    )
    conn.create_function(
        "memory_object",
        2,
        lambda table, raw: json.dumps(
            object_from_policy(storage, table, json.loads(raw)), ensure_ascii=False
        ),
    )
    conn.create_function(
        "memory_source_id",
        2,
        lambda user, origin: evidence_source_id(storage, user, origin),
    )
    conn.create_function(
        "memory_source",
        8,
        lambda *args: json.dumps(source_from_evidence(*args), ensure_ascii=False),
    )
    conn.create_function(
        "memory_link_id",
        2,
        lambda memory, origin: stable_id(memory, "evidence", origin),
    )
    schema = conn.execute(
        "SELECT type FROM sqlite_master WHERE name='memories'"
    ).fetchone()
    if schema and schema[0] == "view":
        storage._typed_enabled = True
        return
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    if storage.db_path != ":memory:":
        backup = Path(storage.db_path + ".before-typed-storage-" + stamp + ".bak")
        with backup.open("xb"):
            pass
        with closing(sqlite3.connect(backup)) as target:
            conn.backup(target)
    with storage.transaction():
        records = [dict(r) for r in conn.execute("SELECT * FROM memories")]
        evidence = [dict(r) for r in conn.execute("SELECT * FROM memory_evidence")]
        # V1 quarantine copies are replaced by the same record IDs, not duplicated.
        for mapping in conn.execute("SELECT * FROM legacy_memory_map").fetchall():
            if mapping["target_table"] not in RECORD_TABLES:
                raise ValueError("Invalid migration target")
            row = conn.execute(
                f"SELECT data FROM {mapping['target_table']} WHERE id=?",
                (mapping["target_id"],),
            ).fetchone()
            if row:
                data = json.loads(row[0])
                if (
                    data.get("version") == "legacy"
                    and data.get("status") == "legacy_unverified"
                ):
                    conn.execute(
                        f"DELETE FROM {mapping['target_table']} WHERE id=?",
                        (mapping["target_id"],),
                    )
        conn.execute("DELETE FROM legacy_memory_map")
        conn.execute("DROP TABLE memory_evidence")
        conn.execute("DROP TABLE memories")
        _views(conn)
        marks = ",".join("?" for _ in COLUMNS)
        storage._importing_records = True
        for record in records:
            conn.execute(
                f"INSERT INTO memories ({','.join(COLUMNS)}) VALUES ({marks})",
                tuple(record[c] for c in COLUMNS),
            )
        storage._importing_records = False
        for row in evidence:
            conn.execute(
                "INSERT INTO memory_evidence VALUES (?,?,?,?,?,?,?,?,?,?)",
                tuple(
                    row[c]
                    for c in (
                        "id",
                        "memory_id",
                        "user_id",
                        "origin_key",
                        "content",
                        "source",
                        "thread_id",
                        "message_id",
                        "created_at",
                        "legacy",
                    )
                ),
            )
        if conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0] != len(records):
            raise ValueError("Typed storage migration count mismatch")
        conn.execute(
            "INSERT OR REPLACE INTO architecture_migrations VALUES (2,?)", (iso_now(),)
        )
        storage._typed_enabled = True
        # Existing native objects receive policy metadata once; their IDs and lifecycle remain intact.
        with storage.transaction():
            for table in RECORD_TABLES:
                if table == "working_states":
                    continue
                for row in conn.execute(
                    f"SELECT id,user_id,data FROM {table}"
                ).fetchall():
                    data = json.loads(row["data"])
                    if "_policy" not in data:
                        data = prepare_native(storage, table, row["user_id"], data)
                        conn.execute(
                            f"UPDATE {table} SET data=? WHERE id=?",
                            (json.dumps(data, ensure_ascii=False), row["id"]),
                        )
                        attach_sources(storage, row["user_id"], data)


def _views(conn):
    projections = []
    for table in RECORD_TABLES:
        fields = ",".join(
            (
                c
                if c in ("id", "user_id")
                else f"json_extract(data,'$._policy.{c}') AS {c}"
            )
            for c in COLUMNS
        )
        projections.append(
            f"SELECT {fields} FROM {table} WHERE json_type(data,'$._policy')='object'"
        )
    conn.execute("CREATE VIEW memories AS " + " UNION ALL ".join(projections))
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_policy_evidence_owner ON memory_links(user_id,json_extract(data,'$.relation'),json_extract(data,'$.origin_key'))"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_policy_evidence_record ON memory_links(user_id,json_extract(data,'$.relation'),json_extract(data,'$.from'))"
    )
    policy = "memory_policy(" + ",".join(f"NEW.{c}" for c in COLUMNS) + ")"
    routes = {
        "working_states": "NEW.state_role='working' OR NEW.memory_type='working'",
        "episode_events": "NEW.state_role!='working' AND NEW.memory_type='episodic'",
        "semantic_assertions": "NEW.state_role!='working' AND NEW.memory_type='semantic' AND COALESCE(NEW.memory_key,'')!=''",
        "semantic_documents": "NEW.state_role!='working' AND NEW.memory_type='semantic' AND COALESCE(NEW.memory_key,'')=''",
        "procedure_versions": "NEW.state_role!='working' AND NEW.memory_type='procedural'",
    }
    inserts = " ".join(
        f"INSERT INTO {table}(id,user_id,scope,data) SELECT NEW.id,NEW.user_id,COALESCE(json_extract(NEW.metadata_json,'$.scope'),'user'),memory_object('{table}',{policy}) WHERE {condition};"
        for table, condition in routes.items()
    )
    containers = """
        INSERT OR IGNORE INTO episodes(id,user_id,scope,data)
          SELECT json_extract(data,'$.episode_id'),user_id,scope,json_object(
            'id',json_extract(data,'$.episode_id'),'thread_id',json_extract(data,'$.thread_id'),
            'task_id',json_extract(data,'$.task_id'),'status','open','recorded_at',NEW.created_at)
          FROM episode_events WHERE id=NEW.id AND user_id=NEW.user_id;
        INSERT OR IGNORE INTO procedures(id,user_id,scope,data)
          SELECT json_extract(data,'$.procedure_id'),user_id,scope,json_object(
            'id',json_extract(data,'$.procedure_id'),'name',COALESCE(NEW.memory_key,NEW.id),
            'active_version',NULL,'scope',scope)
          FROM procedure_versions WHERE id=NEW.id AND user_id=NEW.user_id;
    """
    conn.execute(
        f"CREATE TRIGGER records_insert INSTEAD OF INSERT ON memories BEGIN SELECT CASE WHEN EXISTS(SELECT 1 FROM memories WHERE id=NEW.id) THEN RAISE(ABORT,'duplicate record identity') END; {inserts} {containers} END"
    )
    updates = " ".join(
        f"UPDATE {table} SET data=memory_object('{table}',{policy}),scope=COALESCE(json_extract(NEW.metadata_json,'$.scope'),'user') WHERE id=OLD.id AND user_id=OLD.user_id;"
        for table in RECORD_TABLES
    )
    conn.execute(
        f"CREATE TRIGGER records_update INSTEAD OF UPDATE ON memories BEGIN {updates} END"
    )
    deletes = " ".join(
        f"DELETE FROM {table} WHERE id=OLD.id AND user_id=OLD.user_id;"
        for table in RECORD_TABLES
    )
    conn.execute(
        f"CREATE TRIGGER records_delete INSTEAD OF DELETE ON memories BEGIN {deletes} DELETE FROM memory_links WHERE user_id=OLD.user_id AND json_extract(data,'$.relation')='policy_evidence' AND json_extract(data,'$.from')=OLD.id; END"
    )
    conn.execute(
        """CREATE VIEW memory_evidence AS
        SELECT json_extract(l.data,'$.evidence_id') AS id,
          json_extract(l.data,'$.from') AS memory_id,l.user_id AS user_id,
          json_extract(l.data,'$.origin_key') AS origin_key,
          COALESCE(json_extract(l.data,'$.content'),json_extract(s.data,'$.content')) AS content,
          json_extract(l.data,'$.source') AS source,
          json_extract(l.data,'$.thread_id') AS thread_id,
          json_extract(l.data,'$.message_id') AS message_id,
          json_extract(l.data,'$.created_at') AS created_at,
          json_extract(l.data,'$.legacy') AS legacy
        FROM memory_links l JOIN source_records s ON s.id=json_extract(l.data,'$.to') AND s.user_id=l.user_id
        WHERE json_extract(l.data,'$.relation')='policy_evidence'"""
    )
    refresh = " ".join(
        f"UPDATE {table} SET data=memory_object('{table}',json_extract(data,'$._policy')) WHERE id=NEW.memory_id AND user_id=NEW.user_id;"
        for table in RECORD_TABLES
    )
    conn.execute(
        """CREATE TRIGGER evidence_insert INSTEAD OF INSERT ON memory_evidence BEGIN
        INSERT OR IGNORE INTO source_records(id,user_id,scope,data)
        SELECT memory_source_id(NEW.user_id,NEW.origin_key),NEW.user_id,
          COALESCE(json_extract(m.metadata_json,'$.scope'),'user'),
          memory_source(NEW.user_id,NEW.origin_key,NEW.content,NEW.source,NEW.thread_id,NEW.message_id,NEW.created_at,COALESCE(json_extract(m.metadata_json,'$.scope'),'user'))
        FROM memories m WHERE m.id=NEW.memory_id AND m.user_id=NEW.user_id;
        INSERT OR IGNORE INTO memory_links(id,user_id,scope,data)
        SELECT memory_link_id(NEW.memory_id,NEW.origin_key),NEW.user_id,
          COALESCE(json_extract(m.metadata_json,'$.scope'),'user'),
          json_object('id',memory_link_id(NEW.memory_id,NEW.origin_key),'relation','policy_evidence','from',NEW.memory_id,
            'to',memory_source_id(NEW.user_id,NEW.origin_key),'origin_key',NEW.origin_key,'evidence_id',NEW.id,
            'content',NEW.content,'source',NEW.source,'thread_id',NEW.thread_id,'message_id',NEW.message_id,'created_at',NEW.created_at,'legacy',NEW.legacy)
        FROM memories m WHERE m.id=NEW.memory_id AND m.user_id=NEW.user_id;
    """
        + refresh
        + " END"
    )
    conn.execute(
        """CREATE TRIGGER evidence_delete INSTEAD OF DELETE ON memory_evidence BEGIN
        DELETE FROM memory_links WHERE id=memory_link_id(OLD.memory_id,OLD.origin_key) AND user_id=OLD.user_id;
    END"""
    )


def evidence_source_id(storage, user, origin):
    found = storage._conn.execute(
        "SELECT json_extract(data,'$.to') FROM memory_links WHERE user_id=? AND json_extract(data,'$.relation')='policy_evidence' AND json_extract(data,'$.origin_key')=? LIMIT 1",
        (user, origin),
    ).fetchone()
    if found:
        return found[0]
    context = storage._typed_context or {}
    if context.get("source_refs"):
        return context["source_refs"][0]
    return stable_id(user, "policy-evidence", origin)


def source_from_evidence(
    user, origin, content, client, thread, message, created, scope
):
    sid = stable_id(user, "policy-evidence", origin)
    return {
        "id": sid,
        "source_kind": "user_report",
        "source_event_id": origin,
        "source_ref": "",
        "scope": scope,
        "thread_id": thread,
        "task_id": thread or "manual",
        "recorded_at": created,
        "observed_at": None,
        "content": content,
        "content_hash": stable_id(content),
        "evidence_identity": origin,
        "retention_policy": "persist",
        "metadata": {"client": client, "thread_id": thread, "message_id": message},
    }


def object_from_policy(storage, table, policy):
    # A score/state update must preserve the original object and its native fields.
    existing = storage._conn.execute(
        f"SELECT data FROM {table} WHERE id=? AND user_id=?",
        (policy["id"], policy["user_id"]),
    ).fetchone()
    data = json.loads(existing[0]) if existing else dict(storage._typed_context or {})
    user, mid = policy["user_id"], policy["id"]
    metadata = json.loads(policy["metadata_json"] or "{}")
    role = policy["state_role"]
    data.update(
        id=mid,
        content=policy["content"],
        scope=metadata.get("scope", "user"),
        recorded_at=data.get("recorded_at") or policy["created_at"],
        updated_at=policy["updated_at"],
        metadata=metadata,
        _policy=policy,
        memory_type=policy["memory_type"],
    )
    if table == "working_states":
        data.update(
            user_id=user,
            thread_id=metadata.get("thread_id") or "policy:" + mid,
            task_id=metadata.get("task_id") or "policy:" + mid,
            revision=data.get("revision", 0),
            goals=data.get("goals", []),
            constraints=data.get("constraints", []),
            observations=data.get("observations", []),
            active_knowledge=data.get("active_knowledge", []),
            task_state=data.get("task_state", {}),
            open_questions=data.get("open_questions", []),
            candidate_actions=data.get("candidate_actions", []),
            selected_action=data.get("selected_action"),
            status="completed" if role == "archived" else "active",
            created_at=policy["created_at"],
        )
    elif table == "semantic_assertions":
        data.update(
            subject=data.get("subject", user),
            predicate=data.get("predicate") or policy["memory_key"],
            value=(
                data.get("value")
                if (storage._typed_context or existing) and "value" in data
                else policy["memory_value"]
            ),
            evidence_text=data.get("evidence_text") or policy["content"],
            valid_from=data.get("valid_from"),
            valid_to=data.get("valid_to"),
            epistemic_status=data.get(
                "epistemic_status",
                (
                    "legacy_unverified"
                    if getattr(storage, "_importing_records", False)
                    else "explicit"
                ),
            ),
            confidence=policy["confidence"],
            cardinality=data.get("cardinality", "single"),
            correction=data.get("correction", False),
            status=(
                "legacy_unverified"
                if data.get("epistemic_status") == "legacy_unverified"
                else role
            ),
            version=data.get("version", 1),
            supersedes_ids=data.get("supersedes_ids", []),
        )
    elif table == "semantic_documents":
        data.update(
            document_id=data.get("document_id") or "record:" + mid,
            document_version=data.get("document_version", "1"),
            section_or_locator=data.get("section_or_locator", ""),
            epistemic_status=data.get(
                "epistemic_status",
                (
                    "legacy_unverified"
                    if getattr(storage, "_importing_records", False)
                    else "explicit"
                ),
            ),
            status=(
                "legacy_unverified"
                if data.get("epistemic_status") == "legacy_unverified"
                else role
            ),
        )
    elif table == "episode_events":
        data.update(
            observation=data.get("observation") or policy["content"],
            actor=data.get("actor", "user"),
            event_kind=data.get("event_kind", "input"),
            outcome=data.get("outcome", "unknown"),
            occurred_at=data.get("occurred_at"),
            episode_id=data.get("episode_id")
            or stable_id(user, "episode", metadata.get("thread_id") or mid),
            thread_id=data.get("thread_id") or metadata.get("thread_id") or "manual",
            task_id=data.get("task_id") or metadata.get("task_id") or "manual",
            sequence_no=data.get("sequence_no", 1),
            status=role,
        )
    else:
        data.update(
            procedure_id=data.get("procedure_id") or stable_id(user, "procedure", mid),
            version=data.get("version", 1),
            description=data.get("description") or policy["content"],
            kind=data.get("kind", "reasoning"),
            epistemic_status=data.get(
                "epistemic_status",
                (
                    "legacy_unverified"
                    if getattr(storage, "_importing_records", False)
                    else "explicit"
                ),
            ),
            implementation_ref=data.get("implementation_ref"),
            status=data.get("status", "draft"),
            implementation_hash=data.get("implementation_hash"),
            validation_refs=data.get("validation_refs", []),
            created_at=policy["created_at"],
        )
    # Merge registered typed sources with evidence sources from the compatibility projection.
    links = storage._conn.execute(
        "SELECT json_extract(data,'$.to') FROM memory_links WHERE user_id=? AND json_extract(data,'$.relation')='policy_evidence' AND json_extract(data,'$.from')=?",
        (user, mid),
    )
    refs = set(data.get("source_refs", [])) | {row[0] for row in links}
    data["source_refs"] = sorted(refs)
    if table == "semantic_assertions":
        data["evidence_ids"] = sorted(
            {
                (storage._typed_repo.get("source_records", user, ref) or {}).get(
                    "evidence_identity", ref
                )
                for ref in refs
            }
        )
    return data


def prepare_native(storage, table, user, data):
    """Supply the policy record shape for native objects, without changing their lifecycle."""
    if (
        table not in RECORD_TABLES
        or table == "working_states"
        or not storage._typed_enabled
    ):
        return data
    from ..encoding import Encoder, PROTECTED_TAGS
    from ..retrieval.lexical import normalize_text

    kind = {"episode_events": "episodic", "procedure_versions": "procedural"}.get(
        table, "semantic"
    )
    role = {
        "disputed": "candidate",
        "draft": "current",
        "validated": "current",
        "enabled": "current",
        "disabled": "history",
        "configured": "current",
        "legacy_unverified": "candidate",
    }.get(data.get("status", "current"), data.get("status", "current"))
    if "_policy" in data:
        policy = dict(data["_policy"])
        if table != "procedure_versions":
            policy["state_role"] = role
        return {**data, "_policy": policy}
    content = (
        data.get("content")
        or data.get("evidence_text")
        or data.get("observation")
        or data.get("description")
        or ""
    )
    encoder = Encoder(storage)
    key = data.get("predicate") or data.get("document_id")
    metadata = {**data.get("metadata", {}), "scope": data.get("scope", "user")}
    tags = data.get("tags") or metadata.get("tags", [])
    importance = data.get("importance", 0.7)
    confidence = data.get("confidence", 0.8)
    saliency, goal, preference, attention = encoder.attention_profile(
        user, content, key, tags, importance, ""
    )
    policy = dict(zip(COLUMNS, [None] * len(COLUMNS)))
    policy.update(
        id=data["id"],
        user_id=user,
        content=content,
        normalized_content=normalize_text(content),
        memory_key=key,
        memory_value=str(data.get("value") or ""),
        memory_type=kind,
        state_role=role,
        source=metadata.get("client", "typed_memory"),
        tags_json=json.dumps(tags, ensure_ascii=False),
        importance=importance,
        confidence=confidence,
        saliency=saliency,
        goal_relevance=goal,
        preference_strength=preference,
        attention_bias=attention,
        write_score=encoder.write_score(user, content, tags, importance, confidence),
        prediction_error=0,
        evidence_count=len(set(data.get("source_refs", []))),
        parent_id=None,
        support_ids_json="[]",
        is_protected=int(kind == "procedural" or bool(set(tags) & PROTECTED_TAGS)),
        created_at=data.get("created_at") or data.get("recorded_at") or iso_now(),
        updated_at=data.get("updated_at") or data.get("recorded_at") or iso_now(),
        last_accessed_at=None,
        metadata_json=json.dumps(metadata, ensure_ascii=False),
    )
    return {**data, "_policy": policy}


def attach_sources(storage, user, data):
    if "_policy" not in data:
        return
    for ref in data.get("source_refs", []):
        source = storage._typed_repo.get("source_records", user, ref)
        if not source or not source.get("content"):
            continue
        origin = source.get("evidence_identity", ref)
        thread, message = source_message_context(source)
        # Use the original registered source; no duplicate source body is needed.
        lid = stable_id(data["id"], "evidence", origin)
        link = {
            "id": lid,
            "relation": "policy_evidence",
            "from": data["id"],
            "to": ref,
            "origin_key": origin,
            "evidence_id": stable_id(lid, "evidence"),
            "source": data["_policy"]["source"],
            "thread_id": thread,
            "message_id": message,
            "created_at": source.get("recorded_at"),
            "legacy": int(data.get("epistemic_status") == "legacy_unverified"),
        }
        storage._typed_repo.put(
            "memory_links", user, lid, link, source.get("scope", "user")
        )
