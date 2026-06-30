#!/usr/bin/env python3
"""Compute overnight premium scores for Compute Pool stocks.

V1.1 Percentile-Based Scoring (replaces V1.0 hard thresholds):
    Each stock is scored by its percentile rank within the Compute Pool
    across 5 continuous dimensions. No hard thresholds — distribution is
    forced uniform across 0-100.

Dimensions:
    Theme Continuity     30%  — source_pool ordinal → percentile
    Capital Continuity   25%  — main_net_inflow → percentile
    Tail Strength        20%  — price_position × turnover_quality → percentile
    Position Advantage   15%  — gaussian(|change_pct - 4%|) → percentile
    Risk Penalty        -10%  — combined penalty → inverse percentile

Output: ScoreObject with {value, rank, confidence, trace, tier}

Usage:
    python score_overnight.py enriched.json --json -o opportunity.json
    python score_overnight.py enriched.json --json --opportunity-pool-size 30
"""

import argparse
import json
import math
import sys


WEIGHTS_V1_1 = {
    "theme_continuity": 0.20,
    "capital_continuity": 0.20,
    "tail_strength": 0.15,
    "position_advantage": 0.10,
    "risk_penalty": 0.10,
    "intensity": 0.10,
    "conviction": 0.10,
    "consistency": 0.05,
}


def parse_float(val, default=0.0):
    if val is None or val == "-" or val == "":
        return default
    try:
        return float(
            str(val).replace("%", "").replace("+", "").replace(",", "").replace("亿", "").replace("万", "")
        )
    except (ValueError, TypeError):
        return default


def percentile_rank(values, value, invert=False):
    """Return percentile rank 0-100 of value within values.
    invert=True: low values get high percentile (for risk/penalty).
    Returns 50 for zero-variance case.
    """
    if not values:
        return 50.0
    n = len(values)
    if max(values) - min(values) < 1e-9:
        return 50.0
    if invert:
        lower_count = sum(1 for v in values if v <= value)
    else:
        lower_count = sum(1 for v in values if v < value)
    return round(lower_count / n * 100, 1)


def sigmoid(x, center=0, steepness=1):
    """Smooth sigmoid: ~0 when x<<center, ~1 when x>>center."""
    try:
        return 1.0 / (1.0 + math.exp(-(x - center) * steepness))
    except OverflowError:
        return 1.0 if x > center else 0.0


def gaussian_distance(x, mu, sigma):
    """Gaussian peak at mu: 1.0 at x=mu, decays to ~0 as |x-mu| > 3*sigma."""
    if sigma <= 0:
        return 1.0 if abs(x - mu) < 0.1 else 0.0
    return math.exp(-((x - mu) ** 2) / (2 * sigma * sigma))


def extract_theme_raw(stock):
    """Ordinal source + capital blend. Falls back to capital intensity
    when all stocks share the same source_pool (zero-variance guard)."""
    mapping = {"limit_up": 1.0, "turnover": 0.7, "gain_range": 0.4}
    base = mapping.get(stock.get("source_pool", ""), 0.1)
    enriched = stock.get("enriched", {})
    mf = enriched.get("money_flow", {})
    inflow = parse_float(mf.get("main_net_inflow", "0"))
    cap_blend = sigmoid(inflow, center=1.0, steepness=1.5)
    return base * 0.7 + cap_blend * 0.3


def extract_capital_raw(stock):
    """main_net_inflow in 亿 (log-scaled for distribution spread)."""
    enriched = stock.get("enriched", {})
    mf = enriched.get("money_flow", {})
    raw = parse_float(mf.get("main_net_inflow", "0"))
    return math.log(max(raw, 0.01) + 1)  # log scale spreads small values


