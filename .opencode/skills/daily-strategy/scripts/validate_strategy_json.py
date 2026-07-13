#!/usr/bin/env python3
"""Validate predict/{date}/strategy.json.

This is a lightweight built-in validator with no external dependencies. It is
intended to keep strategy.json stable for review/backtest scripts and avoid
one-off JSON generation/parsing scripts.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import time
from pathlib import Path
from typing import Any


REGIMES = {"panic", "weak", "neutral", "strong-sector"}
DIRECTIONS = {"看多", "偏多", "中性", "看空"}
RATINGS = {"5★", "4★", "3★", "2★", "1★", "—"}
ENTRY_PROFILES = {"趋势跟随", "回调布局", "强势接力", "防御布局", "暂不参与"}
ANCHORS = {"MA5", "MA10", "MA20", "OPEN", "VWAP", "首根5min", "FLEX", "无", "—"}
PLAYBOOKS = {"MOMENTUM", "PULLBACK", "LIMIT_UP_CONT", "DEFENSIVE", "WATCH_ONLY"}
CHASE_POLICIES = {"NO_CHASE", "MA5_ONLY", "OPEN_PROBE_OK"}
ENTRY_WINDOWS = {"OPEN", "MORNING_DIP", "TAIL", "ANY"}
STOP_POLICIES = {"ATR_1.5", "ATR_2.0", "PCT_R35", "—"}
HORIZONS = {"T+0", "T+1", "SWING", "中期", "—"}
STRATEGY_SCHEMAS = {"daily_strategy.v1", "daily_strategy.v2"}
PREOPEN_DECISIONS = {"CONDITIONAL", "WATCH_ONLY"}
ENTRY_SETUPS = {"LIMIT_UP_CONT", "MOMENTUM", "FIRST_BAR_OR_PULLBACK", "PULLBACK", "DEFENSIVE", "WATCH_ONLY"}
REGIME_STOCK_LIMITS = {"strong-sector": 10, "neutral": 10, "weak": 7, "panic": 5}


def err(errors: list[str], path: str, msg: str) -> None:
    errors.append(f"{path}: {msg}")


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def optional_number(errors: list[str], value: Any, path: str) -> None:
    if value is not None and not is_number(value):
        err(errors, path, "must be number or null")


def enum(errors: list[str], value: Any, path: str, allowed: set[str]) -> None:
    if value not in allowed:
        err(errors, path, f"invalid value {value!r}; allowed={sorted(allowed)}")


def validate_preopen_plan(stock: dict[str, Any], i: int, errors: list[str]) -> None:
    base = f"stocks[{i}].preopen_plan"
    plan = stock.get("preopen_plan")
    if not isinstance(plan, dict):
        err(errors, base, "must be object for daily_strategy.v2")
        return
    enum(errors, plan.get("decision"), f"{base}.decision", PREOPEN_DECISIONS)
    enum(errors, plan.get("entry_setup"), f"{base}.entry_setup", ENTRY_SETUPS)
    earliest = plan.get("earliest_entry_time")
    latest = plan.get("latest_entry_time")
    earliest_time = None
    latest_time = None
    if not isinstance(earliest, str) or not re.match(r"^\d{2}:\d{2}:\d{2}$", earliest):
        err(errors, f"{base}.earliest_entry_time", "must be HH:MM:SS")
    else:
        try:
            earliest_time = time.fromisoformat(earliest)
        except ValueError:
            err(errors, f"{base}.earliest_entry_time", "must be a real time")
        if earliest_time is not None and earliest_time < time(9, 35, 5):
            err(errors, f"{base}.earliest_entry_time", "must not be earlier than 09:35:05")
    if not isinstance(latest, str) or not re.match(r"^\d{2}:\d{2}:\d{2}$", latest):
        err(errors, f"{base}.latest_entry_time", "must be HH:MM:SS")
    else:
        try:
            latest_time = time.fromisoformat(latest)
        except ValueError:
            err(errors, f"{base}.latest_entry_time", "must be a real time")
    if earliest_time is not None and latest_time is not None and latest_time < earliest_time:
        err(errors, f"{base}.latest_entry_time", "must not be earlier than earliest_entry_time")
    for key in ("requires_first_bar", "requires_market_confirmation", "requires_theme_confirmation"):
        if not isinstance(plan.get(key), bool):
            err(errors, f"{base}.{key}", "must be boolean")
    invalidations = plan.get("pre_entry_invalidations")
    if not isinstance(invalidations, list) or not invalidations or not all(isinstance(item, str) and item for item in invalidations):
        err(errors, f"{base}.pre_entry_invalidations", "must be non-empty list[str]")


def validate_t1_plan(stock: dict[str, Any], i: int, errors: list[str]) -> None:
    base = f"stocks[{i}].t1_risk_plan"
    plan = stock.get("t1_risk_plan")
    if not isinstance(plan, dict):
        err(errors, base, "must be object for daily_strategy.v2")
        return
    for key in ("overnight_risk", "gap_up_action", "flat_open_action", "gap_down_action"):
        if not isinstance(plan.get(key), str) or not plan.get(key):
            err(errors, f"{base}.{key}", "must be non-empty string")
    days = plan.get("max_holding_days")
    if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= 20:
        err(errors, f"{base}.max_holding_days", "must be integer in [1, 20]")


def validate_stock(stock: dict[str, Any], i: int, errors: list[str], schema: str) -> None:
    base = f"stocks[{i}]"
    required = [
        "code", "name", "sector", "direction", "rating",
        "entry_profile", "anchor", "entry_trigger", "no_buy_condition",
        "position_budget", "horizon", "profile",
    ]
    for key in required:
        if key not in stock:
            err(errors, f"{base}.{key}", "missing required field")

    code = stock.get("code")
    if not isinstance(code, str) or not re.match(r"^(sh|sz)\d{6}$", code):
        err(errors, f"{base}.code", "must be sh/sz + 6 digits")

    for key in ("name", "sector", "entry_trigger", "no_buy_condition"):
        if not isinstance(stock.get(key), str) or not stock.get(key):
            err(errors, f"{base}.{key}", "must be non-empty string")

    enum(errors, stock.get("direction"), f"{base}.direction", DIRECTIONS)
    enum(errors, stock.get("rating"), f"{base}.rating", RATINGS)
    enum(errors, stock.get("entry_profile"), f"{base}.entry_profile", ENTRY_PROFILES)
    enum(errors, stock.get("anchor"), f"{base}.anchor", ANCHORS)
    enum(errors, stock.get("horizon"), f"{base}.horizon", HORIZONS)

    budget = stock.get("position_budget")
    if budget is not None:
        if not is_number(budget):
            err(errors, f"{base}.position_budget", "must be number or null")
        elif not 0 <= budget <= 1:
            err(errors, f"{base}.position_budget", "must be between 0 and 1")

    rules = stock.get("rules_applied", [])
    if rules is not None and not (isinstance(rules, list) and all(isinstance(x, str) for x in rules)):
        err(errors, f"{base}.rules_applied", "must be list[str]")

    profile = stock.get("profile")
    if not isinstance(profile, dict):
        err(errors, f"{base}.profile", "must be object")
        return

    for key in ("playbook", "preferred_anchor", "chase_policy", "entry_window", "stop_policy"):
        if key not in profile:
            err(errors, f"{base}.profile.{key}", "missing required field")

    enum(errors, profile.get("playbook"), f"{base}.profile.playbook", PLAYBOOKS)
    enum(errors, profile.get("preferred_anchor"), f"{base}.profile.preferred_anchor", ANCHORS)
    enum(errors, profile.get("chase_policy"), f"{base}.profile.chase_policy", CHASE_POLICIES)
    enum(errors, profile.get("entry_window"), f"{base}.profile.entry_window", ENTRY_WINDOWS)
    enum(errors, profile.get("stop_policy"), f"{base}.profile.stop_policy", STOP_POLICIES)
    enum(errors, profile.get("time_horizon", stock.get("horizon")), f"{base}.profile.time_horizon", HORIZONS)

    for key in ("ref_ma20", "ref_ma10", "ref_ma5", "ref_high20", "max_extension_atr"):
        optional_number(errors, profile.get(key), f"{base}.profile.{key}")

    if "position_budget" in profile:
        optional_number(errors, profile.get("position_budget"), f"{base}.profile.position_budget")
    if schema == "daily_strategy.v2":
        if stock.get("horizon") != "T+1":
            err(errors, f"{base}.horizon", "daily_strategy.v2 A-share new positions must use T+1")
        validate_preopen_plan(stock, i, errors)
        validate_t1_plan(stock, i, errors)


def validate(doc: dict[str, Any], require_v2: bool = False) -> list[str]:
    errors: list[str] = []
    schema = doc.get("schema_version")
    if schema not in STRATEGY_SCHEMAS:
        err(errors, "schema_version", f"must be one of {sorted(STRATEGY_SCHEMAS)}")
    if require_v2 and schema != "daily_strategy.v2":
        err(errors, "schema_version", "daily_strategy.v2 required")
    if not isinstance(doc.get("date"), str) or not re.match(r"^\d{4}-\d{2}-\d{2}$", doc.get("date", "")):
        err(errors, "date", "must be YYYY-MM-DD")

    market = doc.get("market")
    if not isinstance(market, dict):
        err(errors, "market", "must be object")
    else:
        regime = market.get("regime_prior") if schema == "daily_strategy.v2" else market.get("regime_hint")
        enum(errors, regime, f"market.{'regime_prior' if schema == 'daily_strategy.v2' else 'regime_hint'}", REGIMES)
        if schema == "daily_strategy.v2" and market.get("requires_open_confirmation") is not True:
            err(errors, "market.requires_open_confirmation", "must be true")

    stocks = doc.get("stocks")
    if not isinstance(stocks, list):
        err(errors, "stocks", "must be list")
    else:
        if not stocks:
            err(errors, "stocks", "must not be empty")
        seen: set[str] = set()
        for i, stock in enumerate(stocks):
            if not isinstance(stock, dict):
                err(errors, f"stocks[{i}]", "must be object")
                continue
            code = stock.get("code")
            if isinstance(code, str):
                if code in seen:
                    err(errors, f"stocks[{i}].code", f"duplicate code {code}")
                seen.add(code)
            validate_stock(stock, i, errors, schema if isinstance(schema, str) else "")
    if schema == "daily_strategy.v2":
        limits = doc.get("portfolio_limits")
        if not isinstance(limits, dict):
            err(errors, "portfolio_limits", "must be object")
        else:
            for key in ("max_new_exposure", "max_theme_exposure", "max_single_stock"):
                value = limits.get(key)
                if not is_number(value) or not 0 <= value <= 1:
                    err(errors, f"portfolio_limits.{key}", "must be number in [0, 1]")
            correlated = limits.get("max_correlated_names")
            if not isinstance(correlated, int) or isinstance(correlated, bool) or correlated < 1:
                err(errors, "portfolio_limits.max_correlated_names", "must be positive integer")
            total = limits.get("max_new_exposure")
            theme = limits.get("max_theme_exposure")
            single = limits.get("max_single_stock")
            if all(is_number(value) for value in (total, theme, single)):
                if theme > total:
                    err(errors, "portfolio_limits.max_theme_exposure", "must not exceed max_new_exposure")
                if single > theme or single > total:
                    err(errors, "portfolio_limits.max_single_stock", "must not exceed theme or total exposure")
                for i, stock in enumerate(stocks if isinstance(stocks, list) else []):
                    if isinstance(stock, dict) and is_number(stock.get("position_budget")) and stock["position_budget"] > single:
                        err(errors, f"stocks[{i}].position_budget", "must not exceed portfolio_limits.max_single_stock")
        regime = market.get("regime_prior") if isinstance(market, dict) else None
        stock_limit = REGIME_STOCK_LIMITS.get(regime)
        if isinstance(stocks, list) and stock_limit is not None and len(stocks) > stock_limit:
            err(errors, "stocks", f"{regime} regime allows at most {stock_limit} strategy stocks, got {len(stocks)}; move overflow to observation_pool")
        strategy_codes = {
            stock.get("code") for stock in stocks if isinstance(stock, dict) and isinstance(stock.get("code"), str)
        } if isinstance(stocks, list) else set()
        for i, stock in enumerate(stocks if isinstance(stocks, list) else []):
            if not isinstance(stock, dict):
                continue
            if stock.get("direction") not in {"看多", "偏多"}:
                err(errors, f"stocks[{i}].direction", "main strategy only allows 看多/偏多; move non-buyable stock to observation_pool")
            if stock.get("entry_profile") == "暂不参与":
                err(errors, f"stocks[{i}].entry_profile", "暂不参与 must be placed in observation_pool, not stocks")
        observation = doc.get("observation_pool")
        if not isinstance(observation, list):
            err(errors, "observation_pool", "must be list for daily_strategy.v2")
        else:
            observation_seen: set[str] = set()
            for i, item in enumerate(observation):
                base = f"observation_pool[{i}]"
                if not isinstance(item, dict):
                    err(errors, base, "must be object")
                    continue
                code = item.get("code")
                if not isinstance(code, str) or not re.match(r"^(sh|sz)\d{6}$", code):
                    err(errors, f"{base}.code", "must be sh/sz + 6 digits")
                elif code in observation_seen:
                    err(errors, f"{base}.code", "duplicate")
                elif code in strategy_codes:
                    err(errors, f"{base}.code", "must not duplicate stocks[]")
                else:
                    observation_seen.add(code)
                for key in ("name", "reason"):
                    if not isinstance(item.get(key), str) or not item.get(key):
                        err(errors, f"{base}.{key}", "must be non-empty string")
    return errors


def main() -> None:
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Validate strategy.json")
    parser.add_argument("path", help="Path to strategy.json")
    parser.add_argument("--pretty", action="store_true", help="Print normalized JSON on success")
    parser.add_argument("--require-v2", action="store_true", help="Reject legacy daily_strategy.v1")
    args = parser.parse_args()

    path = Path(args.path)
    with path.open("r", encoding="utf-8") as f:
        doc = json.load(f)

    if not isinstance(doc, dict):
        print("[ERROR] root must be object", file=sys.stderr)
        sys.exit(1)

    errors = validate(doc, require_v2=args.require_v2)
    if errors:
        print(f"[ERROR] {path} failed validation ({len(errors)} errors):", file=sys.stderr)
        for item in errors:
            print(f"  - {item}", file=sys.stderr)
        sys.exit(1)

    print(f"OK: {path}")
    if args.pretty:
        print(json.dumps(doc, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
