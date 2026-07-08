#!/usr/bin/env python3
"""Validate predict/{date}/themes.json."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from mapper_json_lib import clean_text, default_predict_dir, ensure_doc_date, parse_float, read_json


SCHEMA_VERSION = "daily_themes.v1"
STATUSES = {"tradeable", "watch", "discarded"}
DIRECTIONS = {"bullish", "mixed", "panic", "neutral", "unknown"}


def add(errors: list[str], path: str, message: str) -> None:
    errors.append(f"{path}: {message}")


def is_score(value: Any) -> bool:
    number = parse_float(value)
    return number is not None and 0 <= number <= 100


def validate(doc: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if doc.get("schema_version") != SCHEMA_VERSION:
        add(errors, "schema_version", f"must be {SCHEMA_VERSION}")
    if not isinstance(doc.get("date"), str) or not re.match(r"^\d{4}-\d{2}-\d{2}$", doc.get("date", "")):
        add(errors, "date", "must be YYYY-MM-DD")

    themes = doc.get("themes")
    if not isinstance(themes, list):
        add(errors, "themes", "must be list")
        return errors

    seen: set[str] = set()
    for i, theme in enumerate(themes):
        base = f"themes[{i}]"
        if not isinstance(theme, dict):
            add(errors, base, "must be object")
            continue
        name = clean_text(theme.get("name"))
        if not name:
            add(errors, f"{base}.name", "required")
        elif name in seen:
            add(errors, f"{base}.name", f"duplicate {name}")
        else:
            seen.add(name)

        for key in ("heat", "confidence"):
            if not is_score(theme.get(key)):
                add(errors, f"{base}.{key}", "must be number in [0, 100]")
        status = theme.get("status")
        if status not in STATUSES:
            add(errors, f"{base}.status", f"must be one of {sorted(STATUSES)}")
        direction = theme.get("direction", "unknown")
        if direction not in DIRECTIONS:
            add(errors, f"{base}.direction", f"must be one of {sorted(DIRECTIONS)}")

        for key in ("reason", "evidence"):
            value = theme.get(key)
            if value is not None and not isinstance(value, str):
                add(errors, f"{base}.{key}", "must be string or null")

    tradeable = [theme for theme in themes if isinstance(theme, dict) and theme.get("status") == "tradeable"]
    if not tradeable:
        add(errors, "themes", "must include at least one tradeable theme")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate themes.json")
    parser.add_argument("path", nargs="?", help="Path to themes.json")
    parser.add_argument("--date", help="YYYY-MM-DD; used for default path")
    args = parser.parse_args()

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    if args.path:
        path = Path(args.path)
    elif args.date:
        path = default_predict_dir(args.date) / "themes.json"
    else:
        print("[ERROR] provide path or --date", file=sys.stderr)
        return 2

    doc = read_json(path)
    if not isinstance(doc, dict):
        print("[ERROR] root must be object", file=sys.stderr)
        return 1
    if args.date:
        try:
            ensure_doc_date(doc, args.date, str(path))
        except ValueError as exc:
            print(f"[ERROR] {exc}", file=sys.stderr)
            return 1
    errors = validate(doc)
    if errors:
        print(f"[ERROR] {path} failed validation ({len(errors)} errors):", file=sys.stderr)
        for item in errors:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print(f"OK: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
