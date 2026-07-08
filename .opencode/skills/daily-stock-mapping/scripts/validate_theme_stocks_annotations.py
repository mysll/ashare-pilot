#!/usr/bin/env python3
"""Validate predict/{date}/theme_stocks.annotations.json."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from mapper_json_lib import CODE_RE, clean_text, default_predict_dir, ensure_doc_date, read_json


SCHEMA_VERSION = "daily_theme_stocks_annotations.v1"
SOURCE_FLAG_KEYS = {"candidate", "market", "news", "lhb"}


def add(errors: list[str], path: str, message: str) -> None:
    errors.append(f"{path}: {message}")


def is_bool(value: Any) -> bool:
    return isinstance(value, bool)


def validate(doc: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if doc.get("schema_version") != SCHEMA_VERSION:
        add(errors, "schema_version", f"must be {SCHEMA_VERSION}")
    if not isinstance(doc.get("date"), str) or not re.match(r"^\d{4}-\d{2}-\d{2}$", doc.get("date", "")):
        add(errors, "date", "must be YYYY-MM-DD")

    themes = doc.get("themes", [])
    if themes is not None and not isinstance(themes, list):
        add(errors, "themes", "must be list")
    elif isinstance(themes, list):
        seen_themes: set[str] = set()
        for i, theme in enumerate(themes):
            base = f"themes[{i}]"
            if not isinstance(theme, dict):
                add(errors, base, "must be object")
                continue
            name = clean_text(theme.get("name"))
            if not name:
                add(errors, f"{base}.name", "required")
                continue
            if name in seen_themes:
                add(errors, f"{base}.name", f"duplicate {name}")
            seen_themes.add(name)
            for key in ("note", "evidence"):
                value = theme.get(key)
                if value is not None and not isinstance(value, str):
                    add(errors, f"{base}.{key}", "must be string or null")

    stocks = doc.get("stocks")
    if not isinstance(stocks, list):
        add(errors, "stocks", "must be list")
        return errors
    seen: set[str] = set()
    for i, stock in enumerate(stocks):
        base = f"stocks[{i}]"
        if not isinstance(stock, dict):
            add(errors, base, "must be object")
            continue
        code = stock.get("code")
        if not isinstance(code, str) or not CODE_RE.fullmatch(code):
            add(errors, f"{base}.code", "must be a trading code string")
            continue
        if code in seen:
            add(errors, f"{base}.code", f"duplicate {code}")
        seen.add(code)

        source_flags = stock.get("source_flags")
        if source_flags is not None:
            if not isinstance(source_flags, dict):
                add(errors, f"{base}.source_flags", "must be object")
            else:
                for key, value in source_flags.items():
                    if key not in SOURCE_FLAG_KEYS:
                        add(errors, f"{base}.source_flags.{key}", "invalid source flag")
                    elif not is_bool(value):
                        add(errors, f"{base}.source_flags.{key}", "must be boolean")

        for key in ("news_ref", "market_ref", "anomaly", "source_explanation", "note"):
            value = stock.get(key)
            if value is not None and not isinstance(value, str):
                add(errors, f"{base}.{key}", "must be string or null")
        anomaly = stock.get("anomaly")
        if isinstance(anomaly, str) and len(anomaly) > 80:
            add(errors, f"{base}.anomaly", "must be <= 80 chars")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate theme_stocks.annotations.json")
    parser.add_argument("path", nargs="?", help="Path to theme_stocks.annotations.json")
    parser.add_argument("--date", help="YYYY-MM-DD; used for default path")
    args = parser.parse_args()

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    if args.path:
        path = Path(args.path)
    elif args.date:
        path = default_predict_dir(args.date) / "theme_stocks.annotations.json"
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
