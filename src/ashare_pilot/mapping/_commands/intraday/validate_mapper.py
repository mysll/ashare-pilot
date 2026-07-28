#!/usr/bin/env python3
"""Validate intraday_mapper.v3 pool ownership and annotation coverage."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ashare_pilot.mapping.intraday_contract import (
    MAPPER_SCHEMA_VERSION,
    execution_state,
    intraday_dir,
    read_json,
    reasoning_invariant_errors,
    resolved_stop_loss,
)
from .validate_annotations import OBSERVATION_EXECUTION_FIELDS, validate as validate_annotations


def _expected_reasoning(stock: dict, note: dict) -> dict:
    reasoning = {key: value for key, value in note.items() if key != "code"}
    plan = reasoning.get("t_plus_1_plan")
    if isinstance(plan, dict):
        plan = dict(plan)
        plan.update(resolved_stop_loss(stock, plan.get("stop_loss_basis")))
        reasoning["t_plus_1_plan"] = plan
    return reasoning


def validate(
    document,
    date: str,
    annotations: dict | None = None,
    base: dict | None = None,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(document, dict):
        return ["root must be object"]
    if document.get("schema_version") != MAPPER_SCHEMA_VERSION:
        errors.append(f"schema_version must be {MAPPER_SCHEMA_VERSION}")
    if document.get("date") != date:
        errors.append(f"date must be {date}")
    if "stocks" in document:
        errors.append("legacy root stocks field is forbidden")
    executable = document.get("executable_stocks")
    observation = document.get("observation_stocks")
    if not isinstance(executable, list):
        errors.append("executable_stocks must be list")
        executable = []
    if not isinstance(observation, list):
        errors.append("observation_stocks must be list")
        observation = []
    executable_codes = [
        item.get("code") for item in executable if isinstance(item, dict)
    ]
    observation_codes = [
        item.get("code") for item in observation if isinstance(item, dict)
    ]
    if len(executable_codes) != len(set(executable_codes)):
        errors.append("executable_stocks contains duplicate codes")
    if len(observation_codes) != len(set(observation_codes)):
        errors.append("observation_stocks contains duplicate codes")
    overlap = sorted(set(executable_codes) & set(observation_codes))
    if overlap:
        errors.append(f"pool code overlap: {overlap}")
    for item in executable:
        if not isinstance(item, dict):
            continue
        if item.get("execution_state") != execution_state(item):
            errors.append(f"{item.get('code')}: execution_state mismatch")
        reasoning = item.get("reasoning")
        if not isinstance(reasoning, dict):
            errors.append(f"{item.get('code')}: executable reasoning missing")
        else:
            for error in reasoning_invariant_errors(item, reasoning):
                errors.append(f"{item.get('code')}: {error}")
        if "observation_reasoning" in item:
            errors.append(
                f"{item.get('code')}: observation_reasoning forbidden on executable"
            )
    for item in observation:
        if not isinstance(item, dict):
            continue
        if item.get("execution_state") != execution_state(item):
            errors.append(f"{item.get('code')}: execution_state mismatch")
        observation_reasoning = item.get("observation_reasoning")
        if not isinstance(observation_reasoning, dict):
            errors.append(f"{item.get('code')}: observation reasoning missing")
        else:
            for field in sorted(
                OBSERVATION_EXECUTION_FIELDS & set(observation_reasoning)
            ):
                errors.append(
                    f"{item.get('code')}: observation reasoning contains {field}"
                )
        if "reasoning" in item:
            errors.append(f"{item.get('code')}: reasoning forbidden on observation")
    coverage = document.get("annotation_coverage")
    coverage = coverage if isinstance(coverage, dict) else {}
    expected = {
        "executable": {
            "expected": len(executable),
            "annotated": sum(
                isinstance(item, dict) and isinstance(item.get("reasoning"), dict)
                for item in executable
            ),
        },
        "observation": {
            "expected": len(observation),
            "annotated": sum(
                isinstance(item, dict)
                and isinstance(item.get("observation_reasoning"), dict)
                for item in observation
            ),
        },
    }
    if coverage != expected:
        errors.append("annotation_coverage does not match both pools")
    if isinstance(annotations, dict):
        base_for_annotations = base if isinstance(base, dict) else document
        errors.extend(
            f"annotations: {error}"
            for error in validate_annotations(
                annotations,
                date,
                set(executable_codes),
                set(observation_codes),
                base_for_annotations,
            )
        )
        executable_notes = {
            item.get("code"): item
            for item in annotations.get("executable_annotations", [])
            if isinstance(item, dict)
        }
        observation_notes = {
            item.get("code"): item
            for item in annotations.get("observation_annotations", [])
            if isinstance(item, dict)
        }
        if document.get("market_assessment") != annotations.get(
            "market_assessment"
        ):
            errors.append("market_assessment differs from annotations")
        if document.get("strategy") != annotations.get("strategy"):
            errors.append("strategy differs from annotations")
        for item in executable:
            if not isinstance(item, dict):
                continue
            note = executable_notes.get(item.get("code"))
            if isinstance(note, dict) and item.get("reasoning") != _expected_reasoning(
                item, note
            ):
                errors.append(
                    f"{item.get('code')}: reasoning differs from annotations"
                )
        for item in observation:
            if not isinstance(item, dict):
                continue
            note = observation_notes.get(item.get("code"))
            expected_note = (
                {key: value for key, value in note.items() if key != "code"}
                if isinstance(note, dict)
                else None
            )
            if expected_note is not None and item.get(
                "observation_reasoning"
            ) != expected_note:
                errors.append(
                    f"{item.get('code')}: observation reasoning differs from annotations"
                )
    if isinstance(base, dict):
        merged_root_fields = {
            "schema_version",
            "generated_at",
            "generation_mode",
            "market_assessment",
            "strategy",
            "executable_stocks",
            "observation_stocks",
            "annotation_coverage",
        }
        for field, value in base.items():
            if field not in merged_root_fields and document.get(field) != value:
                errors.append(f"{field}: compute-owned root field differs from base")
        for pool, reasoning_field in (
            ("executable_stocks", "reasoning"),
            ("observation_stocks", "observation_reasoning"),
        ):
            base_by_code = {
                item.get("code"): item
                for item in base.get(pool, [])
                if isinstance(item, dict)
            }
            for item in document.get(pool, []):
                if not isinstance(item, dict):
                    continue
                projected = {
                    key: value
                    for key, value in item.items()
                    if key != reasoning_field
                }
                if projected != base_by_code.get(item.get("code")):
                    errors.append(
                        f"{item.get('code')}: compute-owned stock fields differ from base"
                    )
    return errors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--input")
    parser.add_argument("--annotations")
    parser.add_argument("--base")
    args = parser.parse_args(argv)
    path = (
        Path(args.input)
        if args.input
        else intraday_dir(args.date) / "intraday_mapper.json"
    )
    root = intraday_dir(args.date)
    annotations_path = (
        Path(args.annotations)
        if args.annotations
        else root / "intraday_mapper.annotations.json"
    )
    base_path = (
        Path(args.base) if args.base else root / "intraday_mapper.base.json"
    )
    try:
        document = read_json(path)
        annotations = (
            read_json(annotations_path) if annotations_path.exists() else None
        )
        base = read_json(base_path) if base_path.exists() else None
    except (OSError, ValueError) as exc:
        print(f"[ERROR] mapper input unreadable: {exc}", file=sys.stderr)
        return 1
    errors = validate(document, args.date, annotations=annotations, base=base)
    if errors:
        print(f"[ERROR] {path} failed validation:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(
        f"OK: {path} "
        f"({len(document['executable_stocks'])} executable, "
        f"{len(document['observation_stocks'])} observation)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
