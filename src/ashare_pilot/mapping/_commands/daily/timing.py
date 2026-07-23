#!/usr/bin/env python3
"""Best-effort report-only Step 2 timing diagnostics."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ashare_pilot.mapping.daily_contract import default_predict_dir, read_json, utc_now_iso, write_json

TOTAL_STAGES = {"theme_llm", "prepare", "mapper_annotation_llm", "finalize"}
DOWNSTREAM_STAGES = {
    "theme_llm": {"prepare", "indicators", "mapper_annotation_llm", "finalize"},
    "prepare": {"mapper_annotation_llm", "finalize"},
    "mapper_annotation_llm": {"finalize"},
}

def artifact(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    return {"path": str(path), "bytes": path.stat().st_size, "modified_at": path.stat().st_mtime}


def same_artifact(left: dict[str, Any], right: dict[str, Any]) -> bool:
    try:
        same_path = Path(str(left.get("path"))).resolve() == Path(str(right.get("path"))).resolve()
        same_mtime = float(left.get("modified_at")) == float(right.get("modified_at"))
        same_size = int(left.get("bytes")) == int(right.get("bytes"))
        return same_path and same_mtime and same_size
    except (TypeError, ValueError):
        return False


def stages_linked(upstream: dict[str, Any], downstream: dict[str, Any]) -> bool:
    outputs = upstream.get("outputs", []) if isinstance(upstream, dict) else []
    inputs = downstream.get("inputs", []) if isinstance(downstream, dict) else []
    return any(
        same_artifact(left, right)
        for left in outputs if isinstance(left, dict)
        for right in inputs if isinstance(right, dict)
    )


def complete_same_run(stages: dict[str, Any]) -> bool:
    if not TOTAL_STAGES.issubset(stages):
        return False
    return (
        stages_linked(stages["theme_llm"], stages["prepare"])
        and stages_linked(stages["prepare"], stages["mapper_annotation_llm"])
        and stages_linked(stages["mapper_annotation_llm"], stages["finalize"])
    )


def update_report(path: Path, date: str, stage: str, duration: float | None = None,
                  inputs: list[Path] | None = None, outputs: list[Path] | None = None,
                  counts: dict[str, int] | None = None, failures: int | None = None) -> None:
    try:
        doc = read_json(path) if path.exists() else {"schema_version": "daily_step2_timing.v1", "date": date, "stages": {}}
        if not isinstance(doc, dict):
            doc = {"schema_version": "daily_step2_timing.v1", "date": date, "stages": {}}
        stages = doc.setdefault("stages", {})
        for downstream in DOWNSTREAM_STAGES.get(stage, set()):
            stages.pop(downstream, None)
        stages[stage] = {
            "recorded_at": utc_now_iso(),
            "duration_seconds": round(duration, 3) if duration is not None else None,
            "inputs": [item for item in (artifact(p) for p in inputs or []) if item],
            "outputs": [item for item in (artifact(p) for p in outputs or []) if item],
            "counts": counts or {},
            **({"failures": failures} if failures is not None else {}),
        }
        complete = complete_same_run(stages)
        durations = [stages[name].get("duration_seconds") for name in TOTAL_STAGES] if complete else []
        doc["complete_same_run"] = complete
        doc["total_recorded_seconds"] = (
            round(sum(value for value in durations if isinstance(value, (int, float))), 3)
            if complete and all(isinstance(value, (int, float)) for value in durations)
            else None
        )
        doc["updated_at"] = utc_now_iso()
        write_json(path, doc)
    except Exception as exc:  # diagnostics must never invalidate trading contracts
        print(f"[WARN] could not write Step 2 timing diagnostics: {exc}", file=sys.stderr)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Update report-only step2_timing.json")
    parser.add_argument("--date", required=True)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--duration", type=float)
    parser.add_argument("--input", action="append", default=[])
    parser.add_argument("--output", action="append", default=[])
    parser.add_argument("--count", action="append", default=[], metavar="NAME=INT")
    parser.add_argument("--failures", type=int)
    args = parser.parse_args(argv)
    counts = {}
    for item in args.count:
        key, value = item.split("=", 1)
        counts[key] = int(value)
    update_report(default_predict_dir(args.date) / "step2_timing.json", args.date, args.stage, args.duration,
                  [Path(p) for p in args.input], [Path(p) for p in args.output], counts, args.failures)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
