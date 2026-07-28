#!/usr/bin/env python3
"""Build V1.3 scored, executable, and observation selection pools."""

import argparse
import json
import math
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

from ashare_pilot.market_data.settings import (
    load_stock_money_flow_min_inflow_yuan,
)

WEIGHTS_V1_3 = {
    "source_capital_proxy": 0.18,
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


def percentile_rank(values, value):
    """Return ascending percentile rank 0-100 of value within values.

    Higher raw values receive higher percentiles. Returns 50 for the
    zero-variance case.
    """
    if not values:
        return 50.0
    n = len(values)
    if max(values) - min(values) < 1e-9:
        return 50.0
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


def extract_source_capital_proxy_raw(stock):
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
            if dim in money_dims and not stock_money_flow_available(pool[i]):
                flags[i].append({
                    "dim": dim,
                    "raw": round(raws_by_index[i][dim], 6),
                    "replacement": None,
                    "reason": "money_flow_unavailable_not_imputed",
                    "valid_peer_count": len(clean),
                    "replacement_skipped": "scoreability_required",
                })
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


# Legacy absolute-quality helper retained for focused scoring diagnostics.
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
    has genuine standalone merit before entering the historical candidate set:
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


def compute_scores(pool, regime=None, *, replace_missing=False):
    """Compute percentile-based overnight scores for the entire pool.

    Order: extract raws → optional legacy diagnostic replacement → percentiles
    → I10 contribution scale → sum. Selection Pools always disables replacement.
    """
    regime = regime or {}
    raw_scale = regime.get("i10_capital_scale", 1.0)
    capital_scale = 1.0 if raw_scale is None else float(raw_scale)

    # Extract raw values
    raws = {}
    for i, s in enumerate(pool):
        raws[i] = {
            "source_capital_proxy": extract_source_capital_proxy_raw(s),
            "capital": extract_capital_raw(s),
            "tail": extract_tail_raw(s),
            "position": extract_position_raw(s),
            "risk": extract_risk_raw(s),
            "intensity": extract_intensity_raw(s),
            "conviction": extract_conviction_raw(s),
            "consistency": extract_consistency_raw(s),
            "trend": extract_trend_quality_raw(s),
        }

    if replace_missing:
        skip_mf_i11 = not money_flow_available(pool)
        raws = apply_i11_median_replacement(
            raws, pool, skip_money_flow_dims=skip_mf_i11
        )
    else:
        for stock in pool:
            stock.pop("anomaly_flags", None)
            stock.pop("i11_flagged", None)
            stock.pop("i11_applied", None)

    all_raws = {}
    for dim in ["source_capital_proxy", "capital", "tail", "position", "risk", "intensity", "conviction", "consistency", "trend"]:
        all_raws[dim] = [raws[i][dim] for i in raws]

    scored = []
    for i, stock in enumerate(pool):
        r = raws[i]

        source_capital_proxy_pct = percentile_rank(
            all_raws["source_capital_proxy"], r["source_capital_proxy"]
        )
        capital_pct = percentile_rank(all_raws["capital"], r["capital"])
        tail_pct = percentile_rank(all_raws["tail"], r["tail"])
        position_pct = percentile_rank(all_raws["position"], r["position"])
        risk_pct = percentile_rank(all_raws["risk"], r["risk"])

        intensity_pct = percentile_rank(all_raws["intensity"], r["intensity"])
        conviction_pct = percentile_rank(all_raws["conviction"], r["conviction"])
        consistency_pct = percentile_rank(all_raws["consistency"], r["consistency"])
        trend_pct = percentile_rank(all_raws["trend"], r["trend"])

        W = WEIGHTS_V1_3
        source_capital_proxy_contrib = (
            source_capital_proxy_pct * W["source_capital_proxy"]
        )
        capital_contrib = scaled_contribution(capital_pct, W["capital_continuity"], capital_scale)
        tail_contrib = tail_pct * W["tail_strength"]
        position_contrib = position_pct * W["position_advantage"]
        intensity_contrib = scaled_contribution(intensity_pct, W["intensity"], capital_scale)
        conviction_contrib = scaled_contribution(conviction_pct, W["conviction"], capital_scale)
        consistency_contrib = scaled_contribution(consistency_pct, W["consistency"], capital_scale)
        trend_contrib = trend_pct * W["trend_quality"]
        risk_contrib = risk_pct * W["risk_penalty"]

        overnight_score = round(
            source_capital_proxy_contrib
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
            "source_capital_proxy": {"raw": round(r["source_capital_proxy"], 3), "pct": source_capital_proxy_pct, "weight": W["source_capital_proxy"], "contrib": round(source_capital_proxy_contrib, 1)},
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

    scored.sort(
        key=lambda stock: (
            -float(stock.get("overnight_score", 0)),
            str(stock.get("code", "")),
        )
    )

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

    parser = argparse.ArgumentParser(
        description="Build deterministic intraday selection pools (V1.3)"
    )
    parser.add_argument("input", help="Enriched Compute Pool JSON")
    parser.add_argument(
        "--executable-pool-size",
        type=int,
        default=30,
        help="Executable Pool size (default: 30)",
    )
    parser.add_argument(
        "--observation-pool-size",
        type=int,
        default=30,
        help="Observation Pool size (default: 30)",
    )
    parser.add_argument("--date", help="Trading date (defaults from input path)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("-o", "--output", metavar="FILE", help="Save output to file")
    parser.add_argument("--breadth", help="market_breadth.json for I10/I14 regime")
    parser.add_argument("--indices", help="indices.json for I10/I14 regime")
    args = parser.parse_args(argv)

    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    pool = data.get("compute_pool", [])
    if isinstance(data, list):
        pool = data

    valid_vwap_count = sum(
        1
        for stock in pool
        if (
            is_finite_number(
                stock.get("enriched", {}).get("real_time", {}).get("vwap")
            )
            and parse_float(stock["enriched"]["real_time"]["vwap"]) > 0
        )
    )
    if valid_vwap_count == 0:
        print(
            "[ERROR] VWAP is unavailable for the entire Compute Pool",
            file=sys.stderr,
        )
        return 1

    if args.breadth and args.indices:
        regime = parse_regime_from_files(args.breadth, args.indices)
    else:
        regime = unavailable_regime("breadth_or_indices_not_provided")
        print("[WARN] --breadth/--indices omitted; I10/I14 inactive", file=sys.stderr)
    if not regime.get("available"):
        print(f"[WARN] regime unavailable: {regime.get('warnings')}", file=sys.stderr)

    from ashare_pilot.strategy.intraday_selection import (
        build_selection_pools,
        selection_invariant_errors,
    )

    print(f"Building selection pools for {len(pool)} stocks (V1.3)...", file=sys.stderr)
    output = build_selection_pools(
        pool,
        executable_limit=args.executable_pool_size,
        observation_limit=args.observation_pool_size,
        configured_min_inflow_yuan=load_stock_money_flow_min_inflow_yuan(),
        regime=regime,
    )
    input_path = Path(args.input)
    inferred_date = next(
        (
            part
            for part in reversed(input_path.parts)
            if len(part) == 10 and part[4:5] == "-" and part[7:8] == "-"
        ),
        "",
    )
    output["date"] = args.date or (
        data.get("date", "") if isinstance(data, dict) else ""
    ) or inferred_date
    output["generated_at"] = datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    )
    output["recall_quality"] = (
        data.get("recall_quality", {}) if isinstance(data, dict) else {}
    )
    input_quality = data.get("data_quality", {}) if isinstance(data, dict) else {}
    output["data_quality"] = {
        **(input_quality if isinstance(input_quality, dict) else {}),
        "vwap": {
            "status": "complete" if valid_vwap_count == len(pool) else "partial",
            "valid_stock_count": valid_vwap_count,
            "missing_stock_count": len(pool) - valid_vwap_count,
        },
    }
    errors = selection_invariant_errors(output)
    if errors:
        for error in errors:
            print(f"[ERROR] {error}", file=sys.stderr)
        return 1

    output_str = json.dumps(output, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            f.write(output_str)
        print(f"Saved to {args.output}")
    else:
        print(output_str)
    if output["scored_pool_summary"]["scoreable_count"] == 0:
        print("[ERROR] Scored Pool is empty", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
