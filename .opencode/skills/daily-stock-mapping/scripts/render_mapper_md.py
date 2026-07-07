#!/usr/bin/env python3
"""Render mapper.md from mapper.json."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from mapper_json_lib import default_predict_dir, ensure_doc_date, format_num, read_json


def missing(value: Any) -> str:
    return "-" if value is None or value == "" else str(value)


def fmt_score(obj: dict[str, Any] | None) -> str:
    if not isinstance(obj, dict):
        return "-"
    return format_num(obj.get("value"))


def fmt_conf(obj: dict[str, Any] | None) -> str:
    if not isinstance(obj, dict):
        return "-"
    return format_num(obj.get("confidence"))


def fmt_list(items: Any) -> str:
    if not items:
        return "-"
    if isinstance(items, list):
        return ",".join(str(item) for item in items)
    return str(items)


def render(doc: dict[str, Any]) -> str:
    lines: list[str] = [f"# Structured Dataset - {doc.get('date')}", ""]
    market = doc.get("market_state", {})
    lines.extend(
        [
            "## Market State",
            "",
            "| Field | Value |",
            "|-------|-------|",
            f"| DominantThemes | {fmt_dominant(market.get('dominant_themes'))} |",
            f"| FinancingFlow | {missing(market.get('financing_flow'))} |",
            f"| RiskFlags | {fmt_list(market.get('risk_flags'))} |",
            f"| BoardPolicy | {fmt_board_policy(market.get('board_policy'))} |",
            "| RegimeHint | (Step 3 Reasoning territory) |",
            "",
            "## Theme Ranking",
            "",
            "| Theme | Final | Rank | HeatTrace |",
            "|-------|:-----:|:----:|-----------|",
        ]
    )
    for theme in doc.get("themes", []):
        lines.append(
            f"| {missing(theme.get('name'))} | {format_num(theme.get('final_heat'))} | {missing(theme.get('rank'))} | {missing(theme.get('heat_trace'))} |"
        )

    lines.extend(
        [
            "",
            "## Candidate Pool",
            "",
            "Composite formula: Theme_Heat*0.30 + News_Impact*0.20 + Auction_Signal*0.20 + Tech_Score*0.20 + Money_Flow*0.10",
            "",
            "| Code | Name | comp.value | comp.conf | tech.value | tech.conf | th_heat.value | news_imp.value | maj_ev.pol | risk_type.value | pattern.heat | pattern.leader | pattern.auct | auc.value | anomaly | NewsLink | RoleTags |",
            "|------|------|:---------:|:---------:|:----------:|:---------:|:------------:|:------------:|:----------:|:--------------:|:-----------:|:-------------:|:-----------:|:--------:|:--------|:---------|:----------|",
        ]
    )
    for stock in doc.get("candidate_pool", []):
        scores = stock.get("scores", {})
        pattern = stock.get("pattern", {})
        lines.append(
            "| {code} | {name} | {comp} | {comp_conf} | {tech} | {tech_conf} | {theme_heat} | {news_impact} | {major} | {risk} | {p_heat} | {p_leader} | {p_auction} | {auction} | {anomaly} | {news_link} | {roles} |".format(
                code=missing(stock.get("code")),
                name=missing(stock.get("name")),
                comp=fmt_score(scores.get("composite")),
                comp_conf=fmt_conf(scores.get("composite")),
                tech=fmt_score(scores.get("tech")),
                tech_conf=fmt_conf(scores.get("tech")),
                theme_heat=fmt_score(scores.get("theme_heat")),
                news_impact=fmt_score(scores.get("news_impact")),
                major=missing((stock.get("major_event") or {}).get("polarity")),
                risk=fmt_list((stock.get("risk_type") or {}).get("value")),
                p_heat=missing((pattern.get("heat") or {}).get("state")),
                p_leader=missing((pattern.get("leader") or {}).get("state")),
                p_auction=missing((pattern.get("auction") or {}).get("state")),
                auction=fmt_score(scores.get("auction")),
                anomaly=missing(stock.get("anomaly")),
                news_link=missing(stock.get("news_link")),
                roles=fmt_list(stock.get("role_tags")),
            )
        )

    lines.extend(
        [
            "",
            "## Strategy Inputs",
            "",
            "| Code | Price | PriceSource | MA20 | MA5 | ATR | ATR% | High20 | Low20 |",
            "|------|-------|-------------|------|-----|-----|------|--------|-------|",
        ]
    )
    for stock in doc.get("candidate_pool", []):
        inputs = stock.get("strategy_inputs", {})
        lines.append(
            "| {code} | {price} | {source} | {ma20} | {ma5} | {atr} | {atr_pct} | {high20} | {low20} |".format(
                code=missing(stock.get("code")),
                price=format_num(inputs.get("price")),
                source=missing(inputs.get("price_source")),
                ma20=format_num(inputs.get("ma20")),
                ma5=format_num(inputs.get("ma5")),
                atr=format_num(inputs.get("atr")),
                atr_pct=format_num(inputs.get("atr_pct"), percent=True),
                high20=format_num(inputs.get("high20")),
                low20=format_num(inputs.get("low20")),
            )
        )

    lines.extend(["", "## Observation Pool", "", "| Code | Name | Composite | Theme | Reason | Anomaly |", "|------|------|:---------:|-------|--------|---------|"])
    for stock in doc.get("observation_pool", []):
        lines.append(
            f"| {missing(stock.get('code'))} | {missing(stock.get('name'))} | {format_num(stock.get('composite'))} | {missing(stock.get('theme'))} | {missing(stock.get('reason'))} | {missing(stock.get('anomaly'))} |"
        )

    lines.extend(["", "## Excluded Stocks", "", "| Code | Name | ExclusionReason | ExclusionSource |", "|------|------|-----------------|-----------------|"])
    for stock in doc.get("excluded_stocks", []):
        lines.append(
            f"| {missing(stock.get('code'))} | {missing(stock.get('name'))} | {missing(stock.get('reason'))} | {missing(stock.get('source'))} |"
        )

    return "\n".join(lines).rstrip() + "\n"


def fmt_dominant(items: Any) -> str:
    if not items:
        return "-"
    parts = []
    for item in items:
        if isinstance(item, dict):
            heat = item.get("heat")
            parts.append(f"{item.get('name')}({format_num(heat)})" if heat is not None else str(item.get("name")))
        else:
            parts.append(str(item))
    return ", ".join(parts)


def fmt_board_policy(policy: Any) -> str:
    if not isinstance(policy, dict) or not policy:
        return "-"
    return ", ".join(f"{key}={value}" for key, value in policy.items())


def main() -> int:
    parser = argparse.ArgumentParser(description="Render mapper.md from mapper.json")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--input", help="Path to mapper.json; default predict/{date}/mapper.json")
    parser.add_argument("--output", help="Path to mapper.md; default predict/{date}/mapper.md")
    args = parser.parse_args()

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    predict_dir = default_predict_dir(args.date)
    input_path = Path(args.input) if args.input else predict_dir / "mapper.json"
    output_path = Path(args.output) if args.output else predict_dir / "mapper.md"

    doc = read_json(input_path)
    if not isinstance(doc, dict):
        print("[ERROR] root must be object", file=sys.stderr)
        return 1
    try:
        ensure_doc_date(doc, args.date, str(input_path))
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    output_path.write_text(render(doc), encoding="utf-8", newline="\n")
    print(f"OK: wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
