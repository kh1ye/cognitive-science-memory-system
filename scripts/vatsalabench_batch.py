"""Deterministic small expansion, serial execution, no answer-based selection."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from conversation_agent.llm import LLMSettings
from scripts.vatsalabench_full import read, write


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = next(Path("evaluation/Vatsalabench").rglob("index.json")).parent
    excluded = {"b86304ba", "1faac195"}
    candidates = [s for s in read(root / "index.json")["samples"] if s["review_group"] == "reviewed_umrr" and s["sample_id"] not in excluded]
    seed = "vatsalabench-expansion-20261030-v1"
    selected = sorted(candidates, key=lambda s: hashlib.sha256((seed + s["sample_id"]).encode()).hexdigest())[:args.count]
    out = args.output or Path("evaluation/Vatsalabench/results") / datetime.now().strftime("expansion-%Y%m%d-%H%M%S-%f")
    out.mkdir(parents=True, exist_ok=False)
    manifest = {"selection_seed": seed, "population": "reviewed_umrr only", "excluded_seen_samples": sorted(excluded),
                "selected": selected, "runs": [], "concurrency": 1, "automatic_retries": 0,
                "quality_queries_planned": 12 * len(selected), "resource_queries_planned": 3 * len(selected)}
    write(out / "batch.json", manifest)
    settings = LLMSettings.from_env()
    # Connectivity check before any dataset upload, same environment key as child runs.
    settings.create_model().bind(max_tokens=16).invoke("Reply only OK")
    for entry in selected:
        sid = entry["sample_id"]
        print("Starting " + sid, flush=True)
        logfile = out / (sid + ".log")
        with logfile.open("w", encoding="utf-8") as log:
            result = subprocess.run([sys.executable, "scripts/vatsalabench_full.py", "--sample", sid,
                "--output", str(out / sid), "--resource"], stdout=log, stderr=subprocess.STDOUT)
        manifest["runs"].append({"sample_id": sid, "exit_code": result.returncode,
            "results": str(out / sid / "results.json"), "log": str(logfile)})
        write(out / "batch.json", manifest)
        print(f"Finished {sid}: exit={result.returncode}", flush=True)
    print("Batch: " + str(out.resolve()), flush=True)


if __name__ == "__main__":
    main()