def extract_tail_raw(stock):
    """price_position (0-1) × turnover_quality (peak at 10% turnover)."""
    enriched = stock.get("enriched", {})
    rt = enriched.get("real_time", {})
    price = parse_float(rt.get("price", 0))
    high = parse_float(rt.get("high", 0))
    low = parse_float(rt.get("low", 0))
    turnover = parse_float(stock.get("turnover", "0%"))

    if price <= 0 or high <= low:
        return 0.3

    price_pos = (price - low) / (high - low)
    price_pos = max(0.0, min(1.0, price_pos))

    turnover_quality = gaussian_distance(turnover, mu=10, sigma=8)
    volume_ratio = parse_float(stock.get("volume_ratio", "1.0"))
    vol_bonus = max(0.5, min(1.5, volume_ratio))

    return price_pos * turnover_quality * vol_bonus


def extract_position_raw(stock):
    """Gaussian peak at +4% — sweet spot for overnight holding.
    >8% or <0% gets near-zero score.
    """
    change_pct = parse_float(stock.get("change_pct", "0%"))
    return gaussian_distance(change_pct, mu=4.0, sigma=3.0)


def extract_risk_raw(stock):
    """Combined penalty: high change% + high turnover + limit-up source."""
    change_pct = parse_float(stock.get("change_pct", "0%"))
    turnover = parse_float(stock.get("turnover", "0%"))
    penalty = 0.0
    if change_pct >= 9.5:
        penalty += 0.4
    elif change_pct >= 7.0:
        penalty += 0.2
    elif change_pct >= 5.0:
        penalty += 0.05
    if turnover > 25:
        penalty += 0.3
    elif turnover > 15:
        penalty += 0.15
    elif turnover > 10:
        penalty += 0.05
    if stock.get("source_pool") == "limit_up":
        penalty += 0.15
    return min(penalty, 1.0)


def extract_intensity_raw(stock):
    """Capital intensity: main_net_inflow normalized by turnover.
    High inflow with low turnover = strong conviction (quality over quantity).
    """
    enriched = stock.get("enriched", {})
    mf = enriched.get("money_flow", {})
    inflow = parse_float(mf.get("main_net_inflow", "0"))
    turnover = parse_float(stock.get("turnover", "0.1%"))
    if turnover < 0.1:
        turnover = 0.1
    return inflow / turnover


def extract_conviction_raw(stock):
    """Institutional conviction: super_large_net / |main_net_inflow|.
    Values > 0.5 = institutions driving the flow.
    """
    enriched = stock.get("enriched", {})
    mf = enriched.get("money_flow", {})
    super_large = parse_float(mf.get("super_large_net", "0"))
    main_total = parse_float(mf.get("main_net_inflow", "0.01"))
    if main_total < 0.01:
        main_total = 0.01
    return super_large / max(main_total, 0.01)


def extract_consistency_raw(stock):
    """Directional consistency: how aligned are the 4 tiers of capital?
    1.0 = all tiers in same direction. 0.0 = split.
    """
    enriched = stock.get("enriched", {})
    mf = enriched.get("money_flow", {})
    tiers = [
        parse_float(mf.get("super_large_net", "0")),
        parse_float(mf.get("large_net", "0")),
        parse_float(mf.get("medium_net", "0")),
        parse_float(mf.get("small_net", "0")),
    ]
    signs = [1 if v > 0.05 else (-1 if v < -0.05 else 0) for v in tiers]
    pos_count = sum(1 for s in signs if s == 1)
    neg_count = sum(1 for s in signs if s == -1)
    total_nonzero = pos_count + neg_count
    if total_nonzero == 0:
        return 0.5
    alignment = max(pos_count, neg_count) / total_nonzero

    total_abs = sum(abs(v) for v in tiers)
    if total_abs < 1:
        return 0.5
    dominant_abs = max(abs(v) for v in tiers)
    concentration = dominant_abs / total_abs

    return alignment * 0.6 + concentration * 0.4


