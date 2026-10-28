"""Typed memory services. No dynamic imports/eval or generated-code execution."""

import hashlib
import inspect
import json
from uuid import uuid4

from pydantic import BaseModel, Field

from .architecture_models import (
    EpisodeEvent,
    Observation,
    ObservationAnalysis,
    ProcedureProposal,
    SemanticAssertion,
    SemanticDocument,
    WorkingState,
)
from .models import iso_now
from .provenance import source_span
from .retrieval.lexical import cosine_similarity as lexical_score
from .storage.architecture import TABLES, ArchitectureRepository, stable_id


class QueryInput(BaseModel):
    query: str
    scope: str = "user"


class TextInput(BaseModel):
    text: str


class KnowledgeInput(BaseModel):
    assertion: SemanticAssertion


class DecisionInput(BaseModel):
    completed: list[str] = Field(default_factory=list)


def normalize_text_program(service, user_id, args):
    return {"text": " ".join(args.text.split())}


def retrieve_program(service, user_id, args):
    return {"items": service.retrieve_knowledge(user_id, args.query, scope=args.scope)}


def learn_program(service, user_id, args):
    return service.upsert_assertion(user_id, args.assertion)


def decision_program(service, user_id, args):
    return {
        "action": next(
            (a for a in ["retrieve", "reply", "learn"] if a not in args.completed),
            "stop",
        )
    }


# A code-owned allowlist: users may propose references, never replace implementations.
BUILTINS = {
    "text.normalize": ("reasoning", TextInput, normalize_text_program),
    "knowledge.retrieve": ("retrieval", QueryInput, retrieve_program),
    "knowledge.learn": ("learning", KnowledgeInput, learn_program),
    "text.emit": (
        "grounding",
        TextInput,
        lambda service, user, args: {"text": args.text},
    ),
    "decision.next": ("decision", DecisionInput, decision_program),
}


