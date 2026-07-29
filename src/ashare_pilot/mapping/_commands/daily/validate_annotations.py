#!/usr/bin/env python3
"""Validate predict/{date}/mapper.annotations.json."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

from ashare_pilot.mapping.daily_contract import CODE_RE, default_predict_dir, ensure_doc_date, read_json, theme_stock_filter


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


def validate(doc: dict[str, Any], candidate_codes: set[str] | None = None) -> list[str]:
    errors: list[str] = []
    if doc.get("schema_version") != "daily_mapper_annotations.v1":
        add(errors, "schema_version", "must be daily_mapper_annotations.v1")
    if not isinstance(doc.get("date"), str) or not re.match(r"^\d{4}-\d{2}-\d{2}$", doc.get("date", "")):
        add(errors, "date", "must be YYYY-MM-DD")

    if doc.get("themes") not in (None, []):
        add(errors, "themes", "duplicate theme annotations were removed; themes.json owns theme semantics")

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

        # Extra non-candidate rows are structurally checked above, then warned
        # and skipped by coverage/merge. Candidate semantic requirements must
        # not turn those discarded rows into publication blockers.
        if candidate_codes is not None and code not in candidate_codes:
            continue

        relevance = stock.get("news_relevance")
        if relevance is None:
            add(errors, f"{base}.news_relevance", "missing; required for every deterministic candidate")
        else:
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
        if isinstance(anomaly, str) and len(anomaly) > 50:
            add(errors, f"{base}.anomaly", "must be <= 50 chars")

    return errors


def validate_candidate_coverage(
    doc: dict[str, Any],
    theme_stocks: dict[str, Any],
    annotation_input: dict[str, Any] | None = None,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    expected = [
        stock.get("code") for stock in theme_stocks.get("stocks", [])
        if isinstance(stock, dict) and theme_stock_filter(stock)["status"] == "candidate"
    ]
    actual = [stock.get("code") for stock in doc.get("stocks", []) if isinstance(stock, dict)]
    expected_set = set(expected)
    actual_set = set(actual)
    missing = [code for code in expected if code not in actual_set]
    extra = [code for code in actual if code not in expected_set]
    if missing:
        add(errors, "stocks", "missing deterministic candidate annotations: " + ",".join(str(code) for code in missing))
    if extra:
        warnings.append("extra non-candidate annotations will be skipped: " + ",".join(str(code) for code in extra))

    input_candidates = {
        item.get("code"): item
        for item in (annotation_input or {}).get("candidates", [])
        if isinstance(annotation_input, dict)
        and isinstance(item, dict)
        and isinstance(item.get("code"), str)
    }
    pairs = []
    for stock in doc.get("stocks", []):
        if not isinstance(stock, dict) or stock.get("code") not in expected_set:
            continue
        relevance = stock.get("news_relevance")
        if isinstance(relevance, dict):
            pairs.append((relevance.get("r"), relevance.get("p")))
            evidence = input_candidates.get(stock.get("code"), {})
            direct_refs = evidence.get("direct_news_refs", [])
            role_tags = evidence.get("role_tags", [])
            has_direct_evidence = (
                isinstance(direct_refs, list) and bool(direct_refs)
            ) or (
                isinstance(role_tags, list) and "NewsDirect" in role_tags
            )
            if has_direct_evidence and relevance.get("r") == "R2":
                add(
                    errors,
                    f"stocks[{stock.get('code')}].news_relevance.r",
                    "NewsDirect/direct_news_refs evidence must not be downgraded to theme-level R2",
                )
    if len(pairs) >= 5 and len(set(pairs)) == 1 and pairs[0] == ("R2", "P2"):
        warnings.append(
            "uniform R2/P2 accepted because output diversity is not a correctness condition; "
            "direct evidence is validated per candidate"
        )
    return errors, warnings


def validate_news_refs(doc: dict[str, Any], news_doc: dict[str, Any]) -> list[str]:
    valid = {f"news#{item.get('id')}" for item in news_doc.get("items", []) if isinstance(item, dict) and isinstance(item.get("id"), int)}
    errors: list[str] = []
    for i, stock in enumerate(doc.get("stocks", [])):
        if not isinstance(stock, dict):
            continue
        refs = []
        relevance = stock.get("news_relevance")
        if isinstance(relevance, dict) and relevance.get("evidence"):
            refs.append((f"stocks[{i}].news_relevance.evidence", relevance["evidence"]))
        if stock.get("news_link"):
            refs.append((f"stocks[{i}].news_link", stock["news_link"]))
        major = stock.get("major_event")
        if isinstance(major, dict) and major.get("evidence"):
            refs.append((f"stocks[{i}].major_event.evidence", major["evidence"]))
        for path, value in refs:
            for ref in re.findall(r"news#\d+", str(value)):
                if ref not in valid:
                    add(errors, path, f"unresolved canonical evidence ref {ref}")
    return errors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate mapper.annotations.json")
    parser.add_argument("path", nargs="?", help="Path to mapper.annotations.json")
    parser.add_argument("--date", help="YYYY-MM-DD; used for default path")
    parser.add_argument("--theme-stocks", help="Path to theme_stocks.json; defaults beside annotations")
    parser.add_argument(
        "--annotation-input",
        help="Path to .mapper_annotation_input.json; defaults beside annotations when present",
    )
    args = parser.parse_args(argv)

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
    theme_stocks_path = Path(args.theme_stocks) if args.theme_stocks else path.parent / "theme_stocks.json"
    warnings: list[str] = []
    theme_stocks = None
    if theme_stocks_path.exists():
        theme_stocks = read_json(theme_stocks_path)
    candidate_codes = {
        stock.get("code") for stock in theme_stocks.get("stocks", [])
        if isinstance(theme_stocks, dict) and isinstance(stock, dict) and theme_stock_filter(stock)["status"] == "candidate"
    } if isinstance(theme_stocks, dict) else None
    errors = validate(doc, candidate_codes)
    if theme_stocks_path.exists() and not isinstance(theme_stocks, dict):
        errors.append(f"{theme_stocks_path}: root must be object")
    elif isinstance(theme_stocks, dict):
        if args.date:
            try:
                ensure_doc_date(theme_stocks, args.date, str(theme_stocks_path))
            except ValueError as exc:
                errors.append(str(exc))
        annotation_input_path = (
            Path(args.annotation_input)
            if args.annotation_input
            else path.parent / ".mapper_annotation_input.json"
        )
        annotation_input = read_json(annotation_input_path) if annotation_input_path.exists() else None
        coverage_errors, warnings = validate_candidate_coverage(
            doc,
            theme_stocks,
            annotation_input if isinstance(annotation_input, dict) else None,
        )
        errors.extend(coverage_errors)
    elif args.date or args.theme_stocks:
        errors.append(f"missing theme_stocks.json for candidate coverage: {theme_stocks_path}")
    news_path = path.parent / "news.json"
    if news_path.exists():
        news_doc = read_json(news_path)
        if isinstance(news_doc, dict):
            errors.extend(validate_news_refs(doc, news_doc))
    if errors:
        print(f"[ERROR] {path} failed validation ({len(errors)} errors):", file=sys.stderr)
        for item in errors:
            print(f"  - {item}", file=sys.stderr)
        return 1
    for warning in warnings:
        print(f"[WARN] {warning}", file=sys.stderr)
    print(f"OK: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