def compute_confidences(stock, raw_values, all_raws_by_dim):
    """Compute confidence components for this stock."""
    enriched = stock.get("enriched", {})

    mf = enriched.get("money_flow", {})
    has_money_flow = 1 if parse_float(mf.get("main_net_inflow", "0")) != 0 else 0
    rt = enriched.get("real_time", {})
    has_real_time = 1 if parse_float(rt.get("price", 0)) > 0 else 0
    data_checks = [has_money_flow, has_real_time, 1]  # scan data always present
    data_completeness = round(sum(data_checks) / len(data_checks) * 100, 1)

    dim_cvars = []
    for dim, vals in all_raws_by_dim.items():
        if dim not in raw_values:
            continue
        val = raw_values[dim]
        mean = sum(vals) / len(vals) if vals else val
        std = (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5 if vals else 0.1
        if std < 1e-6:
            cv = 0
        else:
            cv = abs(val - mean) / std
        dim_cvars.append(min(cv, 3.0))
    avg_cv = sum(dim_cvars) / len(dim_cvars) if dim_cvars else 1.5
    confidence_interval = max(0.0, min(1.0, 1.0 - avg_cv / 3.0))
    confidence_score = round(confidence_interval * 100, 1)

    overall = round(data_completeness * 0.3 + confidence_score * 0.7, 1)

    return {
        "overall": overall,
        "data_completeness": data_completeness,
        "score_stability": confidence_score,
    }


def compute_scores(pool):
    """Compute percentile-based overnight scores for the entire pool.

    Returns {scored_pool, opportunity_pool_size, ...}
    """
    # Extract raw values
    raws = {}
    for i, s in enumerate(pool):
        raws[i] = {
            "theme": extract_theme_raw(s),
            "capital": extract_capital_raw(s),
            "tail": extract_tail_raw(s),
            "position": extract_position_raw(s),
            "risk": extract_risk_raw(s),
            "intensity": extract_intensity_raw(s),
            "conviction": extract_conviction_raw(s),
            "consistency": extract_consistency_raw(s),
        }

    all_raws = {}
    for dim in ["theme", "capital", "tail", "position", "risk", "intensity", "conviction", "consistency"]:
        all_raws[dim] = [raws[i][dim] for i in raws]

    scored = []
    for i, stock in enumerate(pool):
        r = raws[i]

        theme_pct = percentile_rank(all_raws["theme"], r["theme"])
        capital_pct = percentile_rank(all_raws["capital"], r["capital"])
        tail_pct = percentile_rank(all_raws["tail"], r["tail"])
        position_pct = percentile_rank(all_raws["position"], r["position"])
        risk_pct = percentile_rank(all_raws["risk"], r["risk"], invert=True)

        intensity_pct = percentile_rank(all_raws["intensity"], r["intensity"])
        conviction_pct = percentile_rank(all_raws["conviction"], r["conviction"])
        consistency_pct = percentile_rank(all_raws["consistency"], r["consistency"])

        overnight_score = round(
            theme_pct * WEIGHTS_V1_1["theme_continuity"]
            + capital_pct * WEIGHTS_V1_1["capital_continuity"]
            + tail_pct * WEIGHTS_V1_1["tail_strength"]
            + position_pct * WEIGHTS_V1_1["position_advantage"]
            + intensity_pct * WEIGHTS_V1_1["intensity"]
            + conviction_pct * WEIGHTS_V1_1["conviction"]
            + consistency_pct * WEIGHTS_V1_1["consistency"]
            - (100.0 - risk_pct) * WEIGHTS_V1_1["risk_penalty"],
            1,
        )

        overnight_score = max(overnight_score, 0.0)

        trace = {
            "theme_continuity": {"raw": round(r["theme"], 3), "pct": theme_pct, "weight": WEIGHTS_V1_1["theme_continuity"], "contrib": round(theme_pct * WEIGHTS_V1_1["theme_continuity"], 1)},
            "capital_continuity": {"raw": round(r["capital"], 3), "pct": capital_pct, "weight": WEIGHTS_V1_1["capital_continuity"], "contrib": round(capital_pct * WEIGHTS_V1_1["capital_continuity"], 1)},
            "tail_strength": {"raw": round(r["tail"], 3), "pct": tail_pct, "weight": WEIGHTS_V1_1["tail_strength"], "contrib": round(tail_pct * WEIGHTS_V1_1["tail_strength"], 1)},
            "position_advantage": {"raw": round(r["position"], 3), "pct": position_pct, "weight": WEIGHTS_V1_1["position_advantage"], "contrib": round(position_pct * WEIGHTS_V1_1["position_advantage"], 1)},
            "risk_penalty": {"raw": round(r["risk"], 3), "pct": risk_pct, "weight": WEIGHTS_V1_1["risk_penalty"], "contrib": round((100.0 - risk_pct) * WEIGHTS_V1_1["risk_penalty"], 1)},
            "intensity": {"raw": round(r["intensity"], 3), "pct": intensity_pct, "weight": WEIGHTS_V1_1["intensity"], "contrib": round(intensity_pct * WEIGHTS_V1_1["intensity"], 1)},
            "conviction": {"raw": round(r["conviction"], 3), "pct": conviction_pct, "weight": WEIGHTS_V1_1["conviction"], "contrib": round(conviction_pct * WEIGHTS_V1_1["conviction"], 1)},
            "consistency": {"raw": round(r["consistency"], 3), "pct": consistency_pct, "weight": WEIGHTS_V1_1["consistency"], "contrib": round(consistency_pct * WEIGHTS_V1_1["consistency"], 1)},
        }

        confidence = compute_confidences(stock, r, all_raws)

        stock["overnight_score"] = overnight_score
        stock["score_trace"] = trace
        stock["confidence"] = confidence
        scored.append(stock)

    scored.sort(key=lambda x: x.get("overnight_score", 0), reverse=True)

    for rank_idx, stock in enumerate(scored):
        stock["rank"] = rank_idx + 1
        score = stock.get("overnight_score", 0)
        if score >= 75:
            stock["tier"] = "A"
        elif score >= 60:
            stock["tier"] = "B"
        elif score >= 45:
            stock["tier"] = "C"
        else:
            stock["tier"] = "D"

    return scored


def classify_tier(score, rank, pool_size):
    """Tier by rank percentile (not absolute threshold).
    A = top 10%, B = top 40%, C = top 70%.
    """
    pct = rank / pool_size
    if pct <= 0.10:
        return "A"
    elif pct <= 0.40:
        return "B"
    elif pct <= 0.70:
        return "C"
    else:
        return "D"


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Compute overnight premium scores (V1.1 Percentile)")
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

    print(f"Scoring {len(pool)} stocks (V1.1 Percentile)...", file=sys.stderr)

    scored = compute_scores(pool)

    pool_size = len(scored)

    for s in scored:
        s["tier"] = classify_tier(s["overnight_score"], s["rank"], pool_size)

    opportunity_pool = [
        s for s in scored if s["tier"] in ("A", "B", "C")
    ][:args.opportunity_pool_size]

    leader_watch = [s for s in scored if s["tier"] == "A"][:5]
    premium_candidates = [s for s in opportunity_pool if s["tier"] == "B"]
    early_breakout = [s for s in opportunity_pool if s["tier"] == "C"][:10]

    # Summary stats
    scores = [s["overnight_score"] for s in scored]
    mean_score = round(sum(scores) / len(scores), 1) if scores else 0
    unique_scores = len(set(round(s, 1) for s in scores))

    output = {
        "weights_version": "V1.1_Percentile",
        "pool_size": pool_size,
        "scored_count": len(scored),
        "opportunity_pool_size": len(opportunity_pool),
        "score_stats": {
            "mean": mean_score,
            "min": round(min(scores), 1) if scores else 0,
            "max": round(max(scores), 1) if scores else 0,
            "unique_scores": unique_scores,
        },
        "leader_watch": leader_watch,
        "premium_candidates": premium_candidates,
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
