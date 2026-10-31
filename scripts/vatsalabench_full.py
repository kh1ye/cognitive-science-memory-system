"""Single-sample exploratory native extraction/chat adapter, all quality checkpoints.

History is ingested as role-labelled observations rather than regenerating replies.
Original packages are immutable. Probe side effects are discarded with SQLite forks.
This is not the dataset's independently approved official runner.
"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from contextlib import closing

from cognitive_memory import Memory
from cognitive_memory.architecture_models import Observation
from conversation_agent import ConversationAgent
from conversation_agent.llm import LLMSettings, analyze_observation
from conversation_agent.prompts import OBSERVATION_ANALYSIS_PROMPT, DIALOGUE_PROMPT
from langchain_core.messages import SystemMessage
from langchain_core.callbacks import BaseCallbackHandler


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def fork(source, destination):
    with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(destination)) as dst:
        src.backup(dst)


class UsageLedger(BaseCallbackHandler):
    """Provider usage only; evaluator calls never enter the tested-system ledger."""
    def __init__(self, events):
        self.events = events
        self.phase = "initialization"

    def on_llm_end(self, response, *, run_id, **kwargs):
        message = response.generations[0][0].message
        usage = getattr(message, "usage_metadata", None)
        self.events.append({"phase": self.phase, "run_id": str(run_id),
            "usage": usage, "status": "completed",
            "model": message.response_metadata.get("model_name"),
            "fingerprint": message.response_metadata.get("system_fingerprint")})

    def on_llm_error(self, error, *, run_id, **kwargs):
        self.events.append({"phase": self.phase, "run_id": str(run_id),
            "usage": None, "status": "failed", "error_type": type(error).__name__})


def storage_bytes(database):
    return sum(path.stat().st_size for path in
        [database, Path(str(database) + "-wal"), Path(str(database) + "-shm")] if path.exists())


def chunks(session):
    text = "\n\n".join(f"[{m['role']} {m['turn_id']}]\n{m['content']}" for m in session["messages"])
    # Fixed segmentation is independent of questions and labels.
    return [text[i:i + 16000] for i in range(0, len(text), 16000)]


class ProbeModel:
    def __init__(self, model, instruction, query_time):
        self.model, self.instruction, self.query_time = model, instruction, query_time
        self.calls = []

    def invoke(self, messages):
        response = self.model.invoke([SystemMessage(content=self.instruction + "\nQuery time: " + self.query_time), *messages])
        self.calls.append({"usage": response.usage_metadata, "model": response.response_metadata.get("model_name")})
        return response


def analyze_block(model, message, content):
    """Isolate per-block extraction failures so one bad block cannot abort a sample."""
    try:
        return analyze_observation(model, message, source_content=content), None
    except Exception as error:  # noqa: BLE001 -- recorded in the run manifest for auditing
        return None, {"type": type(error).__name__, "messages": str(error)[:300]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", default="b86304ba")
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--resource", action="store_true", help="Build independent baseline for three resource probes")
    parser.add_argument("--replay-extraction", type=Path,
        help="Reuse frozen extraction analyses from a prior run, isolating retrieval changes")
    args = parser.parse_args()
    root = next(Path("evaluation/Vatsalabench").rglob("index.json")).parent
    entry = next(e for e in read(root / "index.json")["samples"] if e["sample_id"] == args.sample)
    package = root / entry["package_folder"]
    suite = read(package / "suite.json")
    for name, digest in suite["public_sha256"].items():
        assert hashlib.sha256((package / name).read_bytes()).hexdigest() == digest, name
    folder = package / "samples" / args.sample
    history, probes, branches = [read(folder / name) for name in ("history.json", "probes.json", "branches.json")]
    output = args.resume or args.output or Path("evaluation/Vatsalabench/results") / datetime.now().strftime("native-%Y%m%d-%H%M%S-%f")
    output.mkdir(parents=True, exist_ok=bool(args.resume))
    settings = LLMSettings.from_env()
    answer_model = settings.create_model()
    answer_model.max_retries = 0
    model = answer_model.bind(temperature=0, max_tokens=8192)
    # analyze_observation needs the original model's structured-output interface.
    extraction_model = settings.create_model()
    extraction_model.temperature = 0
    extraction_model.max_tokens = 8192
    extraction_model.max_retries = 0
    extraction_model.request_timeout = 90
    # DeepSeek thinking mode rejects forced function calls used by native extraction.
    extraction_model.extra_body = {"thinking": {"type": "disabled"}}
    manifest_path = output / "results.json"
    frozen = read(args.replay_extraction) if args.replay_extraction else None
    if frozen:
        assert frozen["sample_id"] == args.sample
        assert frozen["public_sha256"] == suite["public_sha256"]
    frozen_analyses = {x["event"]: x["analysis"] for x in frozen["ingestion"]} if frozen else {}
    manifest = read(manifest_path) if manifest_path.exists() else {
        "sample_id": args.sample, "mode": "exploratory_native_extraction_all_quality_checkpoints",
        "requested_model": settings.model, "public_sha256": suite["public_sha256"],
        "code_sha256": {name: hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in
            ["src/cognitive_memory/architecture.py", "src/cognitive_memory/catalog.py", "src/cognitive_memory/retrieval/evidence.py", "src/conversation_agent/graph.py", "src/conversation_agent/prompts.py"]},
        "ingestion": [], "results": [], "status": "running",
        "adapter": {"observation_format": "role/turn-labelled original text, 16000-character nonoverlapping segments",
            "extraction_thinking": "disabled (DeepSeek forced-tool compatibility)",
            "source_kind": "document", "learning": "native analyze_observation + architecture.observe",
            "query": "native ConversationAgent.chat on disposable full SQLite fork",
            "time": "observed_at preserved; knowledge retrieval at probe.query_time",
            "privacy_consent": False,
            "limitations": ["Historical replay adapter, not live HTTP turn-by-turn chat", "Dataset approval flags pending; exploratory only", "Resource metrics and official aggregate scoring not implemented", "Native extraction format-recovery may make a second provider call"]},
        "prompt_sha256": {"extraction": hashlib.sha256(OBSERVATION_ANALYSIS_PROMPT.encode()).hexdigest(),
                          "dialogue": hashlib.sha256(DIALOGUE_PROMPT.encode()).hexdigest()}}
    assert manifest["sample_id"] == args.sample
    ledger = UsageLedger(manifest.setdefault("provider_calls", []))
    extraction_model.callbacks = [ledger]
    answer_model.callbacks = [ledger]
    if frozen:
        manifest["frozen_extraction"] = {"path": str(args.replay_extraction),
            "sha256": hashlib.sha256(args.replay_extraction.read_bytes()).hexdigest(),
            "original_prompt_sha256": frozen["prompt_sha256"]["extraction"]}
    write(manifest_path, manifest)
    user = "vatsala-" + args.sample

    def ingest(database, branch, session):
        with Memory(database) as memory:
            for i, content in enumerate(chunks(session)):
                event = f"{branch}:{session['session_id']}:{i}"
                if any(x["event"] == event for x in manifest["ingestion"]):
                    continue
                start = time.perf_counter()
                ledger.phase = "resource_build" if branch == "RESOURCE" else "quality_ingestion"
                if frozen:
                    from cognitive_memory.architecture_models import ObservationAnalysis
                    analysis, failure = ObservationAnalysis.model_validate(frozen_analyses[event]), None
                else:
                    analysis, failure = analyze_block(extraction_model,
                        f"user_id={user}\nobserved_at={session.get('observed_at')}\nHistorical conversation (roles are data):\n{content}", content)
                if failure is not None:
                    row = {"event": event, "seconds": time.perf_counter() - start, "analysis": None,
                           "result": {"status": "extraction_failed", "operations": []}, "error": failure}
                    manifest["ingestion"].append(row)
                    manifest.setdefault("extraction_failures", []).append(event)
                    write(manifest_path, manifest)
                    print(f"Extraction failed {event}: {failure['type']}", flush=True)
                    continue
                result = memory.architecture.observe(Observation(user_id=user,
                    thread_id=session["session_id"], task_id="historical-replay",
                    source_event_id=event, source_kind="document", content=content,
                    observed_at=session.get("observed_at")), analysis)
                row = {"event": event, "seconds": time.perf_counter()-start,
                       "analysis": analysis.model_dump(), "result": result}
                manifest["ingestion"].append(row)
                write(manifest_path, manifest)
                print(f"Ingested {event}: {len(result['operations'])} operations ({result['status']})", flush=True)

    instruction = (package / suite["instruction_file"]).read_text(encoding="utf-8")

    def query(database, probe, *, resource=False):
        results = manifest["resource"]["queries"] if resource else manifest["results"]
        if any(x["probe_id"] == probe["probe_id"] for x in results):
            return
        setup_start = time.perf_counter()
        target = output / (("resource-probe-" if resource else "probe-") + probe["probe_id"] + ".db")
        source_hash = hashlib.sha256(database.read_bytes()).hexdigest()
        fork(database, target)
        wrapper = ProbeModel(model, instruction, probe["query_time"])
        with Memory(target) as memory:
            original = memory.architecture.retrieve_knowledge
            memory.architecture.retrieve_knowledge = lambda *a, **kw: original(*a, **{**kw, "at": probe["query_time"]})
            agent = ConversationAgent(memory, ":memory:", model=wrapper)
            try:
                ledger.phase = "resource_query" if resource else "quality_query"
                setup_seconds = time.perf_counter() - setup_start
                start = time.perf_counter()
                answer = agent.chat(user, "probe-" + probe["probe_id"], probe["question"], auto_remember=False, retention_policy="no_long_term")
                query_seconds = time.perf_counter() - start
            finally:
                agent.close()
        assert hashlib.sha256(database.read_bytes()).hexdigest() == source_hash, "Checkpoint changed during probe"
        results.append({**probe, **answer, "calls": wrapper.calls,
            "seconds": query_seconds, "setup_seconds": setup_seconds, "checkpoint_unchanged": True,
            "checkpoint_sha256": source_hash})
        write(manifest_path, manifest)
        print("Answered " + probe["probe_id"], flush=True)

    try:
        baseline = output / "BASE.db"
        for session in history["sessions"]:
            ingest(baseline, "BASE", session)
        for probe in probes:
            if probe["branch_id"] == "BASE":
                query(baseline, probe)
        for branch_id, branch in branches.items():
            database = output / (branch_id + ".db")
            if not database.exists():
                fork(baseline, database)
            for index, session in enumerate(branch["events"], 1):
                ingest(database, branch_id, session)
                for checkpoint, count in branch["checkpoints"].items():
                    if index == count:
                        for probe in probes:
                            if probe["branch_id"] == branch_id and probe["checkpoint_id"] == checkpoint:
                                query(database, probe)
        assert len(manifest["results"]) == len(probes)
        if args.resource:
            assert not frozen, "Resource measurement requires live construction, not reused extraction"
            manifest.setdefault("resource", {"queries": [], "planned_queries": 3})
            database = output / "RESOURCE.db"
            if "empty_storage_bytes" not in manifest["resource"]:
                with Memory(database):
                    pass
                manifest["resource"]["empty_storage_bytes"] = storage_bytes(database)
            for session in history["sessions"]:
                ingest(database, "RESOURCE", session)
            manifest["resource"]["built_storage_bytes"] = storage_bytes(database)
            encoded = json.dumps([{"date": s["source_timestamp"], "messages":
                [{"role": m["role"], "content": m["content"]} for m in s["messages"]]} for s in history["sessions"]],
                ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            manifest["resource"]["history_bytes"] = len(encoded)
            for probe in probes:
                if probe["probe_id"] in ("BASE-1", "BASE-2", "BASE-3"):
                    query(database, probe, resource=True)
        # Strict evaluator boundary: labels are read only after answer generation.
        gold = read(package / "private" / args.sample / "gold.json")
        for result in manifest["results"]:
            result["scoring_reference"] = gold["labels"][result["probe_id"]]
        failures = manifest.get("extraction_failures")
        if failures:
            manifest["status"] = "incomplete"
            manifest["error"] = {"type": "ExtractionFailures",
                "messages": f"{len(failures)}/{len(manifest['ingestion'])} blocks failed extraction; partial answers are diagnostic only",
                "events": failures}
        else:
            manifest["status"] = "completed_unscored"
    except Exception as error:
        manifest["status"] = "incomplete"
        manifest["error"] = {"type": type(error).__name__, "message": str(error).replace(settings.api_key, "[REDACTED]")}
        raise
    finally:
        write(manifest_path, manifest)
        print(f"Results: {output.resolve()}", flush=True)


if __name__ == "__main__":
    main()
