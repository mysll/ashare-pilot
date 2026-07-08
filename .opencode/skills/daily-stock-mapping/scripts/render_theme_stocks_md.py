#!/usr/bin/env python3
"""Render theme_stocks.md from theme_stocks.json."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from mapper_json_lib import clean_text, default_predict_dir, ensure_doc_date, format_num, read_json, technical_value, theme_stock_filter, theme_stock_theme_text


def missing(value: Any) -> str:
    return "-" if value is None or value == "" else str(value)


def fmt_bool(value: Any) -> str:
    return "Y" if bool(value) else "-"


def fmt_source_flags(flags: Any, key: str) -> str:
    if isinstance(flags, dict):
        return fmt_bool(flags.get(key))
    if isinstance(flags, list):
        return fmt_bool(key in flags)
    return "-"


def render(doc: dict[str, Any]) -> str:
    lines: list[str] = [
        "# Stock Pool",
        "",
        f"Date: {doc.get('date')}",
        "",
        "## Themes Summary",
        "",
        "| # | Theme | Heat | Confidence | Stocks in Pool |",
        "|---|-------|:----:|:----------:|:--------------:|",
    ]

    for i, theme in enumerate(doc.get("themes", []), start=1):
        if not isinstance(theme, dict):
            continue
        lines.append(
            "| {idx} | {name} | {heat} | {conf} | {count} |".format(
                idx=theme.get("rank") or i,
                name=missing(theme.get("name")),
                heat=format_num(theme.get("heat")),
                conf=format_num(theme.get("confidence")),
                count=missing(theme.get("stock_count")),
            )
        )

    stocks = [item for item in doc.get("stocks", []) if isinstance(item, dict)]
    lines.extend(
        [
            "",
            f"Total unique stocks: {len(stocks)}",
            "",
            "## Stock Pool (After Technical Enrichment)",
            "",
            "| # | Code | Name | Best Score | Source Themes | News? | LHB? | Mkt? | Tech | Amount | ATR% | Risk? | Filter | Reason |",
            "|---|------|------|:----------:|---------------|:-----:|:----:|:----:|:----:|:------:|:----:|-------|--------|--------|",
        ]
    )

    for i, stock in enumerate(stocks, start=1):
        filt = theme_stock_filter(stock)
        flags = stock.get("source_flags")
        tech = stock.get("technical") if isinstance(stock.get("technical"), dict) else {}
        risk = tech.get("risk_flags") or tech.get("risk_type") or stock.get("risk_flags")
        if isinstance(risk, list):
            risk_text = ",".join(str(item) for item in risk) if risk else "No"
        else:
            risk_text = clean_text(risk) or "No"
        lines.append(
            "| {idx} | {code} | {name} | {score} | {themes} | {news} | {lhb} | {mkt} | {tech} | {amount} | {atr} | {risk} | {status} | {reason} |".format(
                idx=i,
                code=missing(stock.get("code")),
                name=missing(stock.get("name")),
                score=format_num(stock.get("best_score")),
                themes=missing(theme_stock_theme_text(stock)),
                news=fmt_source_flags(flags, "news"),
                lhb=fmt_source_flags(flags, "lhb"),
                mkt=fmt_source_flags(flags, "market"),
                tech=format_num(technical_value(stock, None, "tech_score")),
                amount=format_num(technical_value(stock, None, "amount")),
                atr=format_num(technical_value(stock, None, "atr_pct"), percent=True),
                risk=missing(risk_text),
                status=missing(filt["status"]),
                reason=missing(filt["reason"]),
            )
        )

    lines.extend(
        [
            "",
            "**Removed stocks (failed hard filters):**",
            "",
            "| Code | Name | Reason | ExclusionSource |",
            "|------|------|--------|-----------------|",
        ]
    )
    for stock in doc.get("removed_stocks", []):
        if not isinstance(stock, dict):
            continue
        lines.append(
            f"| {missing(stock.get('code'))} | {missing(stock.get('name'))} | {missing(stock.get('reason'))} | {missing(stock.get('source'))} |"
        )

    lines.extend(
        [
            "",
            "## Board-Excluded Stocks",
            "",
            "| Code | Name | Reason | Rule |",
            "|------|------|--------|------|",
        ]
    )
    for stock in doc.get("board_excluded", []):
        if not isinstance(stock, dict):
            continue
        lines.append(
            f"| {missing(stock.get('code'))} | {missing(stock.get('name'))} | {missing(stock.get('reason'))} | {missing(stock.get('matched_rule'))} |"
        )

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Render theme_stocks.md from theme_stocks.json")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--input", help="Path to theme_stocks.json; default predict/{date}/theme_stocks.json")
    parser.add_argument("--output", help="Path to theme_stocks.md; default predict/{date}/theme_stocks.md")
    args = parser.parse_args()

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    predict_dir = default_predict_dir(args.date)
    input_path = Path(args.input) if args.input else predict_dir / "theme_stocks.json"
    output_path = Path(args.output) if args.output else predict_dir / "theme_stocks.md"

    doc = read_json(input_path)
    if not isinstance(doc, dict):
        print("[ERROR] root must be object", file=sys.stderr)
        return 1
    try:
        ensure_doc_date(doc, args.date, str(input_path))
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    if doc.get("schema_version") != "daily_theme_stocks.v1":
        print("[ERROR] schema_version must be daily_theme_stocks.v1", file=sys.stderr)
        return 1

    output_path.write_text(render(doc), encoding="utf-8", newline="\n")
    print(f"OK: wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
