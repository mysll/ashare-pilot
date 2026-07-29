"""Hard class and position caps for operation-guide snapshots."""

from __future__ import annotations

from datetime import datetime, time
from typing import Any

from ashare_pilot.position_tier import POSITION_TIERS, lower_position_tier


CLASS_RANK = {"D": 0, "C": 1, "B": 2, "A": 3}


def cap_class(value: str, maximum: str) -> str:
    return value if CLASS_RANK[value] <= CLASS_RANK[maximum] else maximum


def compute_mechanical_decision(
    strategy: dict[str, Any],
    signals: dict[str, Any],
    market: dict[str, Any],
    snapshot_time: datetime,
) -> dict[str, Any]:
    reasons: list[str] = []
    hard_blocks: list[str] = []
    direction = strategy.get("direction")
    profile = strategy.get("profile") or strategy.get("entry_profile")
    warnings = signals.get("data_warning") or []
    severe_warnings = {
        "quote_error", "invalid_price", "intraday_completed_bar_missing",
        "first_bar_missing", "invalid_code",
    }
    action = market.get("global_action")
    preopen = strategy.get("preopen_plan") if isinstance(strategy.get("preopen_plan"), dict) else {}
    morning_tier = strategy.get("position_tier")
    if morning_tier not in POSITION_TIERS:
        raise ValueError(f"invalid position_tier: {morning_tier!r}")

    def plan_time(key: str, fallback: time) -> time:
        value = preopen.get(key)
        if isinstance(value, str):
            try:
                return time.fromisoformat(value)
            except ValueError as exc:
                if strategy.get("strategy_schema_version") == "daily_strategy.v3":
                    raise ValueError(f"invalid v3 preopen_plan.{key}: {value!r}") from exc
        return fallback

    earliest = plan_time("earliest_entry_time", time(9, 35, 5))
    latest_time = plan_time("latest_entry_time", time(10, 0))

    if (
        direction in {"看空", "中性"}
        or profile == "暂不参与"
        or preopen.get("decision") == "WATCH_ONLY"
        or morning_tier == "WATCH_ONLY"
    ):
        hard_blocks.append("morning_strategy_not_buyable")
    if any(item in severe_warnings for item in warnings):
        hard_blocks.append("data_warning")
    if signals.get("high_open_fade") and signals.get("first_bar", {}).get("red_flag"):
        hard_blocks.append("high_open_fade_with_first_bar_red")

    if hard_blocks:
        mechanical = maximum = "D"
    else:
        maximum = "A"
        if action == "NO_NEW_BUY":
            maximum = "C"
            reasons.append("global_no_new_buy")
        elif action == "WAIT" or snapshot_time.time() < earliest:
            maximum = "B"
            reasons.append("market_or_time_wait")
        elif action == "SELECTIVE":
            reasons.append("selective_market")
        if warnings:
            maximum = cap_class(maximum, "B")
            reasons.append("non_severe_data_warning")
        if snapshot_time.time() > latest_time:
            maximum = cap_class(maximum, "C")
            reasons.append("entry_window_expired")

        first = signals.get("first_bar", {})
        latest = signals.get("latest_completed_bar", {})
        price_confirmed = bool(latest.get("price_strength_confirmed") or first.get("price_strength_confirmed"))
        volume_confirmed = latest.get("volume_confirmed") is True or first.get("volume_confirmed") is True
        if signals.get("extended_from_anchor"):
            mechanical = "C"
            reasons.append("extended_from_anchor")
        elif signals.get("below_vwap") or signals.get("high_open_fade"):
            mechanical = "B"
            reasons.append("price_action_not_clean")
        elif price_confirmed and not first.get("red_flag"):
            mechanical = "A" if volume_confirmed else "B"
            reasons.append("price_confirmed" if volume_confirmed else "volume_not_confirmed")
        elif signals.get("near_ma5") or signals.get("near_ma20"):
            mechanical = "B"
            reasons.append("near_anchor_wait_confirmation")
        else:
            mechanical = "C"
            reasons.append("no_actionable_setup")
        mechanical = cap_class(mechanical, maximum)

    market_tier = (
        morning_tier if action == "NORMAL"
        else lower_position_tier(morning_tier) if action == "SELECTIVE"
        else "WATCH_ONLY"
    )
    signal_tier = market_tier if mechanical == "A" else "WATCH_ONLY"
    configured_t1 = strategy.get("t1_risk_plan")
    if isinstance(configured_t1, dict):
        t1_exit_plan = {
            "source": "daily_strategy.v3",
            "overnight_risk": configured_t1.get("overnight_risk"),
            "gap_up_action": configured_t1.get("gap_up_action"),
            "flat_open_action": configured_t1.get("flat_open_action"),
            "gap_down_action": configured_t1.get("gap_down_action"),
        }
    else:
        raise ValueError("daily_strategy.v3 requires t1_risk_plan")
    return {
        "mechanical_class": mechanical,
        "max_allowed_class": maximum,
        "class_reasons": reasons,
        "hard_blocks": hard_blocks,
        "position_tier": {
            "morning": morning_tier,
            "market_adjusted": market_tier,
            "signal_adjusted": signal_tier,
            "final": signal_tier,
        },
        "t1_controls": {
            "same_day_sell_allowed": False,
            "pre_entry_invalidation": strategy.get("no_buy") or strategy.get("no_buy_condition") or "条件失效则取消买入",
            "post_entry_t_risk_alert": "成交后若条件失效，标记为T+1高风险仓，次日优先处理",
            "t1_exit_plan": t1_exit_plan,
        },
    }
