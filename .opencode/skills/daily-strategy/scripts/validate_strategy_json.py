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


def validate_stock(stock: dict[str, Any], i: int, errors: list[str]) -> None:
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


def validate(doc: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if doc.get("schema_version") != "daily_strategy.v1":
        err(errors, "schema_version", "must be daily_strategy.v1")
    if not isinstance(doc.get("date"), str) or not re.match(r"^\d{4}-\d{2}-\d{2}$", doc.get("date", "")):
        err(errors, "date", "must be YYYY-MM-DD")

    market = doc.get("market")
    if not isinstance(market, dict):
        err(errors, "market", "must be object")
    else:
        enum(errors, market.get("regime_hint"), "market.regime_hint", REGIMES)

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
            validate_stock(stock, i, errors)
    return errors


def main() -> None:
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Validate strategy.json")
    parser.add_argument("path", help="Path to strategy.json")
    parser.add_argument("--pretty", action="store_true", help="Print normalized JSON on success")
    args = parser.parse_args()

    path = Path(args.path)
    with path.open("r", encoding="utf-8") as f:
        doc = json.load(f)

    if not isinstance(doc, dict):
        print("[ERROR] root must be object", file=sys.stderr)
        sys.exit(1)

    errors = validate(doc)
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
