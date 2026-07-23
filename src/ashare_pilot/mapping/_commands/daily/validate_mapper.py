#!/usr/bin/env python3
"""Validate predict/{date}/mapper.json."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from ashare_pilot.mapping.daily_contract import CODE_RE, default_predict_dir, ensure_doc_date, load_pool, load_trading_scope, numbers_match, raw_value, read_json, scope_decision


PRICE_SOURCES = {"PrevClose", "Auction", "Live"}
MAJOR_EVENTS = {"positive", "negative", "none", "unknown"}
PATTERN_STATES = {
    "heat": {"RISING", "FALLING", "STABLE", "WATCH", "UNKNOWN"},
    "leader": {"STABLE", "DIVERGENCE", "ABSENT", "UNKNOWN"},
    "auction": {"LEADING", "LAGGING", "MATCH", "NEUTRAL", "UNKNOWN"},
    "rotation": {"PRIMARY", "SECONDARY", "TERTIARY", "NONE", "UNKNOWN"},
    "volume": {"SURGE", "NORMAL", "DRY", "UNKNOWN"},
}


def add(errors: list[str], path: str, message: str) -> None:
    errors.append(f"{path}: {message}")


def is_num(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def check_score(errors: list[str], obj: Any, path: str, require_trace: bool = False) -> None:
    if not isinstance(obj, dict):
        add(errors, path, "must be object")
        return
    value = obj.get("value")
    confidence = obj.get("confidence")
    if value is not None and (not is_num(value) or not 0 <= value <= 100):
        add(errors, f"{path}.value", "must be number in [0, 100] or null")
    if not is_num(confidence) or not 0 <= confidence <= 100:
        add(errors, f"{path}.confidence", "must be number in [0, 100]")
    if require_trace and value is not None and not (obj.get("trace") or obj.get("evidence")):
        add(errors, path, "non-null LLM field must have trace or evidence")


def check_doc(doc: dict[str, Any], pool: dict[str, dict[str, Any]] | None, scope: dict[str, Any] | None = None) -> list[str]:
    errors: list[str] = []
    if doc.get("schema_version") != "daily_mapper.v1":
        add(errors, "schema_version", "must be daily_mapper.v1")
    if not isinstance(doc.get("date"), str) or not re.match(r"^\d{4}-\d{2}-\d{2}$", doc.get("date", "")):
        add(errors, "date", "must be YYYY-MM-DD")

    candidates = doc.get("candidate_pool")
    if not isinstance(candidates, list):
        add(errors, "candidate_pool", "must be list")
        return errors

    seen: set[str] = set()
    for i, stock in enumerate(candidates):
        base = f"candidate_pool[{i}]"
        if not isinstance(stock, dict):
            add(errors, base, "must be object")
            continue
        code = stock.get("code")
        if not isinstance(code, str) or not CODE_RE.fullmatch(code):
            add(errors, f"{base}.code", "must be sh/sz + 6 digits")
            continue
        if code in seen:
            add(errors, f"{base}.code", f"duplicate {code}")
        seen.add(code)
        if scope is not None:
            decision = scope_decision(code, scope)
            if not decision["allowed"]:
                add(errors, f"{base}.code", f"excluded by trading scope ({decision['matched_rule']}): {decision['reason']}")

        scores = stock.get("scores")
        if not isinstance(scores, dict):
            add(errors, f"{base}.scores", "must be object")
        else:
            for key in ("composite", "tech", "theme_heat", "news_impact", "auction", "money_flow"):
                check_score(errors, scores.get(key), f"{base}.scores.{key}", require_trace=key == "news_impact")

        major = stock.get("major_event")
        if not isinstance(major, dict):
            add(errors, f"{base}.major_event", "must be object")
        else:
            if major.get("polarity") not in MAJOR_EVENTS:
                add(errors, f"{base}.major_event.polarity", "invalid enum")
            conf = major.get("confidence")
            if not is_num(conf) or not 0 <= conf <= 100:
                add(errors, f"{base}.major_event.confidence", "must be number in [0, 100]")

        pattern = stock.get("pattern")
        if not isinstance(pattern, dict):
            add(errors, f"{base}.pattern", "must be object")
        else:
            for key, allowed in PATTERN_STATES.items():
                item = pattern.get(key)
                if not isinstance(item, dict):
                    add(errors, f"{base}.pattern.{key}", "must be object")
                    continue
                if item.get("state") not in allowed:
                    add(errors, f"{base}.pattern.{key}.state", f"invalid enum {item.get('state')!r}")
                conf = item.get("confidence")
                if not is_num(conf) or not 0 <= conf <= 100:
                    add(errors, f"{base}.pattern.{key}.confidence", "must be number in [0, 100]")

        inputs = stock.get("strategy_inputs")
        if not isinstance(inputs, dict):
            add(errors, f"{base}.strategy_inputs", "must be object")
        else:
            if inputs.get("price_source") not in PRICE_SOURCES:
                add(errors, f"{base}.strategy_inputs.price_source", "invalid enum")
            for field in ("price", "ma20", "ma5", "atr", "atr_pct", "high20", "low20"):
                value = inputs.get(field)
                if value is not None and not is_num(value):
                    add(errors, f"{base}.strategy_inputs.{field}", "must be number or null")
                if pool is not None:
                    source = raw_value(pool.get(code), field)
                    if not numbers_match(value, source):
                        add(errors, f"{base}.strategy_inputs.{field}", f"differs from pool_indicators for {code}")

    return errors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate mapper.json")
    parser.add_argument("path", nargs="?", help="Path to mapper.json")
    parser.add_argument("--date", help="YYYY-MM-DD; used for default path")
    parser.add_argument("--pool", help="Path to pool_indicators.json")
    parser.add_argument("--scope", help="Path to trading-scope.json")
    args = parser.parse_args(argv)

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    if args.path:
        path = Path(args.path)
    elif args.date:
        path = default_predict_dir(args.date) / "mapper.json"
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
    errors = check_doc(doc, pool, scope)
    if errors:
        print(f"[ERROR] {path} failed validation ({len(errors)} errors):", file=sys.stderr)
        for item in errors:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print(f"OK: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
