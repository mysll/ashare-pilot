#!/usr/bin/env python3
"""Build an intraday operation snapshot from morning strategy and current quotes.

This script does not make trading decisions. It normalizes current market data
into flags that the intraday-operation-guide skill can interpret.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / ".opencode"))

from lib.fetch.fetch_stock import fetch_intraday_kline, fetch_stocks  # noqa: E402


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


def parse_strategies(doc: dict[str, Any], expected_date: str) -> dict[str, dict[str, Any]]:
    if doc.get("schema_version") != "daily_strategy.v1":
        raise ValueError("strategy.json schema_version must be daily_strategy.v1")
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
        normalized.update({
            "profile": stock.get("entry_profile", ""),
            "trigger": stock.get("entry_trigger", ""),
            "no_buy": stock.get("no_buy_condition", ""),
            "position": stock.get("position_budget"),
        })
        strategies[code] = normalized
    return strategies


def parse_mapper_inputs(doc: dict[str, Any], expected_date: str) -> dict[str, dict[str, Any]]:
    if doc.get("schema_version") != "daily_mapper.v1":
        raise ValueError("mapper.json schema_version must be daily_mapper.v1")
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


def compute_kline_flags(klines: list[dict[str, Any]]) -> dict[str, Any]:
    clean = [k for k in klines if "error" not in k and parse_float(k.get("close")) is not None]
    if not clean:
        return {"data_warning": "intraday_kline_missing"}

    latest = clean[-1]
    latest_open = parse_float(latest.get("open"))
    latest_close = parse_float(latest.get("close"))
    latest_high = parse_float(latest.get("high"))
    latest_low = parse_float(latest.get("low"))
    latest_volume = parse_float(latest.get("volume")) or 0.0
    prev = clean[-6:-1] if len(clean) >= 6 else clean[:-1]
    avg_volume = sum(parse_float(k.get("volume")) or 0.0 for k in prev) / len(prev) if prev else 0.0

    rng = (latest_high or 0) - (latest_low or 0)
    close_position = ((latest_close or 0) - (latest_low or 0)) / rng if rng > 0 else None
    large_red = False
    if latest_open and latest_close and latest_open > 0:
        large_red = latest_close < latest_open and (latest_open - latest_close) / latest_open >= 0.015

    return {
        "latest_bar_time": latest.get("time"),
        "latest_bar_open": latest_open,
        "latest_bar_close": latest_close,
        "latest_bar_volume": latest_volume,
        "avg_5bar_volume": avg_volume,
        "volume_multiple": round(latest_volume / avg_volume, 2) if avg_volume > 0 else None,
        "volume_confirmed": bool(avg_volume > 0 and latest_volume >= avg_volume * 1.5),
        "price_strength_confirmed": bool(latest_close and latest_open and latest_close >= latest_open and (close_position is None or close_position >= 0.65)),
        "first_bar_red_flag": large_red,
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


def build_stock_snapshot(code: str, strategy: dict[str, Any], mapper: dict[str, Any], quote: dict[str, Any]) -> dict[str, Any]:
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

    klines = fetch_intraday_kline(code, scale=5, days=1)
    kflags = compute_kline_flags(klines)

    dist_ma5 = safe_ratio((price - ma5) if price is not None and ma5 is not None else None, atr)
    dist_ma20 = safe_ratio((price - ma20) if price is not None and ma20 is not None else None, atr)
    high_fade = False
    if price is not None and open_price is not None and high is not None and open_price > 0:
        opened_strong = (open_price - (parse_float(quote.get("yestclose")) or open_price)) / open_price >= 0.02
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
    if kflags.get("data_warning"):
        data_warnings.append(kflags["data_warning"])
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
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build intraday operation snapshot")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--json", action="store_true", help="Print JSON")
    parser.add_argument("-o", "--output", help="Output file")
    args = parser.parse_args()

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    strategy_path = ROOT / "predict" / args.date / "strategy.json"
    mapper_path = ROOT / "predict" / args.date / "mapper.json"
    strategies = parse_strategies(read_json(strategy_path), args.date)
    mapper_inputs = parse_mapper_inputs(read_json(mapper_path), args.date)
    missing_mapper = [code for code in strategies if code not in mapper_inputs]
    if missing_mapper:
        raise ValueError(
            "mapper.json missing strategy_inputs for strategy codes: "
            + ", ".join(missing_mapper)
        )
    codes = list(strategies)

    quotes = fetch_stocks(codes) if codes else []
    quote_by_code = {q.get("code"): q for q in quotes}

    stocks = []
    for code in codes:
        stocks.append(build_stock_snapshot(code, strategies.get(code, {"code": code}), mapper_inputs.get(code, {"code": code}), quote_by_code.get(code, {"code": code, "error": "quote_missing"})))

    output = {
        "date": args.date,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source_files": {
            "strategy": str(strategy_path),
            "mapper": str(mapper_path),
        },
        "stock_count": len(stocks),
        "stocks": stocks,
    }

    text = json.dumps(output, ensure_ascii=False, indent=2)
    if args.output:
        out = ROOT / args.output
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"Saved to {out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


