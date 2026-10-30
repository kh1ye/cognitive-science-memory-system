"""Typed CoALA memory endpoints; user_id is a local namespace, not authentication."""

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import Field

from cognitive_memory.architecture_models import (
    Contract,
    Observation,
    ObservationAnalysis,
    ProcedureProposal,
    SemanticAssertion,
    SemanticDocument,
)

from ..dependencies import MemoryDependency

router = APIRouter(prefix="/api/architecture", tags=["typed memory"])


class ObserveRequest(Contract):
    observation: Observation
    analysis: ObservationAnalysis | None = None


class Owned(Contract):
    user_id: str = Field(min_length=1)


class Patch(Owned):
    patch: dict


class AssertionRequest(Owned):
    assertion: SemanticAssertion


class DocumentRequest(Owned):
    document: SemanticDocument


class ProcedureRequest(Owned):
    proposal: ProcedureProposal
    name: str | None = None


class RunRequest(Owned):
    arguments: dict
    run_key: str
    thread_id: str = "system"
    task_id: str = "execution"


class RetrieveRequest(Owned):
    query: str
    thread_id: str
    task_id: str
    modules: list[Literal["working", "semantic", "episodic", "procedural"]] = Field(
        default_factory=lambda: ["semantic", "episodic"]
    )
    scope: str = "user"


@router.post("/observe")
def observe(body: ObserveRequest, memory: MemoryDependency):
    return memory.architecture.observe(body.observation, body.analysis)


@router.get("/objects/{module}")
def objects(
    module: Literal[
        "working_states",
        "episodes",
        "episode_events",
        "semantic_assertions",
        "semantic_documents",
        "procedures",
        "procedure_versions",
        "procedure_runs",
        "source_records",
        "memory_links",
        "learning_operations",
    ],
    memory: MemoryDependency,
    user_id: str,
    scope: str | None = None,
):
    return {"items": memory.architecture.repo.rows(module, user_id, scope)}


@router.get("/objects/{module}/{object_id}")
def object_detail(
    module: Literal[
        "working_states",
        "episodes",
        "episode_events",
        "semantic_assertions",
        "semantic_documents",
        "procedures",
        "procedure_versions",
        "procedure_runs",
        "source_records",
        "memory_links",
        "learning_operations",
    ],
    object_id: str,
    memory: MemoryDependency,
    user_id: str,
):
    from cognitive_memory.retrieval.lexical import normalize_text

    record = memory.architecture.repo.get(
        module, normalize_text(user_id) or "demo-user", object_id
    )
    if record is None:
        raise HTTPException(404, "Memory object not found")
    return record


@router.get("/working/{thread_id}/{task_id}")
def working(thread_id: str, task_id: str, memory: MemoryDependency, user_id: str):
    return memory.architecture.working_state(user_id, thread_id, task_id).model_dump()


@router.patch("/working/{thread_id}/{task_id}")
def patch(thread_id: str, task_id: str, body: Patch, memory: MemoryDependency):
    return memory.architecture.update_working_state(
        body.user_id, thread_id, task_id, body.patch
    )


@router.delete("/working/{thread_id}/{task_id}")
def clear(thread_id: str, task_id: str, memory: MemoryDependency, user_id: str):
    memory.architecture.clear_task(user_id, thread_id, task_id)
    return {"deleted": True}


@router.post("/assertions")
def assertion(body: AssertionRequest, memory: MemoryDependency):
    return memory.architecture.upsert_assertion(body.user_id, body.assertion)


@router.post("/documents")
def document(body: DocumentRequest, memory: MemoryDependency):
    return memory.architecture.ingest_document(body.user_id, body.document)


@router.post("/retrieve")
def retrieve(body: RetrieveRequest, memory: MemoryDependency):
    return {
        "items": memory.catalog.retrieve(
            body.user_id,
            body.thread_id,
            body.task_id,
            body.query,
            modules=body.modules,
            scope=body.scope,
        )
    }


@router.post("/procedures")
def propose(body: ProcedureRequest, memory: MemoryDependency):
    return memory.architecture.propose_procedure(
        body.user_id, body.proposal, key=body.name
    )


@router.post("/procedures/install-builtins")
def install(body: Owned, memory: MemoryDependency):
    memory.architecture.install_builtins(body.user_id)
    return {"items": memory.architecture.retrieve_procedures(body.user_id)}


@router.post("/procedures/{version_id}/{action}")
def lifecycle(
    version_id: str,
    action: Literal["validate", "activate", "disable"],
    body: Owned,
    memory: MemoryDependency,
):
    a = memory.architecture
    return (
        a.validate_procedure(body.user_id, version_id)
        if action == "validate"
        else a.activate_procedure(body.user_id, version_id, action == "activate")
    )


@router.post("/runs/{version_id}")
def run(version_id: str, body: RunRequest, memory: MemoryDependency):
    return memory.architecture.execute_procedure(
        body.user_id,
        version_id,
        body.arguments,
        run_key=body.run_key,
        thread=body.thread_id,
        task=body.task_id,
    )


@router.delete("/sources/{source_id}")
def delete_source(source_id: str, memory: MemoryDependency, user_id: str):
    if not memory.architecture.delete_source(user_id, source_id):
        raise HTTPException(404, "Source not found")
    return {"deleted": True}