class MemoryArchitecture:
    def __init__(self, storage, *, analyzer=None):
        self.storage = storage
        self.repo = ArchitectureRepository(storage)
        self.analyzer = analyzer
        # Cross-database transcript cleanup is coordinated by the execution layer.
        self.source_delete_hooks = []

    def _link(self, user, relation, origin, target):
        key = stable_id(user, relation, origin, target)
        self.repo.put(
            "memory_links",
            user,
            key,
            {"id": key, "relation": relation, "from": origin, "to": target},
        )

    def working_state(self, user, thread, task):
        key = stable_id(user, thread, task)
        data = self.repo.get("working_states", user, key)
        return (
            WorkingState.model_validate(data)
            if data
            else WorkingState(user_id=user, thread_id=thread, task_id=task)
        )

    def update_working_state(self, user, thread, task, patch):
        with self.storage.transaction():
            state = self.working_state(user, thread, task)
            allowed = set(WorkingState.model_fields) - {
                "user_id",
                "thread_id",
                "task_id",
                "revision",
                "created_at",
                "updated_at",
            }
            if set(patch) - allowed:
                raise ValueError("Invalid working-state patch")
            state = WorkingState.model_validate(
                {
                    **state.model_dump(),
                    **patch,
                    "revision": state.revision + 1,
                    "updated_at": iso_now(),
                }
            )
            self.repo.put(
                "working_states",
                user,
                stable_id(user, thread, task),
                state.model_dump(),
            )
            return state.model_dump()

    def clear_task(self, user, thread, task):
        with self.storage.transaction():
            self.repo.delete("working_states", user, stable_id(user, thread, task))

    def register_source(self, observation):
        o = Observation.model_validate(observation)
        key = stable_id(o.user_id, o.source_kind, o.source_event_id)
        existing = self.repo.get("source_records", o.user_id, key)
        if existing:
            if (
                existing["content_hash"] != stable_id(o.content)
                or existing["scope"] != o.scope
                or existing.get("retention_policy") != o.retention_policy
            ):
                raise ValueError("Source identity reused with different content/scope")
            return existing
        data = {
            "id": key,
            "source_kind": o.source_kind,
            "source_event_id": o.source_event_id,
            "source_ref": o.source_ref,
            "scope": o.scope,
            "thread_id": o.thread_id,
            "task_id": o.task_id,
            "observed_at": o.observed_at,
            "recorded_at": iso_now(),
            "content_hash": stable_id(o.content),
            "evidence_identity": stable_id(
                o.user_id, o.source_kind, o.source_ref or o.source_event_id
            ),
            "content": o.content if o.retention_policy == "persist" else None,
            "retention_policy": o.retention_policy,
        }
        return self.repo.put("source_records", o.user_id, key, data, o.scope)

    def _check_sources(self, user, sources, scope=None):
        if not sources:
            raise ValueError("At least one registered source is required")
        for source in set(sources):
            row = self.repo.get("source_records", user, source)
            if (
                row is None
                or row.get("retention_policy") != "persist"
                or (scope is not None and row["scope"] != scope)
            ):
                raise ValueError("Unknown or out-of-scope source")
        return sorted(set(sources))

    def append_episode(self, user, thread, task, event, *, source_event_id):
        e = EpisodeEvent.model_validate(event)
        with self.storage.transaction():
            sources = self._check_sources(user, e.source_refs)
            key = stable_id(user, "event", source_event_id)
            existing = self.repo.get("episode_events", user, key)
            if existing:
                return existing
            for ref in [e.parent_event_id, e.corrects]:
                if ref and not self.repo.get("episode_events", user, ref):
                    raise ValueError("Unknown parent/corrected event")
            episode = stable_id(user, "episode", thread, task)
            if not self.repo.get("episodes", user, episode):
                self.repo.put(
                    "episodes",
                    user,
                    episode,
                    {
                        "id": episode,
                        "thread_id": thread,
                        "task_id": task,
                        "status": "open",
                        "recorded_at": iso_now(),
                    },
                )
            sequence = (
                sum(
                    r.get("episode_id") == episode
                    for r in self.repo.rows("episode_events", user)
                )
                + 1
            )
            data = {
                **e.model_dump(),
                "id": key,
                "episode_id": episode,
                "thread_id": thread,
                "task_id": task,
                "sequence_no": sequence,
                "recorded_at": iso_now(),
                "source_refs": sources,
            }
            self.repo.put(
                "episode_events",
                user,
                key,
                data,
                self.repo.get("source_records", user, sources[0])["scope"],
            )
            for source in sources:
                self._link(user, "derived_from", key, source)
            if e.corrects:
                self._link(user, "corrects", key, e.corrects)
            return data

    def upsert_assertion(self, user, assertion):
        a = SemanticAssertion.model_validate(assertion)
        with self.storage.transaction():
            sources = self._check_sources(user, a.source_refs, a.scope)
            evidence = next(
                (
                    span
                    for ref in sources
                    if (
                        span := source_span(
                            a.evidence_text,
                            self.repo.get("source_records", user, ref).get("content")
                            or "",
                        )
                    )
                    is not None
                ),
                None,
            )
            if evidence is None:
                raise ValueError("Assertion has no source evidence")
            a = a.model_copy(update={"evidence_text": evidence})
            rows = self.repo.rows("semantic_assertions", user, a.scope)
            same_relation = [
                r
                for r in rows
                if r["subject"] == a.subject and r["predicate"] == a.predicate
            ]
            same = next(
                (
                    r
                    for r in same_relation
                    if r["value"] == a.value
                    and r["status"] in ("current", "disputed", "candidate")
                    and r["valid_from"] == a.valid_from
                    and r["valid_to"] == a.valid_to
                ),
                None,
            )
            if same:
                same["source_refs"] = sorted(set(same["source_refs"] + sources))
                same["evidence_ids"] = sorted(
                    {
                        self.repo.get("source_records", user, ref)["evidence_identity"]
                        for ref in same["source_refs"]
                    }
                )
                for source in sources:
                    self._link(user, "supports", source, same["id"])
                return self.repo.put(
                    "semantic_assertions", user, same["id"], same, a.scope
                )
            overlapping = [
                r
                for r in same_relation
                if r["status"] in ("current", "disputed")
                and not (
                    a.valid_to and r["valid_from"] and a.valid_to <= r["valid_from"]
                )
                and not (
                    a.valid_from and r["valid_to"] and a.valid_from >= r["valid_to"]
                )
            ]
            status = "candidate" if a.epistemic_status == "inferred" else a.status
            supersedes = []
            if (
                a.cardinality == "single"
                and overlapping
                and a.epistemic_status != "inferred"
            ):
                owned_correction = (
                    a.correction
                    and a.epistemic_status == "explicit"
                    and a.subject == user
                    and all(
                        self.repo.get("source_records", user, s)["source_kind"]
                        == "user_report"
                        for s in sources
                    )
                )
                for old in overlapping:
                    if old["value"] == a.value:
                        continue
                    if owned_correction:
                        old["status"] = "history"
                        supersedes.append(old["id"])
                    else:
                        old["status"] = "disputed"
                        status = "disputed"
                    self.repo.put("semantic_assertions", user, old["id"], old, a.scope)
            key = stable_id(user, "assertion", a.model_dump(), sources)
            data = {
                **a.model_dump(),
                "id": key,
                "status": status,
                "source_refs": sources,
                "evidence_ids": sorted(
                    {
                        self.repo.get("source_records", user, ref)["evidence_identity"]
                        for ref in sources
                    }
                ),
                "version": len(same_relation) + 1,
                "recorded_at": iso_now(),
                "supersedes_ids": supersedes,
            }
            self.repo.put("semantic_assertions", user, key, data, a.scope)
            for source in sources:
                self._link(user, "supports", source, key)
            for old in supersedes:
                self._link(user, "supersedes", key, old)
            if status == "disputed":
                for old in overlapping:
                    self._link(user, "contradicts", key, old["id"])
            return data

    def ingest_document(self, user, document):
        d = SemanticDocument.model_validate(document)
        with self.storage.transaction():
            self._check_sources(user, [d.source_ref], d.scope)
            key = stable_id(
                user, d.document_id, d.document_version, d.section_or_locator
            )
            existing = self.repo.get("semantic_documents", user, key)
            if existing and existing["content"] != d.content:
                raise ValueError("Document versions are immutable")
            data = {
                **d.model_dump(),
                "id": key,
                "content_hash": stable_id(d.content),
                "source_refs": [d.source_ref],
                "status": "current",
                "recorded_at": iso_now(),
            }
            self._link(user, "derived_from", key, d.source_ref)
            return self.repo.put("semantic_documents", user, key, data, d.scope)

    def propose_procedure(self, user, proposal, *, key=None):
        p = ProcedureProposal.model_validate(proposal)
        with self.storage.transaction():
            sources = self._check_sources(user, p.source_refs)
            scope = self.repo.get("source_records", user, sources[0])["scope"]
            self._check_sources(user, sources, scope)
            procedure = key or str(uuid4())
            pid = stable_id(user, procedure)
            versions = [
                r
                for r in self.repo.rows("procedure_versions", user)
                if r.get("procedure_id") == pid
            ]
            registry = self.repo.get("procedures", user, pid) or {}
            version = max(
                [0, *registry.get("deleted_versions", []), *[r["version"] for r in versions if isinstance(r.get("version"), int)]]
            ) + 1
            vid = stable_id(user, pid, version)
            data = {
                **p.model_dump(),
                "id": vid,
                "procedure_id": pid,
                "scope": scope,
                "version": version,
                "status": "draft",
                "implementation_hash": None,
                "validation_refs": [],
                "created_at": iso_now(),
                "preconditions": [],
                "postconditions": [],
            }
            if not self.repo.get("procedures", user, pid):
                self.repo.put(
                    "procedures",
                    user,
                    pid,
                    {
                        "id": pid,
                        "name": procedure,
                        "active_version": None,
                        "scope": scope,
                    },
                )
            return self.repo.put("procedure_versions", user, vid, data)

    def validate_procedure(self, user, version_id):
        with self.storage.transaction():
            p = self.repo.get("procedure_versions", user, version_id)
            if (
                not p
                or p.get("implementation_ref") not in BUILTINS
                or p.get("status") == "legacy_unverified"
            ):
                raise ValueError(
                    "Only code-owned allowlisted implementations can be validated"
                )
            kind, schema, function = BUILTINS[p["implementation_ref"]]
            if kind != p["kind"]:
                raise ValueError("Implementation kind mismatch")
            p.update(
                status="validated",
                input_schema=schema.model_json_schema(),
                output_schema={"type": "object"},
                implementation_hash=hashlib.sha256(
                    inspect.getsource(function).encode()
                ).hexdigest(),
                validation_refs=["code-owned-allowlist-v1"],
            )
            return self.repo.put("procedure_versions", user, version_id, p)

    def activate_procedure(self, user, version_id, enabled=True):
        with self.storage.transaction():
            p = self.repo.get("procedure_versions", user, version_id)
            if not p or p["status"] not in ("validated", "enabled", "disabled"):
                raise ValueError("Procedure must be validated before activation")
            parent = self.repo.get("procedures", user, p["procedure_id"])
            for old in self.repo.rows("procedure_versions", user):
                if (
                    old.get("procedure_id") == p["procedure_id"]
                    and old["status"] == "enabled"
                ):
                    old["status"] = "disabled"
                    self.repo.put("procedure_versions", user, old["id"], old)
            p["status"] = "enabled" if enabled else "disabled"
            parent["active_version"] = version_id if enabled else None
            self.repo.put("procedures", user, parent["id"], parent)
            return self.repo.put("procedure_versions", user, p["id"], p)

    def install_builtins(self, user):
        for name, (kind, _, _) in BUILTINS.items():
            pid = stable_id(user, name)
            if self.repo.get("procedures", user, pid):
                continue
            with self.storage.transaction():
                source = self.register_source(
                    Observation(
                        user_id=user,
                        thread_id="system",
                        task_id="registry",
                        source_kind="system_observation",
                        source_event_id="builtin:" + name,
                        content=name,
                    )
                )
            p = self.propose_procedure(
                user,
                ProcedureProposal(
                    description=name,
                    kind=kind,
                    implementation_ref=name,
                    source_refs=[source["id"]],
                ),
                key=name,
            )
            self.validate_procedure(user, p["id"])
            self.activate_procedure(user, p["id"])

    def register_model_configuration(self, user, *, provider, model):
        """Record hosted configuration only; no weights or credentials are stored."""
        with self.storage.transaction():
            pid = stable_id(user, "hosted-model", provider)
            vid = stable_id(pid, model)
            self.repo.put(
                "procedures",
                user,
                pid,
                {"id": pid, "name": "hosted-model:" + provider, "active_version": vid},
            )
            self.repo.put(
                "procedure_versions",
                user,
                vid,
                {
                    "id": vid,
                    "procedure_id": pid,
                    "version": model,
                    "kind": "reasoning",
                    "description": "Hosted model configuration; provider version may be an alias",
                    "implementation_ref": "hosted-model",
                    "provider": provider,
                    "model": model,
                    "status": "configured",
                    "validation_refs": [],
                    "source_refs": [],
                    "weights_managed": False,
                },
            )

    def execute_procedure(
        self, user, version_id, arguments, *, run_key, thread="system", task="execution"
    ):
        with self.storage.transaction():
            key = stable_id(user, "run", run_key)
            previous = self.repo.get("procedure_runs", user, key)
            if previous:
                if previous["version_id"] != version_id or previous[
                    "parameter_hash"
                ] != stable_id(arguments):
                    raise ValueError(
                        "Run identity reused with different procedure or arguments"
                    )
                return previous
            p = self.repo.get("procedure_versions", user, version_id)
            if (
                not p
                or p["status"] != "enabled"
                or p["implementation_ref"] not in BUILTINS
            ):
                raise ValueError("Procedure is not enabled")
            _, schema, function = BUILTINS[p["implementation_ref"]]
            source = self.register_source(
                Observation(
                    user_id=user,
                    thread_id=thread,
                    task_id=task,
                    source_kind="system_observation",
                    source_event_id="run:" + run_key,
                    content="Procedure invocation",
                )
            )
            run = {
                "id": key,
                "version_id": version_id,
                "version": p["version"],
                "procedure_id": p["procedure_id"],
                "parameter_hash": stable_id(arguments),
                "status": "running",
                "result": None,
                "error": None,
                "source_refs": [source["id"]],
                "recorded_at": iso_now(),
            }
            try:
                validated = schema.model_validate(arguments)
                result = function(self, user, validated)
                if not isinstance(result, dict):
                    raise TypeError("Invalid procedure output")
                run.update(status="succeeded", result=result)
            except Exception as error:  # noqa: BLE001 -- record actual execution failures
                run.update(status="failed", error=type(error).__name__)

            def result_sources(value):
                if isinstance(value, dict):
                    return set(value.get("source_refs", [])) | set().union(
                        *(result_sources(v) for v in value.values()), set()
                    )
                if isinstance(value, list):
                    return set().union(*(result_sources(v) for v in value), set())
                return set()

            run["source_refs"] = sorted(
                set(run["source_refs"]) | result_sources(run.get("result"))
            )
            self.repo.put("procedure_runs", user, key, run)
            event = self.append_episode(
                user,
                thread,
                task,
                EpisodeEvent(
                    actor="system",
                    event_kind="result",
                    observation="Procedure execution",
                    action_ref=key,
                    outcome=run["status"],
                    source_refs=[source["id"]],
                ),
                source_event_id="run-result:" + run_key,
            )
            self._link(user, "used_procedure", event["id"], version_id)
            return run

    def observe(self, observation, analysis=None):
        o = Observation.model_validate(observation)
        from .value import context_only

        if o.retention_policy == "persist" and context_only(o.content):
            o = o.model_copy(update={"retention_policy": "no_long_term"})
        # Privacy gate runs before source registration, state, extraction or logging.
        if o.retention_policy == "no_persist":
            return {"status": "not_persisted", "operations": [], "analysis": None}
        from .encoding import Encoder

        reason = Encoder(self.storage).privacy_reason(o.content, [], o.consent)
        if reason and o.retention_policy == "persist":
            o = o.model_copy(update={"retention_policy": "no_long_term"})
        if analysis is None:
            if self.analyzer is None:
                analysis = (
                    ObservationAnalysis()
                )  # Unknown text is never promoted to facts by keyword heuristics.
            else:
                analysis = self.analyzer(o)
        a = ObservationAnalysis.model_validate(analysis)
        if (
            o.source_kind == "user_report"
            and a.semantic_candidates
            and not a.has_explicit_candidates()
        ):
            o = o.model_copy(update={"retention_policy": "no_long_term"})
        if any(s.sensitive for s in a.semantic_candidates) and not o.consent:
            o = o.model_copy(update={"retention_policy": "no_long_term"})
        with self.storage.transaction():
            source = self.register_source(o)
            state = self.working_state(o.user_id, o.thread_id, o.task_id)
            if source["id"] not in [r.get("source_id") for r in state.observations]:
                patch = {
                    **a.working_state_patch.model_dump(
                        exclude_unset=True, exclude_none=True
                    ),
                    "observations": [
                        *state.observations,
                        {"source_id": source["id"], "content": o.content},
                    ],
                }
                self.update_working_state(o.user_id, o.thread_id, o.task_id, patch)
        operations = []
        if o.retention_policy == "persist":
            candidates = [("episodic", e.model_dump()) for e in a.episode_candidates]
            candidates += [
                ("semantic", s.model_copy(update={"scope": o.scope}).model_dump())
                for s in a.semantic_candidates
            ]
            candidates += [
                ("procedural", p.model_dump()) for p in a.procedure_proposals
            ]
            for index, (module, candidate) in enumerate(candidates):
                # A quoted source span proves provenance, not the truth of an inference.
                # Preserve original indexes so retries keep the same operation identities.
                if (
                    o.source_kind == "user_report"
                    and module == "semantic"
                    and candidate["epistemic_status"] != "explicit"
                ):
                    continue
                opkey = stable_id(o.user_id, source["id"], module, index)
                with self.storage.transaction():
                    previous = self.repo.get("learning_operations", o.user_id, opkey)
                    if previous and previous["status"] == "succeeded":
                        operations.append(previous)
                        continue
                    operation = {
                        "id": opkey,
                        "idempotency_key": opkey,
                        "target_module": module,
                        "source_refs": [source["id"]],
                        "status": "failed",
                        "result_refs": [],
                        "error": None,
                    }
                    try:
                        self.repo.begin_learning_item()
                        candidate["source_refs"] = [source["id"]]
                        if module == "episodic":
                            candidate["occurred_at"] = (
                                candidate.get("occurred_at") or o.observed_at
                            )
                            candidate["actor"] = {
                                "user_report": "user",
                                "system_observation": "system",
                                "tool_result": "tool",
                                "model_inference": "model",
                                "document": "user",
                            }[o.source_kind]
                            if candidate["observation"] not in o.content:
                                raise ValueError("Event has no source evidence")
                            result = self.append_episode(
                                o.user_id,
                                o.thread_id,
                                o.task_id,
                                candidate,
                                source_event_id=opkey,
                            )
                        elif module == "semantic":
                            result = self.upsert_assertion(o.user_id, candidate)
                        else:
                            result = self.propose_procedure(
                                o.user_id, candidate, key=opkey
                            )
                        self.repo.release_learning_item()
                        operation.update(status="succeeded", result_refs=[result["id"]])
                        if module == "semantic":
                            operation.update(
                                result_status=result["status"],
                                epistemic_status=result["epistemic_status"],
                            )
                    except Exception as error:  # noqa: BLE001 -- isolate partial learning failure
                        self.repo.rollback_learning_item()
                        self.repo.release_learning_item()
                        operation["error"] = type(error).__name__
                    self.repo.put(
                        "learning_operations", o.user_id, opkey, operation, o.scope
                    )
                    operations.append(operation)
        return {
            "status": "partial_failure"
            if any(r["status"] == "failed" for r in operations)
            else o.retention_policy,
            "source_id": source["id"],
            "analysis": a.model_dump(),
            "operations": operations,
        }

    def retrieve_episodes(
        self, user, query="", *, scope="user", task=None, outcome=None
    ):
        rows = [
            r
            for r in self.repo.rows("episode_events", user, scope)
            if r.get("status") != "legacy_unverified"
            and (task is None or r.get("task_id") == task)
            and (outcome is None or r.get("outcome") == outcome)
        ]
        return sorted(
            rows,
            key=lambda r: (
                lexical_score(query, r.get("observation", "")),
                r.get("occurred_at") or "",
                r["sequence_no"],
            ),
            reverse=True,
        )[:20]

    def retrieve_knowledge(
        self,
        user,
        query="",
        *,
        scope="user",
        at=None,
        history=False,
        subject=None,
        predicate=None,
    ):
        rows = self.repo.rows("semantic_assertions", user, scope) + self.repo.rows(
            "semantic_documents", user, scope
        )
        rows = [
            r
            for r in rows
            if (history or r["status"] in ("current", "disputed"))
            and (subject is None or r.get("subject") == subject)
            and (predicate is None or r.get("predicate") == predicate)
            and (not r.get("valid_from") or r["valid_from"] <= (at or iso_now()))
            and (not r.get("valid_to") or r["valid_to"] > (at or iso_now()))
        ]
        return sorted(
            rows,
            key=lambda r: lexical_score(query, json.dumps(r, ensure_ascii=False)),
            reverse=True,
        )[:20]

    def retrieve_procedures(self, user, query="", *, kind=None, scope="user"):
        rows = [
            r
            for r in self.repo.rows("procedure_versions", user, scope)
            if r["status"] == "enabled" and (kind is None or r["kind"] == kind)
        ]
        return sorted(
            rows, key=lambda r: lexical_score(query, r["description"]), reverse=True
        )

    def retrieve(
        self, user, thread, task, query, *, modules=("semantic",), scope="user"
    ):
        result = []
        for module in modules:
            if module == "working":
                result.append(
                    {
                        "module": module,
                        "state": self.working_state(user, thread, task).model_dump(),
                    }
                )
                continue
            if module not in ("semantic", "episodic", "procedural"):
                raise ValueError("Invalid retrieval module")
            function = {
                "semantic": self.retrieve_knowledge,
                "episodic": self.retrieve_episodes,
                "procedural": self.retrieve_procedures,
            }[module]
            rows = function(user, query, scope=scope)
            result.extend(
                {
                    "module": module,
                    "memory_id": r["id"],
                    "version": r.get("version", r.get("document_version", 1)),
                    "source_refs": r.get("source_refs", []),
                    "purpose": query,
                    "record": r,
                    "id": r["id"],
                    "memory_type": module,
                    "state_role": r.get("status", "recorded"),
                    "content": r.get("content")
                    or r.get("evidence_text")
                    or r.get("observation")
                    or r.get("description", ""),
                }
                for r in rows[:5]
            )
        self.update_working_state(user, thread, task, {"active_knowledge": result})
        return result

    def remove_object_references(self, user, removed):
        """Detach deleted objects without deleting shared sources or conversations."""
        for state in self.repo.rows("working_states", user):
            refs = state.get("active_knowledge", [])
            remaining = [r for r in refs if r.get("memory_id", r.get("id")) not in removed]
            if len(remaining) != len(refs):
                state["active_knowledge"] = remaining
                self.repo.put("working_states", user, stable_id(user, state["thread_id"], state["task_id"]), state)
        for link in self.repo.rows("memory_links", user):
            if link["from"] in removed or link["to"] in removed:
                self.repo.delete("memory_links", user, link["id"])
        for operation in self.repo.rows("learning_operations", user):
            refs = operation.get("result_refs", [])
            deleted = [ref for ref in refs if ref in removed]
            if deleted:
                operation["result_refs"] = [ref for ref in refs if ref not in removed]
                operation["deleted_result_refs"] = sorted(set(operation.get("deleted_result_refs", []) + deleted))
                operation["result_status"] = "deleted"
                # Keep successful operation identity: replay must not recreate deleted memory.
                source = next((self.repo.get("source_records", user, ref) for ref in operation.get("source_refs", [])), None)
                self.repo.put("learning_operations", user, operation["id"], operation, source["scope"] if source else "user")

    def delete_object(self, user, module, object_id):
        from .catalog import MODULE_TYPES

        if module not in MODULE_TYPES:
            raise ValueError("Not a managed memory module")
        with self.storage.transaction():
            record = self.repo.get(module, user, object_id)
            if record is None:
                return False
            removed = {object_id}
            if module == "procedure_versions":
                pid = record.get("procedure_id")
                registry = self.repo.get("procedures", user, pid) if pid else None
                if registry:
                    if registry.get("active_version") == object_id:
                        registry["active_version"] = None
                    if isinstance(record.get("version"), int):
                        registry["deleted_versions"] = sorted(set(registry.get("deleted_versions", []) + [record["version"]]))
                    self.repo.put("procedures", user, pid, registry)
                for run in self.repo.rows("procedure_runs", user):
                    if run.get("version_id") == object_id:
                        removed.add(run["id"])
                        self.repo.delete("procedure_runs", user, run["id"])
            self.repo.delete(module, user, object_id)
            self.remove_object_references(user, removed)
            return True

    def delete_source(self, user, source_id):
        with self.storage.transaction():
            source = self.repo.get("source_records", user, source_id)
            if not source:
                return False
            removed = {source_id}
            for table in sorted(
                TABLES - {"working_states", "source_records", "memory_links"}
            ):
                for row in self.repo.rows(table, user):
                    refs = row.get("source_refs", [])
                    if source_id not in refs:
                        continue
                    remaining = [s for s in refs if s != source_id]
                    if remaining and table == "semantic_assertions":
                        row.update(
                            source_refs=remaining,
                            evidence_ids=sorted(
                                {
                                    self.repo.get("source_records", user, ref)[
                                        "evidence_identity"
                                    ]
                                    for ref in remaining
                                }
                            ),
                            status="candidate",
                            evidence_text="",
                        )
                        self.repo.put(table, user, row["id"], row, row["scope"])
                    else:
                        self.repo.delete(table, user, row["id"])
                        removed.add(row["id"])
            for state in self.repo.rows("working_states", user):
                # Purge this task's runtime context, which can include derived prose.
                if (
                    state["thread_id"] == source["thread_id"]
                    and state["task_id"] == source["task_id"]
                ):
                    self.repo.delete(
                        "working_states",
                        user,
                        stable_id(user, state["thread_id"], state["task_id"]),
                    )
                elif any(
                    r.get("memory_id") in removed
                    or source_id in r.get("source_refs", [])
                    for r in state["active_knowledge"]
                ):
                    state["active_knowledge"] = []
                    self.repo.put(
                        "working_states",
                        user,
                        stable_id(user, state["thread_id"], state["task_id"]),
                        state,
                    )
            for link in self.repo.rows("memory_links", user):
                if link["from"] in removed or link["to"] in removed:
                    self.repo.delete("memory_links", user, link["id"])
            self.repo.delete("source_records", user, source_id)
        for hook in self.source_delete_hooks:
            hook(user, source["thread_id"])
        return True
