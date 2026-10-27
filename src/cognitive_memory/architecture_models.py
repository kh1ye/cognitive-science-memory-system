"""CoALA-inspired contracts. Fields and lifecycle rules are project engineering choices."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .models import iso_now


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class WorkingState(Contract):
    user_id: str
    thread_id: str
    task_id: str
    revision: int = 0
    goals: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    observations: list[dict] = Field(default_factory=list)
    active_knowledge: list[dict] = Field(default_factory=list)
    task_state: dict = Field(default_factory=dict)
    open_questions: list[str] = Field(default_factory=list)
    candidate_actions: list[dict] = Field(default_factory=list)
    selected_action: dict | None = None
    status: Literal["active", "paused", "completed"] = "active"
    created_at: str = Field(default_factory=iso_now)
    updated_at: str = Field(default_factory=iso_now)


class EpisodeEvent(Contract):
    observation: str
    actor: Literal["user", "system", "tool", "model"] = "user"
    event_kind: Literal[
        "input", "action", "result", "feedback", "correction", "summary"
    ] = "input"
    occurred_at: str | None = None
    action_ref: str | None = None
    outcome: Literal["unknown", "partial", "failed", "succeeded"] = "unknown"
    parent_event_id: str | None = None
    corrects: str | None = None
    source_refs: list[str] = Field(default_factory=list)


class SemanticAssertion(Contract):
    sensitive: bool = False
    evidence_text: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    value: Any
    scope: str = "user"
    valid_from: str | None = None
    valid_to: str | None = None
    epistemic_status: Literal[
        "explicit", "supported", "inferred", "legacy_unverified"
    ] = "explicit"
    status: Literal[
        "current", "disputed", "history", "candidate", "legacy_unverified"
    ] = "current"
    confidence: float = Field(default=0.8, ge=0, le=1)
    cardinality: Literal["single", "multiple"] = "single"
    correction: bool = False
    source_refs: list[str] = Field(default_factory=list)


class SemanticDocument(Contract):
    document_id: str
    document_version: str
    section_or_locator: str = ""
    content: str = Field(min_length=1)
    scope: str = "user"
    source_ref: str


class ProcedureProposal(Contract):
    description: str = Field(min_length=1)
    kind: Literal["reasoning", "retrieval", "learning", "grounding", "decision"]
    implementation_ref: str | None = None
    source_refs: list[str] = Field(default_factory=list)


class WorkingStatePatch(Contract):
    """Observation extraction can propose task context, not provenance or execution status."""

    goals: list[str] | None = None
    constraints: list[str] | None = None
    open_questions: list[str] | None = None
    task_state: dict | None = None


class ObservationAnalysis(Contract):
    working_state_patch: WorkingStatePatch = Field(default_factory=WorkingStatePatch)
    episode_candidates: list[EpisodeEvent] = Field(default_factory=list)
    semantic_candidates: list[SemanticAssertion] = Field(default_factory=list)
    procedure_proposals: list[ProcedureProposal] = Field(default_factory=list)


class Observation(Contract):
    user_id: str = Field(min_length=1)
    thread_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    source_kind: Literal[
        "user_report",
        "system_observation",
        "tool_result",
        "model_inference",
        "document",
    ] = "user_report"
    source_event_id: str = Field(min_length=1)
    source_ref: str = ""
    observed_at: str | None = None
    content: str = Field(min_length=1, max_length=20000)
    scope: str = "user"
    retention_policy: Literal["persist", "no_long_term", "no_persist"] = "persist"
    consent: bool = False


class Action(Contract):
    name: Literal["retrieve", "learn", "reply", "stop"]
    arguments: dict = Field(default_factory=dict)
    reason: str = ""
    status: Literal["proposed", "running", "succeeded", "failed"] = "proposed"
