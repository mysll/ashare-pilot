"""Deterministic Scoreability, Executability, and dual-pool construction."""

from __future__ import annotations

import copy
import math
from collections import Counter
from typing import Any

from ashare_pilot.mapping.intraday_contract import (
    SELECTION_POOLS_SCHEMA_VERSION,
    execution_state,
)


MONEY_FLOW_FIELDS = (
    "main_net_inflow_yuan",
    "main_net_inflow",
    "super_large_net",
    "large_net",
    "medium_net",
    "small_net",
)
TECHNICAL_NUMBER_FIELDS = ("ma5", "ma10", "ma20")
TECHNICAL_BOLL_ZONES = {"above_ub", "upper_half", "below_mid"}
TECHNICAL_MA_ALIGNMENTS = {"bullish", "mixed", "bearish"}


def finite_number(value: Any) -> bool:
    if isinstance(value, bool) or value is None or value == "" or value == "-":
        return False
    try:
        return math.isfinite(
            float(str(value).replace("%", "").replace("+", "").replace(",", ""))
        )
    except (TypeError, ValueError):
        return False


def number(value: Any) -> float | None:
    if not finite_number(value):
        return None
    return float(str(value).replace("%", "").replace("+", "").replace(",", ""))


def assess_scoreability(stock: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    enriched = stock.get("enriched")
    enriched = enriched if isinstance(enriched, dict) else {}
    real_time = enriched.get("real_time")
    real_time = real_time if isinstance(real_time, dict) else {}
    for field in ("price", "high", "low", "yestclose"):
        if not finite_number(real_time.get(field)):
            reasons.append(f"quote_{field}_missing")
    high = number(real_time.get("high"))
    low = number(real_time.get("low"))
    if high is not None and low is not None and high < low:
        reasons.append("quote_range_contradiction")

    money_flow = enriched.get("money_flow")
    money_flow = money_flow if isinstance(money_flow, dict) else {}
    if money_flow.get("available") is not True:
        reasons.append("money_flow_unavailable")
    else:
        for field in MONEY_FLOW_FIELDS:
            if not finite_number(money_flow.get(field)):
                reasons.append(f"money_flow_{field}_missing")
        yuan = number(money_flow.get("main_net_inflow_yuan"))
        formatted = number(money_flow.get("main_net_inflow"))
        if yuan is not None and formatted is not None:
            expected = formatted * 100_000_000
            tolerance = max(1_500_000, abs(yuan) * 0.02)
            if abs(yuan - expected) > tolerance:
                reasons.append("money_flow_main_inflow_contradiction")

    technicals = stock.get("technicals")
    technicals = technicals if isinstance(technicals, dict) else {}
    if (
        not technicals
        or technicals.get("status") == "no_data"
        or technicals.get("boll_zone") == "no_data"
        or technicals.get("ma_alignment") == "no_data"
    ):
        reasons.append("technicals_no_data")
    else:
        for field in TECHNICAL_NUMBER_FIELDS:
            if not finite_number(technicals.get(field)):
                reasons.append(f"technicals_{field}_missing")
        if technicals.get("boll_zone") not in TECHNICAL_BOLL_ZONES:
            reasons.append("technicals_boll_zone_invalid")
        if technicals.get("ma_alignment") not in TECHNICAL_MA_ALIGNMENTS:
            reasons.append("technicals_ma_alignment_invalid")
        if not isinstance(technicals.get("above_ma5"), bool):
            reasons.append("technicals_above_ma5_missing")

    for field in ("quick_score", "change_pct", "turnover", "volume_ratio"):
        if not finite_number(stock.get(field)):
            reasons.append(f"scoring_input_{field}_missing")
    if not isinstance(stock.get("source_pool"), str) or not stock.get("source_pool"):
        reasons.append("scoring_input_source_pool_missing")

    return {"scoreable": not reasons, "reasons": reasons}


def trend_raw(stock: dict[str, Any]) -> float | None:
    technicals = stock.get("technicals")
    technicals = technicals if isinstance(technicals, dict) else {}
    if (
        technicals.get("boll_zone") not in TECHNICAL_BOLL_ZONES
        or technicals.get("ma_alignment") not in TECHNICAL_MA_ALIGNMENTS
        or not isinstance(technicals.get("above_ma5"), bool)
    ):
        return None
    boll_score = (
        1.0
        if technicals["boll_zone"] == "upper_half"
        else 0.3
        if technicals["boll_zone"] == "below_mid"
        else 0.0
    )
    ma_score = (
        1.0
        if technicals["ma_alignment"] == "bullish" and technicals["above_ma5"]
        else 0.3
    )
    volume_ratio = number(stock.get("volume_ratio"))
    if volume_ratio is None:
        return None
    vol_score = (
        0.5
        if volume_ratio == 0
        else 1.0
        if volume_ratio > 1.5
        else 0.5
        if volume_ratio > 1.0
        else 0.0
    )
    return boll_score * 0.4 + ma_score * 0.4 + vol_score * 0.2


def derive_i14_exemption(
    stock: dict[str, Any],
    regime: dict[str, Any] | None,
) -> str | None:
    regime = regime or {}
    i14_active = bool(regime.get("i14_active"))
    if "i14_active" not in regime and finite_number(regime.get("up_ratio_pct")):
        i14_active = float(regime["up_ratio_pct"]) < 35
    if not i14_active:
        return None
    real_time = stock.get("enriched", {}).get("real_time", {})
    price = number(real_time.get("price"))
    vwap = number(real_time.get("vwap"))
    quick_score = number(stock.get("quick_score"))
    if price is None or vwap is None or vwap <= 0 or price >= vwap:
        return None
    deviation_pct = (vwap - price) / vwap * 100
    if quick_score is not None and deviation_pct < 3 and quick_score >= 70:
        return "watch"
    if quick_score is not None and deviation_pct < 5 and quick_score >= 80:
        return "cautious_hold"
    return None


def assess_execution_eligibility(
    stock: dict[str, Any],
    configured_min_inflow_yuan: int | float,
) -> dict[str, Any]:
    reasons: list[str] = []
    if stock.get("score_status") != "scored":
        reasons.append("unscored")

    state = stock.get("execution_state")
    if not isinstance(state, dict) or state.get("eligible") is not True:
        reason = state.get("exclusion_reason") if isinstance(state, dict) else None
        reasons.append(reason or "execution_state_ineligible")

    money_flow = stock.get("enriched", {}).get("money_flow", {})
    inflow = number(money_flow.get("main_net_inflow_yuan"))
    if inflow is None:
        reasons.append("money_flow_main_net_inflow_yuan_missing")
    elif inflow < configured_min_inflow_yuan:
        reasons.append("money_flow_below_configured_minimum")

    raw = trend_raw(stock)
    if raw is None:
        reasons.append("trend_data_unavailable")
    elif raw < 0.3:
        reasons.append("trend_below_floor")

    real_time = stock.get("enriched", {}).get("real_time", {})
    price = number(real_time.get("price"))
    vwap = number(real_time.get("vwap"))
    exemption = stock.get("i14_exemption")
    if vwap is None or vwap <= 0:
        reasons.append("vwap_missing")
    elif price is None:
        reasons.append("quote_price_missing")
    elif exemption == "watch":
        reasons.append("i14_watch")
    elif price < vwap and exemption != "cautious_hold":
        reasons.append("price_below_vwap")

    return {"eligible": not reasons, "reasons": reasons}


def _score_stats(scored: list[dict[str, Any]]) -> dict[str, Any]:
    scores = [float(stock["overnight_score"]) for stock in scored]
    if not scores:
        return {}
    return {
        "mean": round(sum(scores) / len(scores), 1),
        "min": round(min(scores), 1),
        "max": round(max(scores), 1),
        "unique_scores": len(set(scores)),
    }


def build_selection_pools(
    compute_pool: list[dict[str, Any]],
    *,
    executable_limit: int = 30,
    observation_limit: int = 30,
    configured_min_inflow_yuan: int | float,
    regime: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build mutually exclusive pools without proxy-scoring missing data."""
    from ashare_pilot.strategy._commands.overnight import score as scoring

    stocks = copy.deepcopy(compute_pool)
    scoreable: list[dict[str, Any]] = []
    unscored: list[dict[str, Any]] = []
    for stock in stocks:
        stock["execution_state"] = execution_state(stock)
        gate = assess_scoreability(stock)
        if gate["scoreable"]:
            stock["score_status"] = "scored"
            scoreable.append(stock)
        else:
            stock["score_status"] = "unscored"
            stock["observation_reasons"] = gate["reasons"]
            stock["primary_observation_reason"] = gate["reasons"][0]
            for field in ("overnight_score", "rank", "rank_tier", "tier"):
                stock.pop(field, None)
            unscored.append(stock)

    scored = scoring.compute_scores(scoreable, regime=regime, replace_missing=False)
    scored.sort(
        key=lambda stock: (-float(stock["overnight_score"]), stock["code"])
    )
    executable_candidates: list[dict[str, Any]] = []
    scored_observations: list[dict[str, Any]] = []
    for stock in scored:
        stock["trend_raw"] = trend_raw(stock)
        stock["i14_exemption"] = derive_i14_exemption(stock, regime)
        if stock["i14_exemption"] is None:
            stock.pop("i14_exemption", None)
        eligibility = assess_execution_eligibility(
            stock,
            configured_min_inflow_yuan,
        )
        stock["execution_eligibility"] = eligibility
        if eligibility["eligible"]:
            executable_candidates.append(stock)
        else:
            stock["observation_reasons"] = eligibility["reasons"]
            stock["primary_observation_reason"] = eligibility["reasons"][0]
            scored_observations.append(stock)

    executable_candidates.sort(
        key=lambda stock: (-float(stock["overnight_score"]), stock["code"])
    )
    scored_observations.sort(
        key=lambda stock: (-float(stock["overnight_score"]), stock["code"])
    )
    unscored.sort(
        key=lambda stock: (
            -(number(stock.get("quick_score")) or 0),
            stock.get("code", ""),
        )
    )
    all_observations = scored_observations + unscored
    reason_counts = Counter(
        reason
        for stock in all_observations
        for reason in stock.get("observation_reasons", [])
    )
    executable_pool = executable_candidates[:executable_limit]
    observation_pool = all_observations[:observation_limit]
    tier_counts = Counter(stock["rank_tier"] for stock in scored)

    return {
        "schema_version": SELECTION_POOLS_SCHEMA_VERSION,
        "scoring_version": "V1.3_SelectionPools",
        "scoring_policy_version": "selection_pools_v1",
        "configured_limits": {
            "compute_pool_size": len(stocks),
            "executable_pool_size": executable_limit,
            "observation_pool_size": observation_limit,
            "money_flow_min_inflow_yuan": configured_min_inflow_yuan,
            "trend_raw_floor": 0.3,
        },
        "regime_snapshot": regime or {},
        "scored_pool_summary": {
            "scoreable_count": len(scored),
            "unscoreable_count": len(unscored),
            "score_stats": _score_stats(scored),
            "rank_tier_counts": dict(sorted(tier_counts.items())),
        },
        "pool_summary": {
            "executable_count": len(executable_pool),
            "observation_total_before_limit": len(all_observations),
            "observation_count": len(observation_pool),
            "observation_truncated_count": max(
                0, len(all_observations) - len(observation_pool)
            ),
            "observation_reason_counts": dict(sorted(reason_counts.items())),
            "no_executable_candidates": not executable_pool,
        },
        "executable_pool": executable_pool,
        "observation_pool": observation_pool,
    }


def selection_invariant_errors(document: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if document.get("schema_version") != SELECTION_POOLS_SCHEMA_VERSION:
        errors.append(
            f"schema_version must be {SELECTION_POOLS_SCHEMA_VERSION}"
        )
    executable = document.get("executable_pool")
    observation = document.get("observation_pool")
    if not isinstance(executable, list):
        errors.append("executable_pool must be an array")
        executable = []
    if not isinstance(observation, list):
        errors.append("observation_pool must be an array")
        observation = []
    executable_codes = {
        stock.get("code") for stock in executable if isinstance(stock, dict)
    }
    observation_codes = {
        stock.get("code") for stock in observation if isinstance(stock, dict)
    }
    overlap = sorted(code for code in executable_codes & observation_codes if code)
    if overlap:
        errors.append(f"pool code overlap: {', '.join(overlap)}")
    limits = document.get("configured_limits", {})
    if len(executable) > limits.get("executable_pool_size", 30):
        errors.append("executable_pool exceeds configured limit")
    if len(observation) > limits.get("observation_pool_size", 30):
        errors.append("observation_pool exceeds configured limit")

    for index, stock in enumerate(executable):
        prefix = f"executable_pool[{index}]"
        if stock.get("score_status") != "scored":
            errors.append(f"{prefix}.score_status must be scored")
        derived_state = execution_state(stock)
        if stock.get("execution_state") != derived_state:
            errors.append(f"{prefix}.execution_state must match deterministic quote state")
        if derived_state.get("eligible") is not True:
            errors.append(f"{prefix}.execution_state.eligible must be true")
        gate = assess_scoreability(stock)
        if gate["scoreable"] is not True:
            errors.append(f"{prefix} must remain scoreable: {gate['reasons']}")
        candidate = copy.deepcopy(stock)
        candidate["execution_state"] = derived_state
        derived_eligibility = assess_execution_eligibility(
            candidate,
            limits.get("money_flow_min_inflow_yuan", 0),
        )
        if stock.get("execution_eligibility") != derived_eligibility:
            errors.append(
                f"{prefix}.execution_eligibility must match deterministic gates"
            )
        if derived_eligibility.get("eligible") is not True:
            errors.append(f"{prefix}.execution_eligibility.eligible must be true")
        if stock.get("tier") != stock.get("rank_tier"):
            errors.append(f"{prefix}.tier must equal rank_tier")
    for index, stock in enumerate(observation):
        prefix = f"observation_pool[{index}]"
        if stock.get("execution_state") != execution_state(stock):
            errors.append(f"{prefix}.execution_state must match deterministic quote state")
        if not stock.get("observation_reasons"):
            errors.append(f"{prefix}.observation_reasons must be non-empty")
        if stock.get("primary_observation_reason") not in stock.get(
            "observation_reasons", []
        ):
            errors.append(
                f"{prefix}.primary_observation_reason must be in observation_reasons"
            )
        if stock.get("score_status") == "unscored":
            for field in ("overnight_score", "rank", "rank_tier", "tier"):
                if stock.get(field) is not None:
                    errors.append(f"{prefix}.{field} must be null or absent")
    return errors
