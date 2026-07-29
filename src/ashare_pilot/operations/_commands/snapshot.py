#!/usr/bin/env python3
"""Build an intraday operation snapshot from morning strategy and current quotes.

This script does not make trading decisions. It normalizes current market data
into flags that the intraday-operation-guide skill can interpret.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from ashare_pilot.market_data._commands.quote import fetch_intraday_kline, fetch_stocks
from ashare_pilot.market_data.runtime import workspace_path
from ashare_pilot.operations.market_confirmation import INDEX_CODES, build_market_confirmation  # noqa: E402
from ashare_pilot.operations.mechanical_classification import compute_mechanical_decision  # noqa: E402
from ashare_pilot.operations.operation_transition import apply_delivery_gate, apply_previous_snapshot  # noqa: E402
from ashare_pilot.operations.portfolio_allocation import apply_portfolio_limits  # noqa: E402
from ashare_pilot.operations.theme_confirmation import apply_theme_caps, build_theme_confirmations  # noqa: E402
from ashare_pilot.operations.operation_time import (  # noqa: E402
    first_session_bar,
    iso_market,
    now_market,
    parse_market_datetime,
    select_completed_bars,
    snapshot_slot,
)


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace("%", "").replace(",", "")
    if not text or text in {"-", "--", "—", "None", "null"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"required input missing: {path}")
    with path.open("r", encoding="utf-8-sig") as f:
        doc = json.load(f)
    if not isinstance(doc, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return doc


def read_json_any(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"fixture missing: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_strategies(doc: dict[str, Any], expected_date: str) -> dict[str, dict[str, Any]]:
    schema = doc.get("schema_version")
    if schema != "daily_strategy.v3":
        raise ValueError("strategy.json schema_version must be daily_strategy.v3")
    if doc.get("date") != expected_date:
        raise ValueError(f"strategy.json date mismatch: expected {expected_date}, got {doc.get('date')!r}")
    stocks = doc.get("stocks")
    if not isinstance(stocks, list) or not stocks:
        raise ValueError("strategy.json stocks must be a non-empty list")

    strategies: dict[str, dict[str, Any]] = {}
    for stock in stocks:
        if not isinstance(stock, dict) or not isinstance(stock.get("code"), str):
            raise ValueError("strategy.json contains a stock without a valid code")
        code = stock["code"]
        if code in strategies:
            raise ValueError(f"strategy.json contains duplicate code: {code}")
        normalized = dict(stock)
        preopen_plan = stock.get("preopen_plan")
        if not isinstance(preopen_plan, dict):
            raise ValueError(f"strategy.json {code} missing preopen_plan")
        normalized.update({
            "profile": stock.get("entry_profile", ""),
            "trigger": stock.get("entry_trigger", ""),
            "no_buy": stock.get("no_buy_condition", ""),
            "position_tier": stock.get("position_tier"),
            "strategy_schema_version": schema,
            "preopen_plan": preopen_plan,
            "t1_risk_plan": stock.get("t1_risk_plan"),
        })
        strategies[code] = normalized
    return strategies


def parse_mapper_inputs(doc: dict[str, Any], expected_date: str) -> dict[str, dict[str, Any]]:
    if doc.get("schema_version") != "daily_mapper.v2":
        raise ValueError("mapper.json schema_version must be daily_mapper.v2")
    if doc.get("date") != expected_date:
        raise ValueError(f"mapper.json date mismatch: expected {expected_date}, got {doc.get('date')!r}")

    inputs: dict[str, dict[str, Any]] = {}
    for pool_name in ("candidate_pool", "observation_pool"):
        pool = doc.get(pool_name)
        if not isinstance(pool, list):
            raise ValueError(f"mapper.json {pool_name} must be a list")
        for stock in pool:
            if not isinstance(stock, dict) or not isinstance(stock.get("code"), str):
                continue
            raw = stock.get("strategy_inputs")
            if not isinstance(raw, dict):
                continue
            code = stock["code"]
            if code in inputs:
                raise ValueError(f"mapper.json contains duplicate strategy_inputs for code: {code}")
            inputs[code] = {
                "code": code,
                "price_ref": parse_float(raw.get("price")),
                "price_source": raw.get("price_source"),
                "ma20": parse_float(raw.get("ma20")),
                "ma5": parse_float(raw.get("ma5")),
                "atr": parse_float(raw.get("atr")),
                "atr_pct": parse_float(raw.get("atr_pct")),
                "high20": parse_float(raw.get("high20")),
                "low20": parse_float(raw.get("low20")),
            }
    return inputs


def safe_ratio(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


def bar_signals(bar: dict[str, Any] | None, baseline: float | None, baseline_n: int) -> dict[str, Any]:
    if not bar:
        return {"is_complete": False}
    open_price = parse_float(bar.get("open"))
    close = parse_float(bar.get("close"))
    high = parse_float(bar.get("high"))
    low = parse_float(bar.get("low"))
    volume = parse_float(bar.get("volume")) or 0.0
    rng = (high or 0) - (low or 0)
    close_position = ((close or 0) - (low or 0)) / rng if rng > 0 else None
    red_flag = bool(open_price and close and close < open_price and (open_price - close) / open_price >= 0.015)
    multiple = volume / baseline if baseline and baseline > 0 else None
    return {
        "bar_start": bar.get("bar_start"),
        "bar_end": bar.get("bar_end"),
        "is_complete": True,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "close_position": round(close_position, 4) if close_position is not None else None,
        "red_flag": red_flag,
        "volume_baseline_kind": "recent_completed_bars",
        "volume_baseline_sample_n": baseline_n,
        "volume_multiple": round(multiple, 2) if multiple is not None else None,
        "volume_confirmed": (multiple >= 1.5) if multiple is not None else None,
        "price_strength_confirmed": bool(close and open_price and close >= open_price and (close_position is None or close_position >= 0.65)),
    }


def compute_kline_flags(
    klines: list[dict[str, Any]], snapshot_time: datetime, trade_date
) -> dict[str, Any]:
    completed = select_completed_bars(klines, snapshot_time, trade_date, scale_minutes=5)
    warnings: list[str] = []
    if not completed:
        warnings.append("intraday_completed_bar_missing")
    first = first_session_bar(completed, trade_date)
    if snapshot_time.hour == 9 and snapshot_time.minute >= 35 and first is None:
        warnings.append("first_bar_missing")
    latest = completed[-1] if completed else None
    previous = completed[-6:-1] if len(completed) >= 2 else []
    baseline_values = [parse_float(item.get("volume")) for item in previous]
    baseline_values = [item for item in baseline_values if item is not None]
    baseline = sum(baseline_values) / len(baseline_values) if baseline_values else None
    if latest and baseline is None:
        warnings.append("volume_baseline_insufficient")
    first_flags = bar_signals(first, None, 0)
    latest_flags = bar_signals(latest, baseline, len(baseline_values))
    return {
        "snapshot_time": iso_market(snapshot_time),
        "completed_bar_count": len(completed),
        "first_bar": first_flags,
        "latest_completed_bar": latest_flags,
        "data_warning": warnings,
        # Deprecated flat projections for existing human prompts.
        "latest_bar_time": latest_flags.get("bar_end"),
        "volume_multiple": latest_flags.get("volume_multiple"),
        "volume_confirmed": latest_flags.get("volume_confirmed"),
        "price_strength_confirmed": latest_flags.get("price_strength_confirmed", False),
        "first_bar_red_flag": first_flags.get("red_flag", False),
    }


def estimate_vwap(quote: dict[str, Any]) -> float | None:
    amount = parse_float(quote.get("amount"))
    volume = parse_float(quote.get("volume"))
    if amount is None or volume is None or volume <= 0:
        return None
    # Sina quote amount is yuan, volume is shares for A stocks.
    vwap = amount / volume
    if vwap <= 0 or math.isnan(vwap) or math.isinf(vwap):
        return None
    return vwap


def build_stock_snapshot(
    code: str,
    strategy: dict[str, Any],
    mapper: dict[str, Any],
    quote: dict[str, Any],
    snapshot_time: datetime,
    market: dict[str, Any],
    klines: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    price = parse_float(quote.get("price"))
    open_price = parse_float(quote.get("open"))
    high = parse_float(quote.get("high"))
    low = parse_float(quote.get("low"))
    percent = parse_float(quote.get("percent"))
    ma5 = mapper.get("ma5")
    ma20 = mapper.get("ma20")
    atr = mapper.get("atr")
    high20 = mapper.get("high20")
    vwap = estimate_vwap(quote)

    raw_klines = klines if klines is not None else fetch_intraday_kline(code, scale=5, days=1)
    kflags = compute_kline_flags(raw_klines, snapshot_time, snapshot_time.date())

    dist_ma5 = safe_ratio((price - ma5) if price is not None and ma5 is not None else None, atr)
    dist_ma20 = safe_ratio((price - ma20) if price is not None and ma20 is not None else None, atr)
    high_fade = False
    if price is not None and open_price is not None and high is not None and open_price > 0:
        previous_close = parse_float(quote.get("yestclose")) or open_price
        opened_strong = previous_close > 0 and (open_price - previous_close) / previous_close >= 0.02
        faded_from_high = high > 0 and (high - price) / high >= 0.025
        below_open = price < open_price
        high_fade = bool(opened_strong and faded_from_high and below_open)

    extended_anchor = False
    anchor_label = str(strategy.get("anchor") or "").upper()
    if "MA5" in anchor_label:
        anchor = ma5
    elif "MA20" in anchor_label:
        anchor = ma20
    else:
        anchor = ma5 if strategy.get("profile") in {"趋势跟随", "强势接力"} else ma20
    if price is not None and anchor is not None and atr:
        extended_anchor = (price - anchor) / atr > 1.5

    data_warnings = []
    if "error" in quote:
        data_warnings.append("quote_error")
    if price is None or price <= 0:
        data_warnings.append("invalid_price")
    data_warnings.extend(kflags.get("data_warning") or [])
    if not (len(code) == 8 and code[:2] in {"sh", "sz"} and code[2:].isdigit()):
        data_warnings.append("invalid_code")

    flags = {
        "above_ma5": bool(price is not None and ma5 is not None and price >= ma5),
        "above_ma20": bool(price is not None and ma20 is not None and price >= ma20),
        "near_ma5": bool(dist_ma5 is not None and abs(dist_ma5) <= 0.5),
        "near_ma20": bool(dist_ma20 is not None and abs(dist_ma20) <= 0.5),
        "below_vwap": bool(price is not None and vwap is not None and price < vwap),
        "high_open_fade": high_fade,
        "extended_from_anchor": extended_anchor,
        "data_warning": data_warnings,
    }
    flags.update(kflags)
    flags["data_warning"] = data_warnings

    mechanical = compute_mechanical_decision(strategy, flags, market, snapshot_time)

    return {
        "code": code,
        "name": strategy.get("name") or quote.get("name"),
        "strategy": strategy,
        "quote": {
            "price": price,
            "open": open_price,
            "high": high,
            "low": low,
            "percent": percent,
            "time": quote.get("time"),
            "vwap_est": round(vwap, 3) if vwap else None,
        },
        "anchors": mapper,
        "dist_atr": {
            "ma5": round(dist_ma5, 2) if dist_ma5 is not None else None,
            "ma20": round(dist_ma20, 2) if dist_ma20 is not None else None,
            "high20_pct": round((price / high20 - 1) * 100, 2) if price is not None and high20 else None,
        },
        "signals": flags,
        "decision_guardrails": mechanical,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build intraday operation snapshot")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--slot", choices=["auto", "09:35", "09:40", "09:45"], default="auto")
    parser.add_argument("--as-of", help="ISO datetime override for replay/testing")
    parser.add_argument("--quotes-fixture", help="JSON with stocks[] and indices[] for replay")
    parser.add_argument("--intraday-fixture-dir", help="Directory containing <code>.json bars")
    parser.add_argument("--no-network", action="store_true", help="Fail instead of fetching missing fixture data")
    parser.add_argument("--previous-snapshot", help="Previous slot snapshot for transition checks")
    parser.add_argument(
        "--run-mode",
        choices=["INITIAL_CONFIRMATION", "LATE_INITIAL_CONFIRMATION", "SECOND_CONFIRMATION", "RECHECK", "LATE_OBSERVE_ONLY", "EARLY"],
        help="Orchestrator-selected lifecycle mode",
    )
    parser.add_argument("--write-latest", action="store_true", help="Also atomically write operation_snapshot.latest.json")
    parser.add_argument("--json", action="store_true", help="Print JSON")
    parser.add_argument("-o", "--output", help="Output file")
    args = parser.parse_args(argv)

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    snapshot_time = parse_market_datetime(args.as_of) if args.as_of else now_market()
    if snapshot_time is None:
        raise ValueError(f"invalid --as-of value: {args.as_of!r}")
    if snapshot_time.date().isoformat() != args.date:
        raise ValueError(f"snapshot date mismatch: expected {args.date}, got {snapshot_time.date()}")
    actual_slot = snapshot_slot(snapshot_time)
    selected_slot = actual_slot if args.slot == "auto" else args.slot
    slot_minimum = {"09:35": "09:35:10", "09:40": "09:40:10", "09:45": "09:45:10"}
    if selected_slot in slot_minimum and snapshot_time.strftime("%H:%M:%S") < slot_minimum[selected_slot]:
        raise ValueError(f"snapshot time {snapshot_time.time()} is before completed {selected_slot} slot")
    if args.slot != "auto" and actual_slot != selected_slot:
        raise ValueError(
            f"snapshot time {snapshot_time.time()} belongs to slot {actual_slot}, not requested {selected_slot}"
        )

    strategy_path = workspace_path("predict", args.date, "strategy.json")
    mapper_path = workspace_path("predict", args.date, "mapper.json")
    strategies = parse_strategies(read_json(strategy_path), args.date)
    mapper_inputs = parse_mapper_inputs(read_json(mapper_path), args.date)
    missing_mapper = [code for code in strategies if code not in mapper_inputs]
    if missing_mapper:
        raise ValueError(
            "mapper.json missing strategy_inputs for strategy codes: "
            + ", ".join(missing_mapper)
        )
    codes = list(strategies)

    fixture = read_json_any(Path(args.quotes_fixture)) if args.quotes_fixture else None
    if fixture is not None and not isinstance(fixture, (dict, list)):
        raise ValueError("quotes fixture must be object or list")
    if isinstance(fixture, dict):
        quotes = fixture.get("stocks", [])
        index_quotes = fixture.get("indices", [])
    elif isinstance(fixture, list):
        quotes = [item for item in fixture if item.get("code") in codes]
        index_quotes = [item for item in fixture if item.get("code") in INDEX_CODES]
    else:
        if args.no_network:
            raise ValueError("--no-network requires --quotes-fixture")
        quotes = fetch_stocks(codes) if codes else []
        index_quotes = fetch_stocks(list(INDEX_CODES))
    quote_by_code = {q.get("code"): q for q in quotes}
    strategy_doc = read_json(strategy_path)
    market_doc = strategy_doc.get("market") if isinstance(strategy_doc.get("market"), dict) else {}
    regime_prior = market_doc.get("regime_prior") or market_doc.get("regime_hint") or "neutral"
    market = build_market_confirmation(index_quotes, regime_prior)

    stocks = []
    intraday_dir = Path(args.intraday_fixture_dir) if args.intraday_fixture_dir else None
    for code in codes:
        fixture_bars = None
        if intraday_dir is not None:
            fixture_bars = read_json_any(intraday_dir / f"{code}.json")
            if not isinstance(fixture_bars, list):
                raise ValueError(f"intraday fixture for {code} must be list")
        elif args.no_network:
            raise ValueError("--no-network requires --intraday-fixture-dir")
        stocks.append(build_stock_snapshot(
            code,
            strategies.get(code, {"code": code}),
            mapper_inputs.get(code, {"code": code}),
            quote_by_code.get(code, {"code": code, "error": "quote_missing"}),
            snapshot_time,
            market,
            fixture_bars,
        ))

    themes = build_theme_confirmations(stocks)
    apply_theme_caps(stocks, themes)
    previous = read_json(Path(args.previous_snapshot)) if args.previous_snapshot else None
    if previous is not None and previous.get("date") != args.date:
        raise ValueError("previous snapshot date mismatch")
    if previous is not None:
        previous_time = parse_market_datetime(previous.get("generated_at"))
        if previous_time is None or previous_time >= snapshot_time:
            raise ValueError("previous snapshot must have a valid generated_at earlier than current snapshot")
    if args.run_mode in {"SECOND_CONFIRMATION", "RECHECK"} and previous is None:
        raise ValueError(f"{args.run_mode} requires --previous-snapshot")
    if args.run_mode in {"INITIAL_CONFIRMATION", "LATE_INITIAL_CONFIRMATION", "LATE_OBSERVE_ONLY", "EARLY"} and previous is not None:
        raise ValueError(f"{args.run_mode} must not use --previous-snapshot")
    delivery = apply_delivery_gate(stocks, selected_slot, previous is not None)
    transition_warnings = apply_previous_snapshot(stocks, previous)
    portfolio_allocation = apply_portfolio_limits(stocks, strategy_doc.get("portfolio_limits"))

    run_mode = args.run_mode
    if run_mode is None:
        if previous is not None:
            run_mode = "SECOND_CONFIRMATION" if selected_slot == "09:40" else "RECHECK"
        elif selected_slot == "09:35":
            run_mode = "INITIAL_CONFIRMATION"
        elif selected_slot == "09:40":
            run_mode = "LATE_INITIAL_CONFIRMATION"
        elif selected_slot == "EARLY":
            run_mode = "EARLY"
        else:
            run_mode = "LATE_OBSERVE_ONLY"
    lineage = None
    if previous is not None and args.previous_snapshot:
        previous_path = Path(args.previous_snapshot)
        previous_lineage = previous.get("lineage") if isinstance(previous.get("lineage"), dict) else {}
        lineage = {
            "previous_snapshot": str(previous_path),
            "previous_snapshot_sha256": file_sha256(previous_path),
            "chain_root": previous_lineage.get("chain_root") or str(previous_path),
        }

    output = {
        "schema_version": "intraday_operation_snapshot.v3",
        "date": args.date,
        "generated_at": iso_market(snapshot_time),
        "snapshot_slot": selected_slot,
        "run_mode": run_mode,
        "lineage": lineage,
        "source_files": {
            "strategy": str(strategy_path),
            "mapper": str(mapper_path),
        },
        "source_strategy": {
            "schema_version": strategy_doc.get("schema_version"),
            "run_id": strategy_doc.get("run_id"),
        },
        "stock_count": len(stocks),
        "market_confirmation": market,
        "delivery_confirmation": delivery,
        "theme_confirmations": themes,
        "transition_warnings": transition_warnings,
        "portfolio_allocation": portfolio_allocation,
        "stocks": stocks,
    }

    text = json.dumps(output, ensure_ascii=False, indent=2)
    if args.output:
        out = workspace_path(args.output)
        atomic_write(out, text)
        if args.write_latest:
            atomic_write(out.parent / "operation_snapshot.latest.json", text)
        print(f"Saved to {out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


