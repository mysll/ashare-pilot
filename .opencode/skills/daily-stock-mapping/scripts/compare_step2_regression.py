#!/usr/bin/env python3
"""Layered frozen-fixture comparison for Step 2 decision projections."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from mapper_json_lib import read_json


IGNORED_KEYS = {"generated_at", "generation_mode", "annotation_schema_version", "source"}


def normalized(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: normalized(item) for key, item in value.items() if key not in IGNORED_KEYS}
    if isinstance(value, list):
        return [normalized(item) for item in value]
    return value


def diff(left: Any, right: Any, path: str = "$") -> list[tuple[str, Any, Any]]:
    if isinstance(left, dict) and isinstance(right, dict):
        result = []
        for key in sorted(set(left) | set(right)):
            result.extend(diff(left.get(key), right.get(key), f"{path}.{key}"))
        return result
    if isinstance(left, list) and isinstance(right, list):
        result = []
        for index in range(max(len(left), len(right))):
            result.extend(diff(left[index] if index < len(left) else None,
                               right[index] if index < len(right) else None, f"{path}[{index}]"))
        return result
    return [] if left == right else [(path, left, right)]


def allowed_task45(path: str, before: Any, after: Any) -> bool:
    return path.endswith(".pattern.auction.state") and before == "NEUTRAL" and after == "UNKNOWN"


def allowed_by_rule(path: str, before: Any, after: Any, rule: dict[str, Any]) -> bool:
    return rule.get("path") == path and rule.get("before") == before and rule.get("after") == after


def classify_changes(
    changes: list[tuple[str, Any, Any]],
    gate: str,
    allowlist: list[dict[str, Any]] | None = None,
) -> tuple[list[tuple[str, Any, Any]], list[tuple[str, Any, Any]]]:
    allowed = []
    blocked = []
    rules = allowlist or []
    for item in changes:
        path, before, after = item
        accepted = any(allowed_by_rule(path, before, after, rule) for rule in rules)
        if gate == "task45" and allowed_task45(path, before, after):
            accepted = True
        (allowed if accepted else blocked).append(item)
    return allowed, blocked


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare frozen Step 2 projections")
    parser.add_argument("before")
    parser.add_argument("after")
    parser.add_argument("--gate", choices=("task2", "task45"), default="task2")
    parser.add_argument("--allowlist", help="Exact JSON allowlist rules for Task 4/5 diffs")
    parser.add_argument("--output")
    args = parser.parse_args()
    changes = diff(normalized(read_json(Path(args.before))), normalized(read_json(Path(args.after))))
    allowlist = read_json(Path(args.allowlist)) if args.allowlist else []
    if not isinstance(allowlist, list) or any(not isinstance(item, dict) for item in allowlist):
        raise SystemExit("[ERROR] allowlist must be a JSON list of exact {path,before,after} rules")
    allowed, blocked = classify_changes(changes, args.gate, allowlist)
    report = {"gate": args.gate, "change_count": len(changes), "allowed_count": len(allowed),
              "blocked_count": len(blocked), "allowed": allowed, "blocked": blocked}
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
