#!/usr/bin/env python3
"""Shared helpers for the intraday mapper JSON contract."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from ashare_pilot.market_data.runtime import workspace_path
from ashare_pilot.market_data.trading_scope import (
    load_trading_scope,
    scope_decision,
)


HOLD_DIRECTIONS = {"持有偏多", "持有", "谨慎持有"}
STOP_LOSS_BASES = {"day_low", "ma5", "ma10", "ma20", "not_applicable"}
SELECTION_POOLS_SCHEMA_VERSION = "intraday_selection_pools.v1"
MAPPER_BASE_SCHEMA_VERSION = "intraday_mapper_base.v2"
MAPPER_ANNOTATIONS_SCHEMA_VERSION = "intraday_mapper_annotations.v2"
MAPPER_SCHEMA_VERSION = "intraday_mapper.v2"
OVERNIGHT_STRATEGY_SCHEMA_VERSION = "intraday_overnight_strategy.v2"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def intraday_dir(date: str) -> Path:
    return workspace_path("intraday", date)


def cache_dir(date: str) -> Path:
    return workspace_path(".cache", "intraday", date)


def stock_code(item: Any) -> str | None:
    if not isinstance(item, dict):
        return None
    code = item.get("code")
    return code if isinstance(code, str) and code else None


def numeric(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(str(value).replace("%", "").replace("+", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def limit_ratio(code: str, name: str) -> Decimal:
    normalized_name = str(name or "").upper().replace(" ", "")
    if "ST" in normalized_name:
        return Decimal("0.05")
    if str(code or "").startswith(("sz300", "sh688")):
        return Decimal("0.20")
    if str(code or "").startswith("bj"):
        return Decimal("0.30")
    return Decimal("0.10")


def limit_up_price(stock: dict[str, Any]) -> float | None:
    rt = stock.get("enriched", {}).get("real_time", {})
    rt = rt if isinstance(rt, dict) else {}
    try:
        previous = Decimal(str(rt.get("yestclose")))
        if previous <= 0:
            return None
        value = (previous * (Decimal("1") + limit_ratio(stock.get("code", ""), stock.get("name", "")))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        return float(value)
    except (InvalidOperation, TypeError, ValueError):
        return None


def execution_state(stock: dict[str, Any], scope: dict[str, Any] | None = None) -> dict[str, Any]:
    """Derive non-overridable tail-execution eligibility from compute fields."""
    code = str(stock.get("code") or "")
    rt = stock.get("enriched", {}).get("real_time", {})
    rt = rt if isinstance(rt, dict) else {}
    price = numeric(rt.get("price", stock.get("price")))
    high = numeric(rt.get("high"))
    limit_price = limit_up_price(stock)
    quote_complete = price is not None and high is not None and limit_price is not None
    is_limit_up = quote_complete and abs(price - limit_price) < 0.005
    is_sealed = bool(is_limit_up and abs(price - high) < 0.005)
    board = scope_decision(code, scope or load_trading_scope())
    board_excluded = board["excluded"]
    reason = (
        "board_policy"
        if board_excluded
        else "quote_data_missing"
        if not quote_complete
        else "sealed_limit_up"
        if is_sealed
        else None
    )
    return {
        "is_limit_up": bool(is_limit_up),
        "is_sealed": is_sealed,
        "limit_up_price": limit_price,
        "quote_complete": quote_complete,
        "source_pool_limit_up": stock.get("source_pool") == "limit_up",
        "board_excluded": board_excluded,
        "board_rule": board["matched_rule"],
        "board_reason": board["reason"],
        "eligible": reason is None,
        "exclusion_reason": reason,
    }


def stop_loss_price(stock: dict[str, Any], basis: Any) -> float | None:
    if basis == "not_applicable":
        return None
    rt = stock.get("enriched", {}).get("real_time", {})
    rt = rt if isinstance(rt, dict) else {}
    technicals = stock.get("technicals") if isinstance(stock.get("technicals"), dict) else {}
    source = {
        "day_low": rt.get("low"),
        "ma5": technicals.get("ma5"),
        "ma10": technicals.get("ma10"),
        "ma20": technicals.get("ma20"),
    }.get(basis)
    value = numeric(source)
    return round(value, 4) if value is not None else None


def resolved_stop_loss(stock: dict[str, Any], basis: Any) -> dict[str, Any]:
    labels = {"day_low": "今日最低价", "ma5": "MA5", "ma10": "MA10", "ma20": "MA20"}
    price = stop_loss_price(stock, basis)
    if basis == "not_applicable":
        return {"stop_loss_basis": basis, "stop_loss_price": None, "stop_loss": "不适用"}
    label = labels.get(str(basis), str(basis))
    text = f"{label} {price:g}" if price is not None else f"{label}（数据缺失）"
    return {"stop_loss_basis": basis, "stop_loss_price": price, "stop_loss": text}


def reasoning_invariant_errors(stock: dict[str, Any], reasoning: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    direction = reasoning.get("direction")
    tradeability = reasoning.get("tradeability")
    derived_state = execution_state(stock)
    stored_state = stock.get("execution_state")
    if isinstance(stored_state, dict) and stored_state != derived_state:
        errors.append("execution_state differs from deterministic compute fields")
    state = derived_state
    actionable = direction in HOLD_DIRECTIONS
    plan = reasoning.get("t_plus_1_plan")
    plan = plan if isinstance(plan, dict) else {}
    basis = plan.get("stop_loss_basis")

    if state.get("is_sealed") and direction != "观望":
        errors.append("sealed limit-up requires direction=观望")
    if state.get("board_excluded") and direction != "观望":
        errors.append("board-policy exclusion requires direction=观望")
    if actionable and not state.get("eligible"):
        errors.append("actionable direction requires execution_state.eligible=true")
    if actionable and basis not in STOP_LOSS_BASES - {"not_applicable"}:
        errors.append("actionable direction requires a structured stop_loss_basis")
    if not actionable and basis != "not_applicable":
        errors.append("observation direction requires stop_loss_basis=not_applicable")
    if actionable:
        stop = stop_loss_price(stock, basis)
        current = numeric(stock.get("enriched", {}).get("real_time", {}).get("price", stock.get("price")))
        if stop is None or current is None or stop <= 0 or stop >= current:
            errors.append("resolved stop loss must be positive and below current price")
    if basis in STOP_LOSS_BASES:
        resolved = resolved_stop_loss(stock, basis)
        for field in ("stop_loss_price", "stop_loss"):
            if field in plan and plan.get(field) != resolved[field]:
                errors.append(f"{field} differs from deterministic stop-loss resolution")
    return errors


def market_board(code: str) -> str:
    normalized = str(code or "").lower()
    if normalized.startswith("sh688"):
        return "科创板"
    if normalized.startswith("sh"):
        return "沪市主板"
    if normalized.startswith("sz300"):
        return "创业板"
    if normalized.startswith("sz"):
        return "深市主板"
    if normalized.startswith("bj"):
        return "北交所"
    return "未知交易板"


def primary_theme(themes: list[dict[str, Any]]) -> str | None:
    role_order = {"core": 0, "qualified": 1, "edge": 2}
    relations = [
        value
        for value in themes
        if isinstance(value, dict) and isinstance(value.get("name"), str) and value["name"]
    ]
    if not relations:
        return None
    selected = min(
        relations,
        key=lambda value: (
            role_order.get(value.get("member_role"), 2),
            -(numeric(value.get("industry_score")) or 0),
            -(numeric(value.get("purity_score")) or 0),
            -(numeric(value.get("weight")) or 0),
            value["name"],
        ),
    )
    return selected["name"]


def attach_theme_evidence(
    stocks: list[dict[str, Any]],
    stock_themes: dict[str, Any],
    theme_ranking: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    result = []
    for stock in stocks:
        item = dict(stock)
        code = str(item.get("code") or "")
        evidence = stock_themes.get(code) if isinstance(stock_themes, dict) else None
        relations = evidence.get("themes", []) if isinstance(evidence, dict) else []
        relations = [dict(value) for value in relations if isinstance(value, dict)]
        selected = primary_theme(relations)
        item["market_board"] = market_board(code)
        item["primary_theme"] = selected
        item["themes"] = relations
        item["sector"] = selected
        item["theme_support_shadow"] = build_theme_support_shadow(
            relations,
            selected,
            theme_ranking or {},
        )
        result.append(item)
    return result


def build_theme_support_shadow(
    stock_relations: list[dict[str, Any]],
    primary_theme_name: str | None,
    theme_ranking: dict[str, Any],
) -> dict[str, Any]:
    unavailable = {
        "available": False,
        "primary_theme": primary_theme_name,
        "member_role": None,
        "membership_weight": None,
        "core_heat": None,
        "diffusion_heat": None,
        "theme_rank": None,
    }
    if not stock_relations or not primary_theme_name:
        return {**unavailable, "missing_reason": "stock_has_no_theme_relation"}
    relation = next(
        (
            item
            for item in stock_relations
            if isinstance(item, dict) and item.get("name") == primary_theme_name
        ),
        None,
    )
    if not isinstance(relation, dict):
        return {**unavailable, "missing_reason": "theme_membership_incomplete"}
    role = relation.get("member_role")
    weight = numeric(relation.get("weight"))
    if role not in {"core", "qualified", "edge"} or weight is None:
        return {**unavailable, "missing_reason": "theme_membership_incomplete"}
    rankings = (
        theme_ranking.get("theme_ranking", [])
        if isinstance(theme_ranking, dict)
        else []
    )
    ranked = next(
        (
            (index, row)
            for index, row in enumerate(rankings[:15], 1)
            if isinstance(row, dict) and row.get("theme") == primary_theme_name
        ),
        None,
    )
    if ranked is None:
        return {
            **unavailable,
            "member_role": role,
            "membership_weight": weight,
            "missing_reason": "primary_theme_not_in_top15",
        }
    rank, row = ranked
    core_heat = numeric(row.get("core_heat"))
    diffusion_heat = numeric(row.get("diffusion_heat"))
    if core_heat is None or diffusion_heat is None:
        return {
            **unavailable,
            "member_role": role,
            "membership_weight": weight,
            "theme_rank": rank,
            "missing_reason": "dynamic_heat_fields_missing",
        }
    return {
        "available": True,
        "primary_theme": primary_theme_name,
        "member_role": role,
        "membership_weight": weight,
        "core_heat": core_heat,
        "diffusion_heat": diffusion_heat,
        "theme_rank": rank,
        "missing_reason": None,
    }


def merge_annotations(base: dict[str, Any], annotations: dict[str, Any]) -> dict[str, Any]:
    executable_notes = {
        item["code"]: item
        for item in annotations.get("executable_annotations", [])
        if isinstance(item, dict) and isinstance(item.get("code"), str)
    }
    observation_notes = {
        item["code"]: item
        for item in annotations.get("observation_annotations", [])
        if isinstance(item, dict) and isinstance(item.get("code"), str)
    }
    executable_stocks = []
    for stock in base.get("executable_stocks", []):
        item = dict(stock)
        note = executable_notes.get(stock.get("code"))
        if note:
            reasoning = {key: value for key, value in note.items() if key != "code"}
            plan = reasoning.get("t_plus_1_plan")
            if isinstance(plan, dict):
                plan = dict(plan)
                plan.update(resolved_stop_loss(stock, plan.get("stop_loss_basis")))
                reasoning["t_plus_1_plan"] = plan
            item["reasoning"] = reasoning
        executable_stocks.append(item)
    observation_stocks = []
    for stock in base.get("observation_stocks", []):
        item = dict(stock)
        note = observation_notes.get(stock.get("code"))
        if note:
            item["observation_reasoning"] = {
                key: value for key, value in note.items() if key != "code"
            }
        observation_stocks.append(item)

    result = dict(base)
    result["schema_version"] = MAPPER_SCHEMA_VERSION
    result["generated_at"] = utc_now_iso()
    result["generation_mode"] = "compute_base_plus_llm_annotations"
    result["market_assessment"] = annotations.get("market_assessment")
    result["strategy"] = annotations.get("strategy")
    result["executable_stocks"] = executable_stocks
    result["observation_stocks"] = observation_stocks
    result["annotation_coverage"] = {
        "executable": {
            "expected": len(executable_stocks),
            "annotated": len(executable_notes),
        },
        "observation": {
            "expected": len(observation_stocks),
            "annotated": len(observation_notes),
        },
    }
    return result
