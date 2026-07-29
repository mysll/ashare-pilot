"""Validate the LLM-owned Daily Theme annotations contract."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
import time
from typing import Any

from ashare_pilot.mapping.daily_contract import (
    clean_text,
    default_predict_dir,
    ensure_doc_date,
    read_json,
)

from .contract import (
    ANNOTATIONS_SCHEMA,
    ATTENTION_DIRECTIONS,
    CATALYST_TYPES,
    EVIDENCE_SCHEMA,
    NEWS_REF_RE,
    POLICY_BONUSES,
    POLICY_COEFFICIENTS,
    is_number,
)
from .timing import (
    annotation_validation_retry_count,
    safe_record_stage,
)


def add(errors: list[str], path: str, message: str) -> None:
    errors.append(f"{path}: {message}")


def evidence_refs(theme: dict[str, Any]) -> set[str]:
    return {
        ref
        for item in theme.get("evidence", [])
        if isinstance(item, dict)
        for ref in item.get("refs", [])
        if isinstance(ref, str)
    }


def annotation_duration(
    evidence_path: Path,
    annotations_path: Path,
    validation_started_at: float,
) -> float | None:
    """Measure evidence publication through completion of validation."""

    try:
        llm_seconds = max(
            0.0,
            annotations_path.stat().st_mtime - evidence_path.stat().st_mtime,
        )
    except OSError:
        return None
    return llm_seconds + (time.perf_counter() - validation_started_at)


def validate(
    doc: dict[str, Any], evidence_doc: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    if doc.get("schema_version") != ANNOTATIONS_SCHEMA:
        add(errors, "schema_version", f"must be {ANNOTATIONS_SCHEMA}")
    if doc.get("date") != evidence_doc.get("date"):
        add(errors, "date", "must match evidence input")
    if evidence_doc.get("schema_version") != EVIDENCE_SCHEMA:
        add(errors, "evidence.schema_version", f"must be {EVIDENCE_SCHEMA}")

    evidence_themes = evidence_doc.get("themes")
    annotation_themes = doc.get("themes")
    if not isinstance(evidence_themes, list):
        add(errors, "evidence.themes", "must be list")
        return errors
    if not isinstance(annotation_themes, list):
        add(errors, "themes", "must be list")
        return errors
    expected: dict[str, dict[str, Any]] = {}
    for i, item in enumerate(evidence_themes):
        base = f"evidence.themes[{i}]"
        if not isinstance(item, dict):
            add(errors, base, "must be object")
            continue
        name = clean_text(item.get("name"))
        if not name:
            add(errors, f"{base}.name", "required")
            continue
        if name in expected:
            add(errors, f"{base}.name", f"duplicate {name}")
            continue
        expected[name] = item
    seen: set[str] = set()
    for i, item in enumerate(annotation_themes):
        base = f"themes[{i}]"
        if not isinstance(item, dict):
            add(errors, base, "must be object")
            continue
        name = clean_text(item.get("name"))
        if not name:
            add(errors, f"{base}.name", "required")
            continue
        if name in seen:
            add(errors, f"{base}.name", f"duplicate {name}")
        seen.add(name)
        if name not in expected:
            add(errors, f"{base}.name", "not present in evidence input")
        available_refs = evidence_refs(expected[name]) if name in expected else set()
        accepted = item.get("accepted_refs")
        if not isinstance(accepted, list):
            add(errors, f"{base}.accepted_refs", "must be list")
            accepted_refs: set[str] = set()
        else:
            accepted_refs = set()
            for j, ref in enumerate(accepted):
                if not isinstance(ref, str) or not NEWS_REF_RE.fullmatch(ref):
                    add(errors, f"{base}.accepted_refs[{j}]", "invalid news ref")
                elif ref not in available_refs:
                    add(errors, f"{base}.accepted_refs[{j}]", "not owned by theme")
                elif ref in accepted_refs:
                    add(errors, f"{base}.accepted_refs[{j}]", "duplicate")
                accepted_refs.add(ref)

        for key in ("confidence", "market_action", "emotion_raw", "capital"):
            value = item.get(key)
            if not is_number(value) or not 0 <= value <= 100:
                add(errors, f"{base}.{key}", "must be number in [0, 100]")
        direction = item.get("attention_direction")
        if direction not in ATTENTION_DIRECTIONS:
            add(errors, f"{base}.attention_direction", "invalid enum")
        tier = item.get("policy_tier")
        polarity = item.get("policy_polarity")
        if tier not in POLICY_BONUSES:
            add(errors, f"{base}.policy_tier", "invalid enum")
        if polarity not in POLICY_COEFFICIENTS:
            add(errors, f"{base}.policy_polarity", "invalid enum")
        policy_ref = item.get("policy_ref")
        if tier == "none":
            if policy_ref is not None:
                add(errors, f"{base}.policy_ref", "must be null when tier is none")
            if polarity != "neutral":
                add(
                    errors,
                    f"{base}.policy_polarity",
                    "must be neutral when tier is none",
                )
        elif policy_ref not in accepted_refs:
            add(errors, f"{base}.policy_ref", "must be an accepted ref")

        catalyst = item.get("catalyst")
        if catalyst is not None:
            if not isinstance(catalyst, dict):
                add(errors, f"{base}.catalyst", "must be object or null")
            else:
                if catalyst.get("type") not in CATALYST_TYPES:
                    add(errors, f"{base}.catalyst.type", "invalid enum")
                if catalyst.get("evidence_ref") not in accepted_refs:
                    add(
                        errors,
                        f"{base}.catalyst.evidence_ref",
                        "must be an accepted ref",
                    )
                if direction not in {"bullish", "neutral"}:
                    add(
                        errors,
                        f"{base}.catalyst",
                        "requires bullish or neutral attention direction",
                    )
        reason = item.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            add(errors, f"{base}.reason", "must be non-empty string")
        elif len(reason) > 240:
            add(errors, f"{base}.reason", "must be at most 240 characters")

    missing = sorted(set(expected) - seen)
    for name in missing:
        add(errors, "themes", f"missing annotation for {name}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Daily Theme annotations")
    parser.add_argument("--date", required=True)
    parser.add_argument("--annotations")
    parser.add_argument("--evidence")
    parser.add_argument(
        "--record-timing",
        action="store_true",
        help="Automatically record the theme_llm stage",
    )
    args = parser.parse_args(argv)
    validation_started_at = time.perf_counter()
    predict = default_predict_dir(args.date)
    annotations_path = (
        Path(args.annotations)
        if args.annotations
        else predict / ".theme_annotations.json"
    )
    evidence_path = (
        Path(args.evidence)
        if args.evidence
        else predict / ".theme_evidence_input.json"
    )
    try:
        annotations = read_json(annotations_path)
        evidence = read_json(evidence_path)
        if not isinstance(annotations, dict) or not isinstance(evidence, dict):
            raise ValueError("annotations and evidence roots must be objects")
        ensure_doc_date(annotations, args.date, str(annotations_path))
        ensure_doc_date(evidence, args.date, str(evidence_path))
        errors = validate(annotations, evidence)
    except (OSError, ValueError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    retries = annotation_validation_retry_count(
        predict / "step1_timing.json", evidence_path
    )
    if args.record_timing:
        annotation_themes = annotations.get("themes")
        safe_record_stage(
            predict / "step1_timing.json",
            args.date,
            "theme_llm",
            annotation_duration(
                evidence_path, annotations_path, validation_started_at
            ),
            [evidence_path],
            [annotations_path],
            {
                "themes": len(annotation_themes)
                if isinstance(annotation_themes, list)
                else 0
            },
            retries,
            "failed" if errors else "passed",
        )
    if errors:
        print(f"[ERROR] annotations failed validation ({len(errors)} errors):", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(f"OK: {annotations_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
