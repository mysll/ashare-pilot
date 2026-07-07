#!/usr/bin/env python3
"""Validate predict/{date}/mapper.annotations.json."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from mapper_json_lib import CODE_RE, default_predict_dir, ensure_doc_date, read_json


RELEVANCE = {"R0", "R1", "R2", "R3", "R4"}
PROMINENCE = {"P0", "P1", "P2", "P3"}
MAJOR_EVENTS = {"positive", "negative", "none", "unknown"}
POLARITY = {"bullish", "neutral", "bearish", "unknown"}
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


def check_conf(errors: list[str], value: Any, path: str) -> None:
    if not is_num(value) or not 0 <= value <= 100:
        add(errors, path, "confidence must be number in [0, 100]")


def has_evidence_or_trace(item: dict[str, Any]) -> bool:
    return bool(item.get("evidence") or item.get("trace"))


def check_scored(errors: list[str], item: Any, path: str, require_value: bool = True) -> None:
    if item is None:
        return
    if not isinstance(item, dict):
        add(errors, path, "must be object")
        return
    if require_value and "value" not in item:
        add(errors, f"{path}.value", "missing")
    if "confidence" not in item:
        add(errors, f"{path}.confidence", "missing")
    else:
        check_conf(errors, item.get("confidence"), f"{path}.confidence")
    if not has_evidence_or_trace(item):
        add(errors, path, "must include evidence or trace")


def validate(doc: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if doc.get("schema_version") != "daily_mapper_annotations.v1":
        add(errors, "schema_version", "must be daily_mapper_annotations.v1")
    if not isinstance(doc.get("date"), str) or not re.match(r"^\d{4}-\d{2}-\d{2}$", doc.get("date", "")):
        add(errors, "date", "must be YYYY-MM-DD")

    themes = doc.get("themes", [])
    if themes is not None and not isinstance(themes, list):
        add(errors, "themes", "must be list")
    elif isinstance(themes, list):
        for i, theme in enumerate(themes):
            base = f"themes[{i}]"
            if not isinstance(theme, dict):
                add(errors, base, "must be object")
                continue
            if not isinstance(theme.get("name"), str) or not theme.get("name"):
                add(errors, f"{base}.name", "must be non-empty string")
            check_scored(errors, theme.get("emotion"), f"{base}.emotion")
            policy = theme.get("policy_polarity")
            if policy is not None:
                if not isinstance(policy, dict):
                    add(errors, f"{base}.policy_polarity", "must be object")
                else:
                    if policy.get("value") not in POLARITY:
                        add(errors, f"{base}.policy_polarity.value", "invalid enum")
                    if "confidence" in policy:
                        check_conf(errors, policy.get("confidence"), f"{base}.policy_polarity.confidence")
                    if not has_evidence_or_trace(policy):
                        add(errors, f"{base}.policy_polarity", "must include evidence or trace")

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
            add(errors, f"{base}.code", "must be sh/sz + 6 digits")
        elif code in seen:
            add(errors, f"{base}.code", f"duplicate {code}")
        else:
            seen.add(code)

        relevance = stock.get("news_relevance")
        if relevance is not None:
            if not isinstance(relevance, dict):
                add(errors, f"{base}.news_relevance", "must be object")
            else:
                if relevance.get("r") not in RELEVANCE:
                    add(errors, f"{base}.news_relevance.r", "invalid enum")
                if relevance.get("p") not in PROMINENCE:
                    add(errors, f"{base}.news_relevance.p", "invalid enum")
                check_conf(errors, relevance.get("confidence"), f"{base}.news_relevance.confidence")
                if not has_evidence_or_trace(relevance):
                    add(errors, f"{base}.news_relevance", "must include evidence or trace")

        major = stock.get("major_event")
        if major is not None:
            if not isinstance(major, dict):
                add(errors, f"{base}.major_event", "must be object")
            else:
                if major.get("polarity") not in MAJOR_EVENTS:
                    add(errors, f"{base}.major_event.polarity", "invalid enum")
                check_conf(errors, major.get("confidence"), f"{base}.major_event.confidence")
                if not has_evidence_or_trace(major):
                    add(errors, f"{base}.major_event", "must include evidence or trace")

        pattern = stock.get("pattern")
        if pattern is not None:
            if not isinstance(pattern, dict):
                add(errors, f"{base}.pattern", "must be object")
            else:
                for key, allowed in PATTERN_STATES.items():
                    item = pattern.get(key)
                    if item is None:
                        continue
                    if not isinstance(item, dict):
                        add(errors, f"{base}.pattern.{key}", "must be object")
                        continue
                    if item.get("state") not in allowed:
                        add(errors, f"{base}.pattern.{key}.state", "invalid enum")
                    check_conf(errors, item.get("confidence"), f"{base}.pattern.{key}.confidence")
                    if not has_evidence_or_trace(item):
                        add(errors, f"{base}.pattern.{key}", "must include evidence or trace")

        anomaly = stock.get("anomaly")
        if anomaly is not None and not isinstance(anomaly, str):
            add(errors, f"{base}.anomaly", "must be string or null")
        if isinstance(anomaly, str) and len(anomaly) > 80:
            add(errors, f"{base}.anomaly", "must be <= 80 chars")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate mapper.annotations.json")
    parser.add_argument("path", nargs="?", help="Path to mapper.annotations.json")
    parser.add_argument("--date", help="YYYY-MM-DD; used for default path")
    args = parser.parse_args()

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    if args.path:
        path = Path(args.path)
    elif args.date:
        path = default_predict_dir(args.date) / "mapper.annotations.json"
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
