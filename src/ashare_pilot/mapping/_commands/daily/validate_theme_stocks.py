#!/usr/bin/env python3
"""Validate predict/{date}/theme_stocks.json."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from ashare_pilot.mapping.daily_contract import (
    CODE_RE,
    clean_text,
    default_predict_dir,
    ensure_doc_date,
    load_pool,
    load_trading_scope,
    numbers_match,
    parse_float,
    raw_value,
    read_json,
    scope_decision,
    technical_value,
    theme_stock_filter,
    theme_projection_errors,
)


SCHEMA_VERSION = "daily_theme_stocks.v2"
FILTER_STATUSES = {"candidate", "observation", "removed"}
REMOVED_SOURCES = {"board-policy", "hard-filter", "soft-filter", "indicators-fetch-failed", "manual", "removed"}


def add(errors: list[str], path: str, message: str) -> None:
    errors.append(f"{path}: {message}")


def is_num(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def check_code(errors: list[str], code: Any, path: str) -> str | None:
    if not isinstance(code, str) or not CODE_RE.fullmatch(code):
        add(errors, path, "must be a trading code string")
        return None
    return code


def check_scope(errors: list[str], code: str, path: str, scope: dict[str, Any], allowed_expected: bool) -> None:
    decision = scope_decision(code, scope)
    if allowed_expected and not decision["allowed"]:
        add(errors, path, f"must not be in stocks[]; excluded by {decision['matched_rule']}: {decision['reason']}")
    if not allowed_expected and decision["allowed"]:
        add(errors, path, f"must not be board_excluded; allowed by {decision['matched_rule']}")


def check_removed_item(errors: list[str], item: Any, path: str, scope: dict[str, Any], pool: dict[str, dict[str, Any]] | None) -> str | None:
    if not isinstance(item, dict):
        add(errors, path, "must be object")
        return None
    code = check_code(errors, item.get("code"), f"{path}.code")
    if not code:
        return None
    reason = clean_text(item.get("reason"))
    source = clean_text(item.get("source"))
    if not reason:
        add(errors, f"{path}.reason", "required")
    if not source:
        add(errors, f"{path}.source", "required")
    elif source not in REMOVED_SOURCES:
        add(errors, f"{path}.source", f"invalid source {source!r}")
    if source == "board-policy":
        check_scope(errors, code, f"{path}.code", scope, allowed_expected=False)
    elif scope_decision(code, scope)["allowed"] is False:
        add(errors, f"{path}.code", "scope-excluded code belongs in board_excluded[]")
    if pool is not None and source == "hard-filter":
        entry = pool.get(code)
        amount = parse_float(raw_value(entry, "amount"))
        atr_pct = parse_float(raw_value(entry, "atr_pct"))
        fetch_failed = bool(entry.get("fetch_failed")) if entry else False
        if not fetch_failed and not ((amount is not None and amount < 30000) or (atr_pct is not None and atr_pct > 8)):
            add(errors, path, "hard-filter item is not supported by pool_indicators amount/atr_pct")
    return code


def check_doc(doc: dict[str, Any], scope: dict[str, Any], pool: dict[str, dict[str, Any]] | None) -> list[str]:
    errors: list[str] = []
    if doc.get("schema_version") != SCHEMA_VERSION:
        add(errors, "schema_version", f"must be {SCHEMA_VERSION}")
    if not isinstance(doc.get("date"), str) or not re.match(r"^\d{4}-\d{2}-\d{2}$", doc.get("date", "")):
        add(errors, "date", "must be YYYY-MM-DD")

    themes = doc.get("themes")
    if not isinstance(themes, list):
        add(errors, "themes", "must be list")
    else:
        for i, theme in enumerate(themes):
            errors.extend(theme_projection_errors(theme, f"themes[{i}]"))

    board_codes: set[str] = set()
    for i, item in enumerate(doc.get("board_excluded", [])):
        if not isinstance(item, dict):
            add(errors, f"board_excluded[{i}]", "must be object")
            continue
        code = check_code(errors, item.get("code"), f"board_excluded[{i}].code")
        if not code:
            continue
        if code in board_codes:
            add(errors, f"board_excluded[{i}].code", f"duplicate {code}")
        board_codes.add(code)
        if not clean_text(item.get("reason")):
            add(errors, f"board_excluded[{i}].reason", "required")
        check_scope(errors, code, f"board_excluded[{i}].code", scope, allowed_expected=False)

    removed_codes: set[str] = set()
    for i, item in enumerate(doc.get("removed_stocks", [])):
        code = check_removed_item(errors, item, f"removed_stocks[{i}]", scope, pool)
        if not code:
            continue
        if code in removed_codes:
            add(errors, f"removed_stocks[{i}].code", f"duplicate {code}")
        if code in board_codes:
            add(errors, f"removed_stocks[{i}].code", "duplicates board_excluded[]")
        removed_codes.add(code)

    stocks = doc.get("stocks")
    if not isinstance(stocks, list):
        add(errors, "stocks", "must be list")
        return errors

    seen: set[str] = set()
    status_counts = {"candidate": 0, "observation": 0, "removed": 0}
    for i, stock in enumerate(stocks):
        path = f"stocks[{i}]"
        if not isinstance(stock, dict):
            add(errors, path, "must be object")
            continue
        code = check_code(errors, stock.get("code"), f"{path}.code")
        if not code:
            continue
        if code in seen:
            add(errors, f"{path}.code", f"duplicate {code}")
        seen.add(code)
        if code in board_codes:
            add(errors, f"{path}.code", "duplicates board_excluded[]")
        if code in removed_codes:
            add(errors, f"{path}.code", "duplicates removed_stocks[]")
        check_scope(errors, code, f"{path}.code", scope, allowed_expected=True)

        if not clean_text(stock.get("name")):
            add(errors, f"{path}.name", "required")
        source_themes = stock.get("source_themes")
        if not isinstance(source_themes, list) or not source_themes:
            add(errors, f"{path}.source_themes", "must be non-empty list")

        filt = theme_stock_filter(stock)
        status = filt["status"]
        if status not in FILTER_STATUSES:
            add(errors, f"{path}.filter.status", f"invalid status {status!r}")
            continue
        status_counts[status] += 1
        if status in {"observation", "removed"} and not filt["reason"]:
            add(errors, f"{path}.filter.reason", "required for non-candidate stocks")
        if status == "removed" and not filt["source"]:
            add(errors, f"{path}.filter.source", "required for removed stocks")

        if pool is None:
            continue
        entry = pool.get(code)
        if entry is None:
            add(errors, f"{path}.code", "missing from pool_indicators.json")
            continue
        fetch_failed = bool(technical_value(stock, entry, "fetch_failed"))
        amount = parse_float(technical_value(stock, entry, "amount"))
        atr_pct = parse_float(technical_value(stock, entry, "atr_pct"))
        tech_score = parse_float(technical_value(stock, entry, "tech_score"))

        for field in ("amount", "atr_pct", "tech_score"):
            technical = stock.get("technical") if isinstance(stock.get("technical"), dict) else {}
            if field in technical:
                source = raw_value(entry, field) if field != "tech_score" else technical_value({}, entry, "tech_score")
                if not numbers_match(technical.get(field), source):
                    add(errors, f"{path}.technical.{field}", f"differs from pool_indicators for {code}")

        if status == "candidate":
            if fetch_failed:
                add(errors, f"{path}.filter.status", "fetch_failed stock cannot be candidate")
            if amount is not None and amount < 30000:
                add(errors, f"{path}.filter.status", "amount < 30000 cannot be candidate")
            if atr_pct is not None and atr_pct > 8:
                add(errors, f"{path}.filter.status", "atr_pct > 8 cannot be candidate")
            if tech_score is None:
                add(errors, f"{path}.filter.status", "tech_score=null should be observation")
        elif status == "observation":
            if fetch_failed and filt["reason"] not in {"Indicators_Fetch_Failed", "fetch_failed"}:
                add(errors, f"{path}.filter.reason", "fetch_failed observation should use Indicators_Fetch_Failed")

    if stocks and status_counts["candidate"] == 0 and status_counts["observation"] == 0 and not removed_codes:
        notes = doc.get("generation_notes")
        if not isinstance(notes, list) or not notes:
            add(errors, "generation_notes", "required when candidate/observation/removed are all empty")

    return errors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate theme_stocks.json")
    parser.add_argument("path", nargs="?", help="Path to theme_stocks.json")
    parser.add_argument("--date", help="YYYY-MM-DD; used for default path")
    parser.add_argument("--pool", help="Path to pool_indicators.json")
    parser.add_argument("--scope", help="Path to trading-scope.json")
    args = parser.parse_args(argv)

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    if args.path:
        path = Path(args.path)
    elif args.date:
        path = default_predict_dir(args.date) / "theme_stocks.json"
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

    pool = None
    pool_path = Path(args.pool) if args.pool else path.parent / "pool_indicators.json"
    if pool_path.exists():
        pool = load_pool(pool_path)
    scope = load_trading_scope(Path(args.scope) if args.scope else None)

    errors = check_doc(doc, scope, pool)
    if errors:
        print(f"[ERROR] {path} failed validation ({len(errors)} errors):", file=sys.stderr)
        for item in errors:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print(f"OK: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
