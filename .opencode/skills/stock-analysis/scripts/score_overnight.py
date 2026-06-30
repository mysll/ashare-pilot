#!/usr/bin/env python3
"""Compute overnight premium scores for Compute Pool stocks.

5-dimension scoring (V1 Rule Based, Initial Weights):
    Theme Continuity  30%
    Capital Continuity 25%
    Tail Strength     20%
    Position Advantage 15%
    Risk Deduction    -10% (penalty)

Outputs: Opportunity Pool (A/B/C tiers, 20-40 stocks).

Usage:
    python score_overnight.py enriched.json --json -o opportunity.json
    python score_overnight.py enriched.json --json --opportunity-pool-size 30
"""

import argparse
import json
import sys


INITIAL_WEIGHTS = {
    "theme_continuity": 0.30,
    "capital_continuity": 0.25,
    "tail_strength": 0.20,
    "position_advantage": 0.15,
    "risk": -0.10,
}


def parse_float(val, default=0.0):
    if val is None or val == "-" or val == "":
        return default
    try:
        return float(
            str(val).replace("%", "").replace("+", "").replace(",", "").replace("亿", "")
        )
    except (ValueError, TypeError):
        return default


def score_theme_continuity(stock: dict) -> float:
    src = stock.get("source_pool", "")
    if src == "limit_up":
        return 0.85
    elif src == "turnover":
        return 0.60
    elif src == "gain_range":
        return 0.55
    return 0.40


def score_capital_continuity(stock: dict) -> float:
    enriched = stock.get("enriched", {})
    mf = enriched.get("money_flow", {})
    main_inflow = parse_float(mf.get("main_net_inflow", "0"))

    if main_inflow > 1.0:
        return 0.95
    elif main_inflow > 0.3:
        return 0.80
    elif main_inflow > 0:
        return 0.65
    elif main_inflow > -0.3:
        return 0.40
    else:
        return 0.15


def score_tail_strength(stock: dict) -> float:
    enriched = stock.get("enriched", {})
    rt = enriched.get("real_time", {})
    price = parse_float(rt.get("price", 0))
    high = parse_float(rt.get("high", 0))
    low = parse_float(rt.get("low", 0))
    turnover = parse_float(stock.get("turnover", "0%"))

    if price <= 0 or high <= low:
        return 0.50

    price_position = (price - low) / (high - low) if high > low else 0.5

    if turnover > 20:
        return 0.35
    elif 5 <= turnover <= 15 and price_position > 0.6:
        return 0.85
    elif 2 <= turnover <= 10 and price_position > 0.7:
        return 0.75
    return 0.50


def score_position_advantage(stock: dict) -> float:
    change_pct = parse_float(stock.get("change_pct", "0%"))

    if 2.0 <= change_pct <= 5.0:
        return 0.95
    elif 0.5 <= change_pct < 2.0:
        return 0.65
    elif 5.0 < change_pct <= 7.0:
        return 0.55
    elif 7.0 < change_pct <= 9.0:
        return 0.30
    else:
        return 0.10


def score_risk_penalty(stock: dict) -> float:
    change_pct = parse_float(stock.get("change_pct", "0%"))
    turnover = parse_float(stock.get("turnover", "0%"))

    penalty = 0.0

    if change_pct >= 9.5:
        penalty += 0.30
    if turnover > 25:
        penalty += 0.25
    elif turnover > 15:
        penalty += 0.10
    if stock.get("source_pool") == "limit_up":
        penalty += 0.10

    return min(penalty, 1.0)


def classify_tier(score: float) -> str:
    if score >= 75:
        return "A"
    elif score >= 60:
        return "B"
    elif score >= 45:
        return "C"
    else:
        return "D"


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Compute overnight premium scores")
    parser.add_argument("input", help="Enriched Compute Pool JSON")
    parser.add_argument(
        "--opportunity-pool-size", type=int, default=30,
        help="Final pool size (default: 30)",
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("-o", "--output", metavar="FILE", help="Save output to file")
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    pool = data.get("compute_pool", [])
    if isinstance(data, list):
        pool = data

    scored = []
    for stock in pool:
        theme = score_theme_continuity(stock)
        capital = score_capital_continuity(stock)
        tail = score_tail_strength(stock)
        position = score_position_advantage(stock)
        risk = score_risk_penalty(stock)

        overnight_score = round(
            theme * INITIAL_WEIGHTS["theme_continuity"] * 100
            + capital * INITIAL_WEIGHTS["capital_continuity"] * 100
            + tail * INITIAL_WEIGHTS["tail_strength"] * 100
            + position * INITIAL_WEIGHTS["position_advantage"] * 100
            - risk * abs(INITIAL_WEIGHTS["risk"]) * 100,
            1,
        )

        tier = classify_tier(overnight_score)

        stock["overnight_score"] = max(overnight_score, 0)
        stock["score_breakdown"] = {
            "theme_continuity": round(theme * 100, 1),
            "capital_continuity": round(capital * 100, 1),
            "tail_strength": round(tail * 100, 1),
            "position_advantage": round(position * 100, 1),
            "risk_penalty": round(risk * 100, 1),
        }
        stock["tier"] = tier
        scored.append(stock)

    scored.sort(key=lambda x: x.get("overnight_score", 0), reverse=True)

    opportunity_pool = [
        s for s in scored if s["tier"] in ("A", "B", "C")
    ][:args.opportunity_pool_size]

    leader_watch = [s for s in scored if s["tier"] == "A"][:5]
    early_breakout = [s for s in scored if s["tier"] == "C"][:10]

    output = {
        "weights_version": "V1_Rule_Based",
        "scored_count": len(scored),
        "opportunity_pool_size": len(opportunity_pool),
        "leader_watch": leader_watch,
        "premium_candidates": [s for s in opportunity_pool if s["tier"] == "B"],
        "early_breakout": early_breakout,
        "opportunity_pool": opportunity_pool,
    }

    output_str = json.dumps(output, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            f.write(output_str)
        print(f"Saved to {args.output}")
    else:
        print(output_str)


if __name__ == "__main__":
    main()
