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
import statistics
import sys
from pathlib import Path


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

WEIGHTS_V1_2 = {
    "theme_continuity": 0.18,
    "capital_continuity": 0.18,
    "tail_strength": 0.14,
    "position_advantage": 0.09,
    "risk_penalty": 0.10,
    "intensity": 0.09,
    "conviction": 0.09,
    "consistency": 0.05,
    "trend_quality": 0.08,
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


def extract_trend_quality_raw(stock):
    """Trend quality from Bollinger zone + MA alignment + volume ratio.
    1.0 = bullish healthy trend (upper_half + bullish MAs + vol_ratio>1.5).
    """
    tech = stock.get("technicals", {})
    if not tech or tech.get("boll_zone") == "no_data":
        return 0.5

    boll_zone = tech.get("boll_zone", "below_mid")
    ma_alignment = tech.get("ma_alignment", "mixed")
    above_ma5 = tech.get("above_ma5", False)

    boll_score = 1.0 if boll_zone == "upper_half" else (0.3 if boll_zone == "below_mid" else 0.0)
    ma_score = 1.0 if (ma_alignment == "bullish" and above_ma5) else 0.3
    vol_ratio = parse_float(stock.get("volume_ratio", "1.0"))
    if vol_ratio == 0.0:
        vol_score = 0.5
    else:
        vol_score = 1.0 if vol_ratio > 1.5 else (0.5 if vol_ratio > 1.0 else 0.0)

    return boll_score * 0.4 + ma_score * 0.4 + vol_score * 0.2


def apply_quality_filter(pool, regime=None):
    """Absolute eligibility floor — removes ONLY genuinely disqualifying stocks.

    Hard exclusions:
        1. No real-time data (price <= 0)
        2. Price below intraday VWAP (unless I14 exemption applies)

    I14 (weak market, up_ratio_pct < 35): micro VWAP deviation may pass with
    a tradeability ceiling tag (watch / cautious_hold). Requires numeric
    quick_score; no invented proxy.

    Returns (passed, filtered, quality_stats) where quality_stats includes
    vwap_missing_count, i14_applied_count, i14_skipped_no_quick_score.
    """
    regime = regime or {}
    i14_active = bool(regime.get("i14_active"))
    if "i14_active" not in regime and is_finite_number(regime.get("up_ratio_pct")):
        i14_active = float(regime["up_ratio_pct"]) < 35

    passed = []
    filtered = []
    vwap_missing_count = 0
    i14_applied_count = 0
    i14_skipped_no_quick_score = 0

    for s in pool:
        s.pop("i14_exemption", None)
        enriched = s.get("enriched", {})
        rt = enriched.get("real_time", {})
        price = parse_float(rt.get("price", 0))
        vwap = parse_float(rt.get("vwap", 0))
        reasons = []

        if price <= 0:
            reasons.append("无实时行情数据")
        elif vwap > 0 and price < vwap:
            deviation_pct = (vwap - price) / vwap * 100.0
            qs_raw = s.get("quick_score")
            has_qs = is_finite_number(qs_raw)
            quick_score = float(qs_raw) if has_qs else None
            exempt = None
            if i14_active:
                if not has_qs:
                    i14_skipped_no_quick_score += 1
                elif deviation_pct < 3 and quick_score >= 70:
                    exempt = "watch"
                elif deviation_pct < 5 and quick_score >= 80:
                    exempt = "cautious_hold"
            if exempt:
                s["i14_exemption"] = exempt
                i14_applied_count += 1
            else:
                reasons.append("价格跌破当日成交均价线")
        elif vwap <= 0:
            vwap_missing_count += 1

        if reasons:
            s["exclusion_source"] = "quality-filter"
            s["exclusion_reason"] = "; ".join(reasons)
            filtered.append(s)
        else:
            passed.append(s)

    stats = {
        "vwap_missing_count": vwap_missing_count,
        "i14_applied_count": i14_applied_count,
        "i14_skipped_no_quick_score": i14_skipped_no_quick_score,
    }
    return passed, filtered, stats


def is_finite_number(val) -> bool:
    if isinstance(val, bool) or val is None or val == "" or val == "-":
        return False
    try:
        x = float(str(val).replace("%", "").replace("+", "").replace(",", ""))
        return math.isfinite(x)
    except (TypeError, ValueError):
        return False


def is_present_number(obj: dict, key: str) -> bool:
    if not isinstance(obj, dict) or key not in obj:
        return False
    return is_finite_number(obj.get(key))


def unavailable_regime(reason: str) -> dict:
    return {
        "available": False,
        "up_ratio_pct": None,
        "sz_change_pct": None,
        "i10_active": False,
        "i14_active": False,
        "i10_capital_scale": 1.0,
        "warnings": [reason],
    }


def i10_capital_scale(up_ratio_pct: float, sz_change_pct: float) -> float:
    if up_ratio_pct >= 40 or sz_change_pct >= 0:
        return 1.0
    if up_ratio_pct >= 20:
        return 0.5
    if up_ratio_pct >= 10:
        return 0.25
    return 0.0


def parse_required_percent(val) -> float:
    if not is_finite_number(val):
        raise ValueError("percent_missing")
    return float(str(val).replace("%", "").replace("+", "").replace(",", ""))


def parse_regime_from_files(breadth_path, indices_path) -> dict:
    """Load regime_snapshot from market_breadth.json + indices.json."""
    try:
        with open(breadth_path, "r", encoding="utf-8") as f:
            breadth = json.load(f)
        with open(indices_path, "r", encoding="utf-8") as f:
            indices = json.load(f)
        if not isinstance(breadth, dict):
            return unavailable_regime("market_breadth_not_object")
        if breadth.get("partial") is True:
            return unavailable_regime("market_breadth_partial")
        if is_finite_number(breadth.get("up_ratio")):
            up_ratio_pct = float(breadth["up_ratio"])
            if not 0.0 <= up_ratio_pct <= 100.0:
                return unavailable_regime("market_breadth_up_ratio_out_of_range")
        else:
            for key in ("up_count", "down_count", "flat_count"):
                if not is_finite_number(breadth.get(key)):
                    return unavailable_regime(f"market_breadth_missing_{key}")
            up = float(breadth["up_count"])
            down = float(breadth["down_count"])
            flat = float(breadth["flat_count"])
            if min(up, down, flat) < 0:
                return unavailable_regime("market_breadth_negative_count")
            total = up + down + flat
            if total <= 0:
                return unavailable_regime("market_breadth_total_zero")
            up_ratio_pct = up / total * 100.0

        if not isinstance(indices, list):
            return unavailable_regime("indices_not_array")
        sz = next((row for row in indices if isinstance(row, dict) and row.get("code") == "sz399001"), None)
        if sz is None:
            return unavailable_regime("sz399001_missing")
        sz_change_pct = parse_required_percent(sz.get("percent"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return unavailable_regime(f"regime_parse_error:{type(exc).__name__}")

    scale = i10_capital_scale(up_ratio_pct, sz_change_pct)
    return {
        "available": True,
        "up_ratio_pct": round(up_ratio_pct, 2),
        "sz_change_pct": round(sz_change_pct, 2),
        "i10_active": scale < 1.0,
        "i14_active": up_ratio_pct < 35,
        "i10_capital_scale": scale,
        "warnings": [],
    }


def detect_dim_anomaly(dim: str, raw: float, stock: dict):
    """Return reason if missing/contradictory source data; raw=0 alone is not anomaly."""
    enriched = stock.get("enriched", {}) or {}
    mf = enriched.get("money_flow", {}) or {}
    rt = enriched.get("real_time", {}) or {}
    turnover = parse_float(stock.get("turnover", "0%"))

    if dim == "conviction" and not is_present_number(mf, "super_large_net"):
        return "missing_super_large_net"
    if dim in ("intensity", "capital") and not is_present_number(mf, "main_net_inflow"):
        return "missing_main_net_inflow"
    if dim == "consistency" and any(
        not is_present_number(mf, key)
        for key in ("super_large_net", "large_net", "medium_net", "small_net")
    ):
        return "partial_money_flow_tiers"
    if dim == "tail":
        high = parse_float(rt.get("high", 0))
        low = parse_float(rt.get("low", 0))
        price = parse_float(rt.get("price", 0))
        if price > 0 and turnover > 20 and high <= low:
            return "intraday_range_contradiction"
    return None


def apply_i11_median_replacement(raws_by_index: dict, pool: list, skip_money_flow_dims: bool = False) -> dict:
    """Replace missing/contradictory dim raws with valid-peer median (>=3 peers)."""
    if not raws_by_index:
        return {}
    money_dims = {"capital", "intensity", "conviction", "consistency"}
    dims = list(next(iter(raws_by_index.values())).keys())
    adjusted = {i: dict(raws_by_index[i]) for i in raws_by_index}
    flags = {i: [] for i in raws_by_index}

    for dim in dims:
        if skip_money_flow_dims and dim in money_dims:
            continue
        clean = []
        for i in raws_by_index:
            reason = detect_dim_anomaly(dim, raws_by_index[i][dim], pool[i])
            if not reason:
                clean.append(raws_by_index[i][dim])
        med = statistics.median(clean) if len(clean) >= 3 else None
        for i in raws_by_index:
            reason = detect_dim_anomaly(dim, raws_by_index[i][dim], pool[i])
            if not reason:
                continue
            if med is not None:
                flags[i].append({
                    "dim": dim,
                    "raw": round(raws_by_index[i][dim], 6),
                    "replacement": round(med, 6),
                    "reason": reason,
                    "valid_peer_count": len(clean),
                })
                adjusted[i][dim] = med
            else:
                flags[i].append({
                    "dim": dim,
                    "raw": round(raws_by_index[i][dim], 6),
                    "replacement": None,
                    "reason": reason,
                    "valid_peer_count": len(clean),
                    "replacement_skipped": "insufficient_valid_peers",
                })

    for i in raws_by_index:
        pool[i]["anomaly_flags"] = flags[i]
        pool[i]["i11_flagged"] = bool(flags[i])
        pool[i]["i11_applied"] = any(f.get("replacement") is not None for f in flags[i])
    return adjusted


def scaled_contribution(percentile: float, weight: float, scale: float) -> float:
    return percentile * weight * scale


# Absolute quality floor for opportunity-pool entry.
# Fetched main_net_inflow (亿) must be net positive; the configurable minimum
# is enforced by adaptive pagination before this generic floor is evaluated.
FLOOR_MIN_INFLOW = 0.0
FLOOR_MIN_TREND = 0.3


def stock_money_flow_available(stock):
    """Distinguish a fetched zero value from a stock absent in partial pages."""
    mf = stock.get("enriched", {}).get("money_flow", {})
    if not isinstance(mf, dict):
        return False
    if "available" in mf:
        return mf.get("available") is True
    return is_present_number(mf, "main_net_inflow")


def stock_money_flow_below_minimum(stock):
    """True when adaptive pagination intentionally filtered this stock."""
    mf = stock.get("enriched", {}).get("money_flow", {})
    return isinstance(mf, dict) and mf.get("minimum_filter_applied") is True


def money_flow_available(pool):
    """True if stock-level money flow data is present for this pool.

    The East Money money-flow endpoint occasionally returns nothing (after
    hours, cookie expiry, API change), leaving main_net_inflow == 0 for the
    whole pool. In that case the inflow floor must be SKIPPED rather than
    rejecting every stock — otherwise a data outage silently empties the pool.
    """
    return any(stock_money_flow_available(s) for s in pool)


def passes_absolute_floor(
    stock,
    check_inflow=True,
    require_minimum_inflow=False,
):
    """Absolute quality gate, independent of percentile rank.

    Percentile scoring is RELATIVE — on a weak day the 'best of the worst'
    still ranks high and would emit a buy signal. This gate ensures a stock
    has genuine standalone merit before entering the opportunity pool:
        - main force capital is net positive (real money committed)
        - trend quality is not in its worst state

    When check_inflow is False (money-flow data unavailable pool-wide), the
    inflow condition is skipped so a data outage does not empty the pool.

    Returns (ok: bool, reason: str). reason is "" when ok.
    """
    enriched = stock.get("enriched", {})
    mf = enriched.get("money_flow", {})
    inflow = parse_float(mf.get("main_net_inflow", "0"))
    trend_raw = extract_trend_quality_raw(stock)

    reasons = []
    if require_minimum_inflow:
        reasons.append("主力资金净流入未达到配置最低额度")
    elif check_inflow and inflow <= FLOOR_MIN_INFLOW:
        reasons.append("主力资金净流出")
    if trend_raw < FLOOR_MIN_TREND:
        reasons.append("趋势质量不达标")

    return (not reasons), "; ".join(reasons)



def compute_confidences(stock, raw_values, all_raws_by_dim):
    """Compute confidence components for this stock."""
    enriched = stock.get("enriched", {})

    mf = enriched.get("money_flow", {})
    has_money_flow = 1 if stock_money_flow_available(stock) else 0
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


def compute_scores(pool, regime=None):
    """Compute percentile-based overnight scores for the entire pool.

    Order: extract raws → I11 median replace → percentiles → I10 contrib scale → sum.
    """
    regime = regime or {}
    raw_scale = regime.get("i10_capital_scale", 1.0)
    capital_scale = 1.0 if raw_scale is None else float(raw_scale)

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
            "trend": extract_trend_quality_raw(s),
        }

    skip_mf_i11 = not money_flow_available(pool)
    raws = apply_i11_median_replacement(raws, pool, skip_money_flow_dims=skip_mf_i11)

    all_raws = {}
    for dim in ["theme", "capital", "tail", "position", "risk", "intensity", "conviction", "consistency", "trend"]:
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
        trend_pct = percentile_rank(all_raws["trend"], r["trend"])

        W = WEIGHTS_V1_2
        theme_contrib = theme_pct * W["theme_continuity"]
        capital_contrib = scaled_contribution(capital_pct, W["capital_continuity"], capital_scale)
        tail_contrib = tail_pct * W["tail_strength"]
        position_contrib = position_pct * W["position_advantage"]
        intensity_contrib = scaled_contribution(intensity_pct, W["intensity"], capital_scale)
        conviction_contrib = scaled_contribution(conviction_pct, W["conviction"], capital_scale)
        consistency_contrib = scaled_contribution(consistency_pct, W["consistency"], capital_scale)
        trend_contrib = trend_pct * W["trend_quality"]
        risk_contrib = (100.0 - risk_pct) * W["risk_penalty"]

        overnight_score = round(
            theme_contrib
            + capital_contrib
            + tail_contrib
            + position_contrib
            + intensity_contrib
            + conviction_contrib
            + consistency_contrib
            + trend_contrib
            - risk_contrib,
            1,
        )

        overnight_score = max(overnight_score, 0.0)

        trace = {
            "theme_continuity": {"raw": round(r["theme"], 3), "pct": theme_pct, "weight": W["theme_continuity"], "contrib": round(theme_contrib, 1)},
            "capital_continuity": {"raw": round(r["capital"], 3), "pct": capital_pct, "weight": W["capital_continuity"], "scale": capital_scale, "contrib": round(capital_contrib, 1)},
            "tail_strength": {"raw": round(r["tail"], 3), "pct": tail_pct, "weight": W["tail_strength"], "contrib": round(tail_contrib, 1)},
            "position_advantage": {"raw": round(r["position"], 3), "pct": position_pct, "weight": W["position_advantage"], "contrib": round(position_contrib, 1)},
            "risk_penalty": {"raw": round(r["risk"], 3), "pct": risk_pct, "weight": W["risk_penalty"], "contrib": round(risk_contrib, 1)},
            "intensity": {"raw": round(r["intensity"], 3), "pct": intensity_pct, "weight": W["intensity"], "scale": capital_scale, "contrib": round(intensity_contrib, 1)},
            "conviction": {"raw": round(r["conviction"], 3), "pct": conviction_pct, "weight": W["conviction"], "scale": capital_scale, "contrib": round(conviction_contrib, 1)},
            "consistency": {"raw": round(r["consistency"], 3), "pct": consistency_pct, "weight": W["consistency"], "scale": capital_scale, "contrib": round(consistency_contrib, 1)},
            "trend_quality": {"raw": round(r["trend"], 3), "pct": trend_pct, "weight": W["trend_quality"], "contrib": round(trend_contrib, 1)},
        }

        confidence = compute_confidences(stock, r, all_raws)

        stock["overnight_score"] = overnight_score
        stock["score_trace"] = trace
        stock["confidence"] = confidence
        scored.append(stock)

    scored.sort(key=lambda x: x.get("overnight_score", 0), reverse=True)

    pool_size = len(scored)
    for rank_idx, stock in enumerate(scored):
        rank = rank_idx + 1
        stock["rank"] = rank
        stock["absolute_score"] = stock.get("overnight_score", 0)
        rank_tier = classify_rank_tier(rank, pool_size)
        stock["rank_tier"] = rank_tier
        stock["tier"] = rank_tier  # compatibility alias == rank_tier only
        stock["rank_tier_rule"] = "rank_percentile_v1"

    return scored


def classify_rank_tier(rank, pool_size):
    """Rank tier by pool rank percentile (not absolute score, not tradeability).
    A = top 10%, B = top 40%, C = top 70%, D = rest.
    """
    if pool_size <= 0:
        return "D"
    pct = rank / pool_size
    if pct <= 0.10:
        return "A"
    elif pct <= 0.40:
        return "B"
    elif pct <= 0.70:
        return "C"
    else:
        return "D"


def classify_tier(score, rank, pool_size):
    """Backward-compatible alias; ignores absolute score, uses rank only."""
    return classify_rank_tier(rank, pool_size)


def main(argv=None):
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
    parser.add_argument("--breadth", help="market_breadth.json for I10/I14 regime")
    parser.add_argument("--indices", help="indices.json for I10/I14 regime")
    args = parser.parse_args(argv)

    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    pool = data.get("compute_pool", [])
    input_data_quality = data.get("data_quality", {}) if isinstance(data, dict) else {}
    if isinstance(data, list):
        pool = data

    if args.breadth and args.indices:
        regime = parse_regime_from_files(args.breadth, args.indices)
    else:
        regime = unavailable_regime("breadth_or_indices_not_provided")
        print("[WARN] --breadth/--indices omitted; I10/I14 inactive", file=sys.stderr)
    if not regime.get("available"):
        print(f"[WARN] regime unavailable: {regime.get('warnings')}", file=sys.stderr)

    print(f"Scoring {len(pool)} stocks (V1.2 TrendQuality)...", file=sys.stderr)

    pool, quality_filtered, quality_stats = apply_quality_filter(pool, regime=regime)
    vwap_missing_count = quality_stats["vwap_missing_count"]
    vwap_skip_note = ""
    if vwap_missing_count > 0:
        vwap_skip_note = f" (VWAP无数据跳过过滤: {vwap_missing_count}只)"
    if quality_stats["i14_applied_count"]:
        vwap_skip_note += f" (I14豁免: {quality_stats['i14_applied_count']}只)"
    print(f"Quality filter: {len(pool)} passed, {len(quality_filtered)} filtered{vwap_skip_note}", file=sys.stderr)

    scored = compute_scores(pool, regime=regime)

    pool_size = len(scored)

    # Absolute quality floor: percentile rank is relative, so gate on
    # standalone merit before a stock can enter the opportunity pool.
    # If money-flow data is unavailable pool-wide, skip the inflow condition
    # so a data outage does not silently empty the pool.
    money_quality = (
        input_data_quality.get("money_flow", {})
        if isinstance(input_data_quality, dict)
        and isinstance(input_data_quality.get("money_flow"), dict)
        else {}
    )
    threshold_filter_active = money_quality.get("fetch_status") == "threshold_reached"
    mf_available = money_flow_available(scored)
    floor_rejected = []
    for s in scored:
        below_minimum = (
            threshold_filter_active and stock_money_flow_below_minimum(s)
        )
        ok, reason = passes_absolute_floor(
            s,
            check_inflow=(
                mf_available
                and stock_money_flow_available(s)
                and not below_minimum
            ),
            require_minimum_inflow=below_minimum,
        )
        s["floor_pass"] = ok
        if not ok:
            s["floor_reason"] = reason
            floor_rejected.append(s)

    opportunity_pool = [
        s for s in scored
        if s["tier"] in ("A", "B", "C") and s.get("floor_pass", False)
    ][:args.opportunity_pool_size]

    # Empty-pool fallback: never silently return nothing. If the floor + tier
    # gate cleared everyone, surface the top-ranked tier-A/B/C candidates with
    # an explicit warning so the Reasoning layer can decide to stand aside.
    quality_stats["money_flow"] = money_quality
    money_status = money_quality.get("status")
    if threshold_filter_active:
        threshold_yuan = money_quality.get("min_main_inflow_yuan")
        threshold_wan = (
            round(float(threshold_yuan) / 10_000)
            if isinstance(threshold_yuan, (int, float))
            else "未知"
        )
        pool_warning = (
            f"主力资金流按配置最低净流入 {threshold_wan} 万元过滤："
            f"覆盖 {money_quality.get('matched_stock_count', 0)}/"
            f"{money_quality.get('requested_stock_count', len(scored))} 只；"
            "达到阈值边界后主动停止分页，未覆盖股票不进入可执行机会池"
        )
    elif money_status == "partial":
        coverage = money_quality.get("coverage_pct")
        pool_warning = (
            "主力资金流数据不完整："
            f"覆盖 {money_quality.get('matched_stock_count', 0)}/"
            f"{money_quality.get('requested_stock_count', len(scored))} 只"
            f"（{coverage if coverage is not None else '未知'}%），"
            f"已保留前 {money_quality.get('pages_fetched', 0)} 页成功数据；"
            "未覆盖股票不执行资金流地板，不按净流入为 0 处理"
        )
    elif not mf_available:
        pool_warning = "主力资金流数据整体缺失，已跳过资金地板检查——评分可信度下降，Reasoning层需谨慎"
    else:
        pool_warning = ""
    if not opportunity_pool:
        tier_candidates = [
            s for s in scored
            if s["tier"] in ("A", "B", "C")
            and not stock_money_flow_below_minimum(s)
        ]
        if tier_candidates:
            degrade_note = (
                "绝对质量地板过滤后无合格标的；以下为降级候选(未通过地板)，"
                "仅供参考，Reasoning层应倾向观望"
            )
            pool_warning = f"{pool_warning}；{degrade_note}" if pool_warning else degrade_note
            opportunity_pool = [dict(s, degraded=True) for s in tier_candidates][:args.opportunity_pool_size]
        else:
            no_pool_note = "无任何A/B/C档标的，建议全部观望"
            pool_warning = f"{pool_warning}；{no_pool_note}" if pool_warning else no_pool_note

    leader_watch = [s for s in opportunity_pool if s["tier"] == "A"][:5]
    premium_candidates = [s for s in opportunity_pool if s["tier"] == "B"]
    early_breakout = [s for s in opportunity_pool if s["tier"] == "C"][:10]

    # Summary stats
    scores = [s["overnight_score"] for s in scored]
    mean_score = round(sum(scores) / len(scores), 1) if scores else 0
    unique_scores = len(set(round(s, 1) for s in scores))

    output = {
        "weights_version": "V1.2_TrendQuality",
        "scoring_policy_version": "convergence_v1",
        "pool_size": pool_size,
        "scored_count": len(scored),
        "quality_filtered_count": len(quality_filtered),
        "vwap_missing_count": vwap_missing_count,
        "i14_applied_count": quality_stats["i14_applied_count"],
        "i14_skipped_no_quick_score": quality_stats["i14_skipped_no_quick_score"],
        "data_quality_summary": quality_stats,
        "regime_snapshot": regime,
        "money_flow_available": mf_available,
        "quality_filtered": quality_filtered,
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
        "floor_rejected_count": len(floor_rejected),
        "pool_warning": pool_warning,
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
