#!/usr/bin/env python3
"""Best-effort, content-linked Step 3 timing diagnostics."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ashare_pilot.market_data.runtime import workspace_path

STAGES = ("prepare", "strategy_llm", "finalize")
DOWNSTREAM = {"prepare": {"strategy_llm", "finalize"}, "strategy_llm": {"finalize"}}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    stat = path.stat()
    return {
        "path": str(path), "bytes": stat.st_size, "modified_at": stat.st_mtime,
        "sha256": file_sha256(path),
    }


def same_artifact(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return bool(left.get("sha256")) and left.get("sha256") == right.get("sha256")


def linked(upstream: dict[str, Any], downstream: dict[str, Any]) -> bool:
    return any(
        same_artifact(out, inp)
        for out in upstream.get("outputs", []) if isinstance(out, dict)
        for inp in downstream.get("inputs", []) if isinstance(inp, dict)
    )


def complete_same_run(stages: dict[str, Any]) -> bool:
    return (
        all(name in stages for name in STAGES)
        and bool(stages["finalize"].get("outputs"))
        and linked(stages["prepare"], stages["strategy_llm"])
        and linked(stages["strategy_llm"], stages["finalize"])
    )


def update_report(path: Path, date: str, stage: str, duration: float | None = None,
                  inputs: list[Path] | None = None, outputs: list[Path] | None = None,
                  counts: dict[str, int] | None = None, validation_retries: int | None = None,
                  index_fetch_duration: float | None = None, index_fetch_failed: bool | None = None,
                  timing_method: str | None = None,
                  validation_status: str | None = None,
                  validation_errors: list[str] | None = None) -> None:
    try:
        if stage not in STAGES:
            raise ValueError(f"unsupported stage: {stage}")
        if path.exists():
            doc = json.loads(path.read_text(encoding="utf-8"))
        else:
            doc = {"schema_version": "daily_step3_timing.v1", "date": date, "stages": {}}
        if not isinstance(doc, dict) or doc.get("schema_version") != "daily_step3_timing.v1" or doc.get("date") != date:
            doc = {"schema_version": "daily_step3_timing.v1", "date": date, "stages": {}}
        stages = doc.setdefault("stages", {})
        if stage == "prepare":
            doc["validation_attempts"] = []
        for name in DOWNSTREAM.get(stage, set()):
            stages.pop(name, None)
        entry: dict[str, Any] = {
            "recorded_at": utc_now(),
            "duration_seconds": round(duration, 3) if duration is not None else None,
            "inputs": [item for item in (artifact(p) for p in inputs or []) if item],
            "outputs": [item for item in (artifact(p) for p in outputs or []) if item],
            "counts": counts or {},
        }
        if validation_retries is not None:
            entry["validation_retry_count"] = validation_retries
        if timing_method is not None:
            entry["timing_method"] = timing_method
        if index_fetch_duration is not None or index_fetch_failed is not None:
            entry["index_fetch"] = {
                "duration_seconds": round(index_fetch_duration or 0.0, 3),
                "failed": bool(index_fetch_failed),
            }
        stages[stage] = entry
        if validation_status is not None:
            attempts = doc.setdefault("validation_attempts", [])
            attempts.append({
                "recorded_at": utc_now(),
                "stage": stage,
                "status": validation_status,
                "retry_count": validation_retries or 0,
                "errors": list(validation_errors or []),
                "input_sha256": entry["inputs"][0].get("sha256") if entry["inputs"] else None,
            })
        complete = complete_same_run(stages)
        doc["complete_same_run"] = complete
        doc["gate_d_eligible"] = bool(
            complete and stages.get("strategy_llm", {}).get("timing_method") == "measured"
        )
        durations = [stages[name].get("duration_seconds") for name in STAGES] if complete else []
        doc["total_recorded_seconds"] = round(sum(durations), 3) if complete and all(isinstance(v, (int, float)) for v in durations) else None
        doc["updated_at"] = utc_now()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)
    except Exception as exc:
        print(f"[WARN] could not write Step 3 timing diagnostics: {exc}", file=sys.stderr)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Update report-only step3_timing.json")
    parser.add_argument("--date", required=True)
    parser.add_argument("--stage", required=True, choices=STAGES)
    parser.add_argument("--duration", type=float)
    parser.add_argument("--input", action="append", default=[])
    parser.add_argument("--output", action="append", default=[])
    parser.add_argument("--count", action="append", default=[], metavar="NAME=INT")
    parser.add_argument("--validation-retries", type=int)
    parser.add_argument("--timing-method", choices=("measured", "mtime_estimate"))
    args = parser.parse_args(argv)
    counts = {key: int(value) for key, value in (item.split("=", 1) for item in args.count)}
    update_report(workspace_path("predict", args.date, "step3_timing.json"), args.date, args.stage, args.duration,
                  [Path(p) for p in args.input], [Path(p) for p in args.output], counts, args.validation_retries,
                  timing_method=args.timing_method)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
