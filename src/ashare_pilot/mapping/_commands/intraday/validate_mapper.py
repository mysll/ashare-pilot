#!/usr/bin/env python3
"""Validate intraday_mapper.v2 pool ownership and annotation coverage."""

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
)


def validate(document, date: str) -> list[str]:
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
        if not isinstance(item.get("observation_reasoning"), dict):
            errors.append(f"{item.get('code')}: observation reasoning missing")
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
    return errors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--input")
    args = parser.parse_args(argv)
    path = (
        Path(args.input)
        if args.input
        else intraday_dir(args.date) / "intraday_mapper.json"
    )
    try:
        document = read_json(path)
    except (OSError, ValueError) as exc:
        print(f"[ERROR] {path}: {exc}", file=sys.stderr)
        return 1
    errors = validate(document, args.date)
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
