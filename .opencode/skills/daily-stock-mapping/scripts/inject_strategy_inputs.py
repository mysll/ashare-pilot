#!/usr/bin/env python3
"""Inject and validate mapper.md Strategy Inputs from pool_indicators.json.

The mapper is authored as markdown, but market/technical numeric fields must
come from the structured compute artifact. This script replaces the
`## Strategy Inputs` table with values from `pool_indicators.json`, then checks
that the written table still matches the JSON source.

Default behavior is pipeline-friendly: validation failures are reported with a
clear regeneration hint and exit code 0. Use `--strict` for CI-style hard fail.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CODE_RE = re.compile(r"\b(?:sh|sz)\d{6}\b")
DEFAULT_NUMERIC_TOLERANCE = 0.005


@dataclass
class Issue:
    code: str
    field: str
    mapper_value: str
    source_value: str
    message: str


def raw_value(entry: dict[str, Any], field: str) -> Any:
    raw = entry.get("raw_observation", {})
    value = raw.get(field)
    if isinstance(value, dict):
        return value.get("value")
    return value


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace("%", "").replace(",", "")
    if not text or text in {"-", "--", "—", "None", "null"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def format_num(value: Any, percent: bool = False) -> str:
    number = parse_float(value)
    if number is None:
        return "—"
    text = f"{number:.2f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return f"{text}%" if percent else text


def load_pool(path: Path) -> dict[str, dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"pool_indicators must be a list: {path}")
    pool: dict[str, dict[str, Any]] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        code = item.get("code")
        if isinstance(code, str):
            pool[code] = item
    return pool


def extract_section(text: str, heading: str) -> tuple[int, int] | None:
    marker = f"## {heading}"
    start = text.find(marker)
    if start < 0:
        return None
    next_match = re.search(r"(?m)^##\s+", text[start + len(marker) :])
    end = len(text) if next_match is None else start + len(marker) + next_match.start()
    return start, end


def parse_candidate_codes(mapper_text: str) -> list[str]:
    section = extract_section(mapper_text, "Candidate Pool")
    if section is None:
        return []
    start, end = section
    codes: list[str] = []
    seen: set[str] = set()
    for line in mapper_text[start:end].splitlines():
        if not line.startswith("|"):
            continue
        match = CODE_RE.search(line)
        if not match:
            continue
        code = match.group(0)
        if code not in seen:
            seen.add(code)
            codes.append(code)
    return codes


def build_strategy_inputs(codes: list[str], pool: dict[str, dict[str, Any]]) -> str:
    lines = [
        "## Strategy Inputs",
        "",
        "| Code | Price | PriceSource | MA20 | MA5 | ATR | ATR% | High20 | Low20 |",
        "|------|-------|-------------|------|-----|-----|------|--------|-------|",
    ]
    for code in codes:
        entry = pool.get(code, {})
        lines.append(
            "| {code} | {price} | PrevClose | {ma20} | {ma5} | {atr} | {atr_pct} | {high20} | {low20} |".format(
                code=code,
                price=format_num(raw_value(entry, "price")),
                ma20=format_num(raw_value(entry, "ma20")),
                ma5=format_num(raw_value(entry, "ma5")),
                atr=format_num(raw_value(entry, "atr")),
                atr_pct=format_num(raw_value(entry, "atr_pct"), percent=True),
                high20=format_num(raw_value(entry, "high20")),
                low20=format_num(raw_value(entry, "low20")),
            )
        )
    return "\n".join(lines).rstrip() + "\n"


def replace_strategy_inputs(mapper_text: str, replacement: str) -> str:
    section = extract_section(mapper_text, "Strategy Inputs")
    if section is None:
        suffix = "" if mapper_text.endswith("\n") else "\n"
        return mapper_text + suffix + "\n" + replacement
    start, end = section
    before = mapper_text[:start].rstrip()
    after = mapper_text[end:].lstrip("\n")
    return before + "\n\n" + replacement + ("\n" + after if after else "")


def parse_strategy_inputs(mapper_text: str) -> dict[str, dict[str, str]]:
    section = extract_section(mapper_text, "Strategy Inputs")
    if section is None:
        return {}
    start, end = section
    rows: dict[str, dict[str, str]] = {}
    for line in mapper_text[start:end].splitlines():
        if not line.startswith("|"):
            continue
        match = CODE_RE.search(line)
        if not match:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 9:
            continue
        code = match.group(0)
        rows[code] = {
            "price": cells[1],
            "price_source": cells[2],
            "ma20": cells[3],
            "ma5": cells[4],
            "atr": cells[5],
            "atr_pct": cells[6],
            "high20": cells[7],
            "low20": cells[8],
        }
    return rows


def values_match(mapper_value: str, source_value: Any, tolerance: float) -> bool:
    source_num = parse_float(source_value)
    mapper_num = parse_float(mapper_value)
    if source_num is None:
        return mapper_num is None
    if mapper_num is None:
        return False
    allowed = max(abs(source_num) * tolerance, 0.02)
    return abs(mapper_num - source_num) <= allowed


def validate(mapper_text: str, codes: list[str], pool: dict[str, dict[str, Any]], tolerance: float) -> list[Issue]:
    rows = parse_strategy_inputs(mapper_text)
    issues: list[Issue] = []
    fields = [
        ("price", "price"),
        ("ma20", "ma20"),
        ("ma5", "ma5"),
        ("atr", "atr"),
        ("atr_pct", "atr_pct"),
        ("high20", "high20"),
        ("low20", "low20"),
    ]
    for code in codes:
        row = rows.get(code)
        entry = pool.get(code)
        if row is None:
            issues.append(Issue(code, "row", "missing", "present", "Candidate missing from Strategy Inputs"))
            continue
        if entry is None:
            issues.append(Issue(code, "pool", "present", "missing", "Candidate missing from pool_indicators.json"))
            continue
        if row.get("price_source") != "PrevClose":
            issues.append(Issue(code, "price_source", row.get("price_source", ""), "PrevClose", "PriceSource must be PrevClose for pool indicator values"))
        for mapper_field, source_field in fields:
            source = raw_value(entry, source_field)
            mapper = row.get(mapper_field, "")
            if not values_match(mapper, source, tolerance):
                issues.append(
                    Issue(
                        code=code,
                        field=mapper_field,
                        mapper_value=mapper,
                        source_value=format_num(source, percent=mapper_field == "atr_pct"),
                        message="Mapper value differs from pool_indicators.json",
                    )
                )
    return issues


def print_report(issues: list[Issue], injected: bool, mapper_path: Path) -> None:
    status = "PASS" if not issues else "VALIDATION_FAILED_REGENERATE_MAPPER"
    action = "injected" if injected else "checked"
    print(f"[{status}] Strategy Inputs {action}: {mapper_path}")
    if not issues:
        return
    print("LLM action: regenerate mapper.md or rerun this injection after fixing Candidate Pool.")
    for issue in issues[:50]:
        print(
            f"- {issue.code} {issue.field}: mapper={issue.mapper_value} source={issue.source_value} ({issue.message})"
        )
    if len(issues) > 50:
        print(f"- ... {len(issues) - 50} more issues")


def main() -> int:
    parser = argparse.ArgumentParser(description="Inject and validate mapper Strategy Inputs")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--mapper", help="Path to mapper.md; default predict/{date}/mapper.md")
    parser.add_argument("--pool", help="Path to pool_indicators.json; default predict/{date}/pool_indicators.json")
    parser.add_argument("--check", action="store_true", help="Validate only; do not rewrite mapper.md")
    parser.add_argument("--strict", action="store_true", help="Return non-zero on validation failure")
    parser.add_argument("--tolerance", type=float, default=DEFAULT_NUMERIC_TOLERANCE, help="Relative numeric tolerance")
    args = parser.parse_args()

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    root = Path(__file__).resolve().parents[4]
    mapper_path = Path(args.mapper) if args.mapper else root / "predict" / args.date / "mapper.md"
    pool_path = Path(args.pool) if args.pool else root / "predict" / args.date / "pool_indicators.json"

    mapper_text = mapper_path.read_text(encoding="utf-8")
    pool = load_pool(pool_path)
    codes = parse_candidate_codes(mapper_text) or list(pool)

    injected = False
    if not args.check:
        replacement = build_strategy_inputs(codes, pool)
        mapper_text = replace_strategy_inputs(mapper_text, replacement)
        mapper_path.write_text(mapper_text, encoding="utf-8", newline="\n")
        injected = True

    issues = validate(mapper_text, codes, pool, args.tolerance)
    print_report(issues, injected, mapper_path)
    return 1 if issues and args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
