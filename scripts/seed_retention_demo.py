"""Create explicitly synthetic, historically timed forgetting examples in an isolated space.

No direct score/count edits: confirmations pass through Memory.add_memory. Re-running
does not rewrite existing fixture memories, move their clock, or restore archives.
"""
import argparse
from contextlib import contextmanager
from datetime import timedelta
import json
from pathlib import Path
from unittest.mock import patch

from cognitive_memory import Memory
from cognitive_memory.models import utc_now

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "evaluation/forgetting-demo/cases.json").read_text(encoding="utf-8"))
VERSION = FIXTURE["version"]
CASES = FIXTURE["cases"]
DEMO_USER = "forgetting-demo"


@contextmanager
def simulated_clock(stamp):
    with (
        patch("cognitive_memory.models.utc_now", return_value=stamp),
        patch("cognitive_memory.retention.utc_now", return_value=stamp),
    ):
        yield


def seed_examples(memory, user=DEMO_USER, reference_time=None):
    if user != DEMO_USER and not user.startswith(DEMO_USER + "-"):
        raise ValueError("历史测试样例只能写入 forgetting-demo 或其专用测试空间。")
    now = reference_time or utc_now()
    created = []
    with memory.storage.transaction():
        existing = {
            row["metadata"].get("fixture_case_id"): row
            for row in memory.list_memories(user, include_archived=True, limit=1000)
            if row["metadata"].get("fixture_version") == VERSION
        }
        for case in CASES:
            if case["id"] in existing:
                continue
            count = case.get("evidence_count", 1)
            latest_age = case["age_days"]
            first_age = case.get("created_age_days", latest_age + (count - 1) * 14)
            for index in range(count):
                age = first_age if count == 1 else first_age - (first_age - latest_age) * index / (count - 1)
                stamp = now - timedelta(days=age)
                content = "【遗忘测试】" + case["content"]
                values = {
                    "user_id": user, "content": content,
                    "memory_type": case.get("memory_type", "semantic"),
                    "importance": case.get("importance", .6),
                    "confidence": case.get("confidence", .8),
                    "source": "retention_demo_fixture",
                    "tags": ["retention_demo", *case.get("tags", [])],
                    "metadata": {
                        "fixture_version": VERSION, "fixture_case_id": case["id"],
                        "fixture_label": case["label"], "synthetic": True,
                        "time_simulated": True, "seed_reference_time": now.isoformat(),
                        "thread_id": "retention-demo-fixtures",
                        "message_id": f"{VERSION}:{case['id']}:{index}",
                    },
                }
                if case.get("confirmation_mode") == "same_value":
                    values.update(memory_key="retention_demo_" + case["id"], memory_value=case["content"])
                    if index:
                        values["content"] = content + f"（第 {index + 1} 份确认）"
                with simulated_clock(stamp):
                    result = memory.add_memory(values)
                expected = "REINFORCED" if index else "KEEP_SESSION_ONLY" if "noise" in case.get("tags", []) else "WRITE_CURRENT"
                if result["decision"] != expected:
                    raise ValueError(f"Fixture {case['id']}: {result['decision']} != {expected}")
            created.append(case["id"])
    return {"user_id": user, "fixture_version": VERSION, "created_cases": created,
            "existing_cases": len(existing), "reference_time": now.isoformat()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=ROOT / "memory_product/data/memory_demo.db")
    parser.add_argument("--user", default=DEMO_USER)
    args = parser.parse_args()
    with Memory(args.db) as memory:
        result = seed_examples(memory, args.user)
        result["summary"] = memory.retention.overview(args.user, 1000)["summary"]
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
