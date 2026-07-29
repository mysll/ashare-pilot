"""Artifact-linked Step 1 timing diagnostics."""

from __future__ import annotations

from pathlib import Path
import sys

from ashare_pilot.mapping._commands.daily.timing import (
    artifact,
    same_artifact,
)
from ashare_pilot.mapping.daily_contract import (
    read_json,
    utc_now_iso,
    write_json,
)


TOTAL_STAGES = ("news_fetch", "theme_prepare", "theme_llm", "theme_finalize")


def complete_same_run(stages: dict) -> bool:
    if not all(name in stages for name in TOTAL_STAGES):
        return False
    return all(
        any(
            same_artifact(left, right)
            for left in stages[upstream].get("outputs", [])
            for right in stages[downstream].get("inputs", [])
        )
        for upstream, downstream in zip(TOTAL_STAGES, TOTAL_STAGES[1:])
    )


def update_report(
    path: Path,
    date: str,
    stage: str,
    duration: float | None,
    inputs: list[Path],
    outputs: list[Path],
    counts: dict[str, int],
    validation_retries: int | None,
    validation_status: str | None = None,
) -> None:
    doc = (
        read_json(path)
        if path.exists()
        else {
            "schema_version": "daily_step1_timing.v1",
            "date": date,
            "stages": {},
        }
    )
    if not isinstance(doc, dict) or doc.get("date") != date:
        doc = {
            "schema_version": "daily_step1_timing.v1",
            "date": date,
            "stages": {},
        }
    stages = doc.setdefault("stages", {})
    index = TOTAL_STAGES.index(stage)
    for downstream in TOTAL_STAGES[index + 1 :]:
        stages.pop(downstream, None)
    stages[stage] = {
        "recorded_at": utc_now_iso(),
        "duration_seconds": round(duration, 3) if duration is not None else None,
        "inputs": [item for item in (artifact(path) for path in inputs) if item],
        "outputs": [item for item in (artifact(path) for path in outputs) if item],
        "counts": counts,
        "validation_retry_count": validation_retries or 0,
        **(
            {"validation_status": validation_status}
            if validation_status is not None
            else {}
        ),
    }
    complete = complete_same_run(stages)
    durations = (
        [stages[name].get("duration_seconds") for name in TOTAL_STAGES]
        if complete
        else []
    )
    doc["complete_same_run"] = complete
    doc["total_recorded_seconds"] = (
        round(sum(durations), 3)
        if complete and all(isinstance(value, (int, float)) for value in durations)
        else None
    )
    doc["updated_at"] = utc_now_iso()
    write_json(path, doc)


def safe_record_stage(
    path: Path,
    date: str,
    stage: str,
    duration: float | None,
    inputs: list[Path],
    outputs: list[Path],
    counts: dict[str, int],
    validation_retries: int | None = None,
    validation_status: str | None = None,
) -> None:
    """Write report-only timing data without affecting a business command."""

    try:
        update_report(
            path,
            date,
            stage,
            duration,
            inputs,
            outputs,
            counts,
            validation_retries,
            validation_status,
        )
    except Exception as exc:
        print(
            f"[WARN] could not write Step 1 timing diagnostics: {exc}",
            file=sys.stderr,
        )


def annotation_validation_retry_count(
    path: Path, evidence_path: Path
) -> int:
    """Infer whether the current annotations validate follows one failed attempt."""

    try:
        doc = read_json(path)
        stage = doc.get("stages", {}).get("theme_llm", {})
        current = artifact(evidence_path)
        if (
            not isinstance(stage, dict)
            or stage.get("validation_status") != "failed"
            or current is None
            or not any(
                same_artifact(item, current)
                for item in stage.get("inputs", [])
                if isinstance(item, dict)
            )
        ):
            return 0
        return min(int(stage.get("validation_retry_count", 0)) + 1, 1)
    except (OSError, TypeError, ValueError):
        return 0


def recorded_annotation_retry_count(path: Path, evidence_path: Path) -> int:
    """Read the retry count recorded by the current annotations validation."""

    try:
        doc = read_json(path)
        stage = doc.get("stages", {}).get("theme_llm", {})
        current = artifact(evidence_path)
        if (
            not isinstance(stage, dict)
            or current is None
            or not any(
                same_artifact(item, current)
                for item in stage.get("inputs", [])
                if isinstance(item, dict)
            )
        ):
            return 0
        return min(max(int(stage.get("validation_retry_count", 0)), 0), 1)
    except (OSError, TypeError, ValueError):
        return 0
