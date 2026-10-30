"""Offline dataset checks. Does not call a model or modify source packages."""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def inside(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"Path outside package: {relative}")
    return path


def check(root):
    index = read(root / "index.json")
    rows = []
    seen = set()
    for entry in index["samples"]:
        sid = entry["sample_id"]
        row = {"sample_id": sid, "review_group": entry["review_group"], "errors": []}
        try:
            if sid in seen:
                raise ValueError("Duplicate sample ID")
            seen.add(sid)
            package = inside(root, entry["package_folder"])
            suite = read(inside(root, entry["suite_file"]))
            for relative, expected in suite["public_sha256"].items():
                actual = hashlib.sha256(inside(package, relative).read_bytes()).hexdigest()
                if actual != expected:
                    row["errors"].append(f"Hash mismatch: {relative}")
            sample_path = inside(package, suite["samples"][0])
            sample = read(sample_path)
            history = read(inside(sample_path.parent, sample["history_file"]))
            probes = read(inside(sample_path.parent, sample["probes_file"]))
            branches = read(inside(sample_path.parent, sample["branches_file"]))
            gold = read(package / "private" / sid / "gold.json")
            sessions = history["sessions"]
            ids = [p["probe_id"] for p in probes]
            if len(ids) != len(set(ids)):
                row["errors"].append("Duplicate probe IDs")
            for probe in probes:
                if probe["probe_id"] not in gold["labels"]:
                    row["errors"].append(f"Missing label: {probe['probe_id']}")
                if probe["branch_id"] != "BASE" and probe["branch_id"] not in branches:
                    row["errors"].append(f"Missing branch: {probe['branch_id']}")
            row.update(
                sessions=len(sessions),
                messages=sum(len(s["messages"]) for s in sessions),
                history_characters=sum(len(m["content"]) for s in sessions for m in s["messages"]),
                probes=len(probes),
                branches=list(branches),
                protocol_approved=sample.get("review", {}).get("protocol_approved", False),
                metrics=sorted({m for p in probes for m in p["metrics"]}),
            )
        except (OSError, ValueError, KeyError, TypeError) as error:
            row["errors"].append(str(error))
        rows.append(row)
    return {
        "mode": "offline_preflight_not_quality_evaluation",
        "dataset_root": str(root.resolve()),
        "declared_samples": index["samples_count"],
        "checked_samples": len(rows),
        "sample_count_matches": len(rows) == index["samples_count"],
        "samples_with_errors": sum(bool(r["errors"]) for r in rows),
        "review_groups": dict(Counter(r["review_group"] for r in rows)),
        "protocol_approved_samples": sum(r.get("protocol_approved", False) for r in rows),
        "totals": {k: sum(r.get(k, 0) for r in rows) for k in ["sessions", "messages", "history_characters", "probes"]},
        "samples": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("evaluation/Vatsalabench"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    indexes = list(args.dataset.rglob("index.json"))
    indexes = [p for p in indexes if read(p).get("schema") == "portable-data-handoff-v1"]
    if len(indexes) != 1:
        parser.error(f"Expected one handoff index.json, found {len(indexes)}")
    report = check(indexes[0].parent)
    output = args.output or Path("evaluation/Vatsalabench/results") / datetime.now().strftime("%Y%m%d-%H%M%S-%f") / "preflight.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "samples"}, ensure_ascii=False, indent=2))
    print(f"Report: {output.resolve()}")
    return int(report["samples_with_errors"] > 0 or not report["sample_count_matches"])


if __name__ == "__main__":
    raise SystemExit(main())
