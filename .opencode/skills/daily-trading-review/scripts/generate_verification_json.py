#!/usr/bin/env python3
"""Generate machine-readable daily verification data independently of Markdown.

Inputs:
  - recommendation codes passed by the review agent via --codes, OR
    predict/{date}/strategy.md as a backward-compatible fallback
  - optional predict/{date}/pool_indicators.json for precomputed MA/ATR fields
  - market data fetchers for daily OHLC, intraday first candle, MA/ATR

Output:
  - memory/daily/{date}/verification.json

The JSON is the data source for backtests. verification.md is a human report and
must not be parsed for quantitative research.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / ".opencode"))
sys.path.insert(0, str(ROOT))

from lib.fetch.fetch_history import fetch_history
from lib.fetch.fetch_indicators import calc_atr, calc_sma, parse_value
from lib.fetch.fetch_stock import fetch_intraday_kline, fetch_stocks


STRATEGY_HEADER_HINTS = ("代码", "名称", "交易策略", "入场条件")
SHADOW_BANDS = {
    "MA20_ZONE": ("ma20", 0.5),
    "MA10_ZONE": ("ma10", 0.4),
    "MA5_ZONE": ("ma5", 0.5),
}


def split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", "").strip()
    if text in ("", "-", "—", "None"):
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(m.group()) if m else None


def round2(value: float | None) -> float | None:
    return round(value, 2) if value is not None else None


def pct(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator * 100


def normalize_date(date: str) -> str:
    return date.replace("-", "")


def parse_regime(text: str) -> str:
    m = re.search(r"RegimeHint:\s*`?([A-Za-z\-]+)`?", text)
    return m.group(1).strip().lower() if m else "unknown"


def _nested_value(entry: dict[str, Any], section: str, field: str) -> Any:
    cell = entry.get(section, {}).get(field)
    if isinstance(cell, dict):
        return cell.get("value")
    return cell


def load_pool_indicators(path: Path | None) -> dict[str, dict[str, Any]]:
    if not path or not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"pool_indicators must be a list: {path}")
    return {
        e["code"]: e
        for e in data
        if isinstance(e, dict) and isinstance(e.get("code"), str)
    }


def rows_from_codes(codes: list[str]) -> list[dict[str, Any]]:
    rows = []
    for code in codes:
        code = code.strip()
        if not code:
            continue
        if not re.match(r"^(sh|sz)\d{6}$", code):
            raise ValueError(f"Unsupported code for daily verification: {code}")
        rows.append({
            "code": code,
            "代码": code,
            "名称": None,
            "板块": None,
            "方向": None,
            "评级": None,
            "交易策略": None,
            "入场条件": None,
            "仓位": None,
            "持仓": None,
            "anchor_kind": None,
        })
    if not rows:
        raise ValueError("--codes did not contain any valid sh/sz codes")
    return rows


def rows_from_strategy_json(path: Path) -> tuple[str, list[dict[str, Any]]]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise ValueError(f"strategy_json root must be object: {path}")
    regime = doc.get("market", {}).get("regime_hint") or "unknown"
    rows = []
    for stock in doc.get("stocks", []):
        if not isinstance(stock, dict):
            continue
        code = stock.get("code")
        if not isinstance(code, str) or not re.match(r"^(sh|sz)\d{6}$", code):
            continue
        anchor = stock.get("anchor")
        rows.append({
            "code": code,
            "代码": code,
            "名称": stock.get("name"),
            "板块": stock.get("sector"),
            "方向": stock.get("direction"),
            "评级": stock.get("rating"),
            "交易策略": stock.get("entry_profile"),
            "入场条件": stock.get("entry_trigger"),
            "仓位": stock.get("position_budget"),
            "持仓": stock.get("horizon"),
            "anchor_kind": None if anchor in (None, "无", "—") else anchor,
            "strategy_json": stock,
        })
    if not rows:
        raise ValueError(f"No valid stocks in strategy_json: {path}")
    return regime, rows


def parse_strategy(strategy_path: Path) -> tuple[str, list[dict[str, Any]]]:
    text = strategy_path.read_text(encoding="utf-8")
    regime = parse_regime(text)
    rows: list[dict[str, Any]] = []

    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not (line.startswith("|") and all(h in line for h in STRATEGY_HEADER_HINTS)):
            continue
        header = split_row(line)
        idx = {name: next((j for j, h in enumerate(header) if name in h), None)
               for name in ("代码", "名称", "板块", "方向", "评级", "交易策略", "入场条件", "仓位", "持仓")}
        j = i + 2
        while j < len(lines) and lines[j].startswith("|") and "---" not in lines[j]:
            cells = split_row(lines[j])
            code_i = idx.get("代码")
            if code_i is None or code_i >= len(cells):
                j += 1
                continue
            code = cells[code_i]
            if not re.match(r"^(sh|sz)\d{6}$", code):
                j += 1
                continue
            row = {"code": code}
            for key, pos in idx.items():
                if pos is not None and pos < len(cells):
                    row[key] = cells[pos]
            row["anchor_kind"] = infer_anchor_kind(row.get("入场条件", ""), row.get("交易策略", ""))
            rows.append(row)
            j += 1
        break

    if not rows:
        raise ValueError(f"No strategy table found in {strategy_path}")
    return regime, rows


def infer_anchor_kind(entry_condition: str, strategy: str) -> str | None:
    text = f"{entry_condition} {strategy}".upper()
    if "暂不参与" in strategy:
        return None
    if "MA5" in text:
        return "MA5"
    if "MA10" in text:
        return "MA10"
    if "MA20" in text:
        return "MA20"
    if "OPEN" in text or "竞价" in entry_condition or "开盘" in entry_condition:
        return "OPEN"
    if "追" in entry_condition:
        return "OPEN"
    return None


def fetch_daily_records(code: str, date: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str | None]:
    end = normalize_date(date)
    warnings = None
    records = fetch_history(code, end=end, range_str="6m", use_cache=False, source="sohu")
    if not records:
        records = fetch_history(code, end=end, range_str="6m", use_cache=False, source="sina")
    if not records:
        return None, [], "history_fetch_failed"
    day = next((r for r in records if str(r.get("date")) == date), None)
    if day is None:
        # Current-day historical K may be absent before EOD. Fallback to quote.
        quote = next((r for r in fetch_stocks([code]) if "error" not in r), None)
        if quote:
            day = {
                "date": date,
                "open": quote.get("open"),
                "high": quote.get("high"),
                "low": quote.get("low"),
                "close": quote.get("price"),
                "volume": quote.get("volume"),
                "change_pct": quote.get("percent"),
            }
            warnings = "daily_history_missing_used_realtime_quote"
    return day, records, warnings


def compute_prior_indicators(
    records: list[dict[str, Any]],
    date: str,
    pool_entry: dict[str, Any] | None = None,
) -> dict[str, float | None]:
    if pool_entry:
        raw = pool_entry.get("raw_observation", {})
        ma5 = _nested_value(pool_entry, "raw_observation", "ma5")
        ma20 = _nested_value(pool_entry, "raw_observation", "ma20")
        atr = _nested_value(pool_entry, "raw_observation", "atr")
        # pool_indicators currently does not include MA10; compute it below when possible.
        pooled = {
            "ma5": round2(to_float(ma5)),
            "ma10": None,
            "ma20": round2(to_float(ma20)),
            "atr": round2(to_float(atr)),
        }
    else:
        pooled = {"ma5": None, "ma10": None, "ma20": None, "atr": None}

    prior = [r for r in records if str(r.get("date")) < date]
    closes = [parse_value(r.get("close")) or 0 for r in prior]
    highs = [parse_value(r.get("high")) or 0 for r in prior]
    lows = [parse_value(r.get("low")) or 0 for r in prior]
    if not prior:
        return pooled
    ma5 = calc_sma(closes, 5)[-1] if len(closes) >= 5 else None
    ma10 = calc_sma(closes, 10)[-1] if len(closes) >= 10 else None
    ma20 = calc_sma(closes, 20)[-1] if len(closes) >= 20 else None
    atr = calc_atr(highs, lows, closes, 14)[-1] if len(closes) >= 15 else None
    return {
        "ma5": pooled["ma5"] if pooled["ma5"] is not None else round2(ma5),
        "ma10": round2(ma10),
        "ma20": pooled["ma20"] if pooled["ma20"] is not None else round2(ma20),
        "atr": pooled["atr"] if pooled["atr"] is not None else round2(atr),
    }


def first_candle_state(code: str, date: str, anchor: float | None = None) -> tuple[str | None, dict[str, Any] | None, str | None]:
    try:
        rows = fetch_intraday_kline(code, scale=5, days=1)
    except Exception as exc:  # noqa: BLE001 - data fetcher exceptions should become warnings
        return None, None, f"intraday_fetch_failed:{exc}"
    if not rows:
        return None, None, "intraday_empty"
    first = rows[0]
    o, c, low = to_float(first.get("open")), to_float(first.get("close")), to_float(first.get("low"))
    state = "中性"
    if c is not None and o is not None:
        if anchor is not None:
            # "企稳" includes reclaim attempts that close near the anchor after
            # an intraday probe. The human review treats a bullish first 5m bar
            # within 1% below anchor as stabilization, not a clean breakdown.
            if c >= anchor or (c >= o and c >= anchor * 0.99):
                state = "企稳"
            elif low is not None and low < anchor and c < anchor:
                state = "击穿"
        else:
            state = "企稳" if c >= o else "击穿"
    return state, first, None


def actual_entry(anchor_kind: str | None, indicators: dict[str, float | None], day: dict[str, Any], strategy: str) -> dict[str, Any]:
    if not anchor_kind and strategy in (None, ""):
        return {
            "anchor_kind": None,
            "anchor_price": None,
            "touched": None,
            "result": "not_applicable_codes_only",
        }
    if not anchor_kind or strategy == "暂不参与":
        return {
            "anchor_kind": None,
            "anchor_price": None,
            "touched": None,
            "result": "观望",
        }
    anchor_map = {
        "MA5": indicators.get("ma5"),
        "MA10": indicators.get("ma10"),
        "MA20": indicators.get("ma20"),
        "OPEN": to_float(day.get("open")),
    }
    anchor = anchor_map.get(anchor_kind)
    low, close, open_ = to_float(day.get("low")), to_float(day.get("close")), to_float(day.get("open"))
    touched = bool(anchor is not None and low is not None and low <= anchor)
    hold = pct((close - anchor) if (touched and close is not None and anchor is not None) else None, anchor)
    mae = pct((low - anchor) if (touched and low is not None and anchor is not None) else None, anchor)
    if touched:
        result = "成功" if hold is not None and hold > 0 else "失败"
    else:
        result = "踏空" if open_ is not None and close is not None and close > open_ else "观望正确"
    return {
        "anchor_kind": anchor_kind,
        "anchor_price": round2(anchor),
        "touched": touched,
        "hold_pct": round2(hold),
        "mae_pct": round2(mae),
        "result": result,
    }


def simulate_band(lo: float | None, hi: float | None, day: dict[str, Any], enabled: bool = True) -> dict[str, Any]:
    low, high, close, open_ = (to_float(day.get(k)) for k in ("low", "high", "close", "open"))
    if not enabled or lo is None or hi is None:
        return {"enabled": False, "lo": round2(lo), "hi": round2(hi), "touched": None}
    touched = low is not None and low <= hi and (high is None or high >= lo)
    entry = hi
    hold = pct((close - entry) if (touched and close is not None) else None, entry)
    mae = pct((low - entry) if (touched and low is not None) else None, entry)
    missed_upside = None
    avoided_loss = None
    if not touched and close is not None and open_ is not None:
        if close > open_:
            missed_upside = pct(close - open_, open_)
        else:
            avoided_loss = pct(open_ - close, open_)
    return {
        "enabled": True,
        "lo": round2(lo),
        "hi": round2(hi),
        "touched": bool(touched),
        "entry_price": round2(entry) if touched else None,
        "hold_pct": round2(hold),
        "mae_pct": round2(mae),
        "missed_upside_pct": round2(missed_upside),
        "avoided_loss_pct": round2(avoided_loss),
    }


def shadow_bands(indicators: dict[str, float | None], day: dict[str, Any], first_k_state: str | None) -> dict[str, Any]:
    atr = indicators.get("atr")
    bands: dict[str, Any] = {}
    for name, (field, mult) in SHADOW_BANDS.items():
        anchor = indicators.get(field)
        hi = anchor + mult * atr if anchor is not None and atr is not None else None
        bands[name] = simulate_band(anchor, hi, day)
    open_ = to_float(day.get("open"))
    hi = open_ + 0.3 * atr if open_ is not None and atr is not None else None
    bands["OPEN_CONFIRM"] = simulate_band(open_, hi, day, enabled=(first_k_state == "企稳"))
    return bands


def build_verification(
    date: str,
    strategy_path: Path | None,
    codes: list[str] | None = None,
    regime_hint: str | None = None,
    pool_indicators_path: Path | None = None,
    strategy_json_path: Path | None = None,
) -> dict[str, Any]:
    if strategy_json_path:
        regime, strategy_rows = rows_from_strategy_json(strategy_json_path)
    elif codes:
        regime = regime_hint or "unknown"
        strategy_rows = rows_from_codes(codes)
    elif strategy_path:
        regime, strategy_rows = parse_strategy(strategy_path)
    else:
        raise ValueError("Either --codes or --strategy is required")
    pool = load_pool_indicators(pool_indicators_path)
    stocks = []
    warnings: list[str] = []

    for row in strategy_rows:
        code = row["code"]
        day, history, warning = fetch_daily_records(code, date)
        if warning:
            warnings.append(f"{code}:{warning}")
        if not day:
            stocks.append({"code": code, "fetch_failed": True, "strategy": row})
            warnings.append(f"{code}:no_daily_ohlc")
            continue

        pool_entry = pool.get(code)
        indicators = compute_prior_indicators(history, date, pool_entry)
        prelim_entry = actual_entry(row.get("anchor_kind"), indicators, day, row.get("交易策略", ""))
        first_state, first_k, first_warning = first_candle_state(code, date, prelim_entry.get("anchor_price"))
        if first_warning:
            warnings.append(f"{code}:{first_warning}")
        entry = actual_entry(row.get("anchor_kind"), indicators, day, row.get("交易策略", ""))

        high, close = to_float(day.get("high")), to_float(day.get("close"))
        anchor = entry.get("anchor_price")
        giveback = pct(high - close, anchor) if entry.get("touched") and high is not None and close is not None else None

        stocks.append({
            "code": code,
            "name": row.get("名称"),
            "sector": row.get("板块"),
            "direction": row.get("方向"),
            "rating": row.get("评级"),
            "strategy": row.get("交易策略"),
            "entry_condition": row.get("入场条件"),
            "position_budget": row.get("仓位"),
            "horizon": row.get("持仓"),
            "prices": {
                "open": round2(to_float(day.get("open"))),
                "low": round2(to_float(day.get("low"))),
                "high": round2(to_float(day.get("high"))),
                "close": round2(to_float(day.get("close"))),
                "volume": to_float(day.get("volume")),
                "change_pct": to_float(day.get("change_pct")),
            },
            "indicators": indicators,
            "first_5m": {
                "state": first_state,
                "raw": first_k,
            },
            "actual_entry": {
                **entry,
                "profit_giveback_pct": round2(giveback),
            },
            "shadow_bands": shadow_bands(indicators, day, first_state),
            "pool_indicators_available": pool_entry is not None,
            "strategy_profile": row.get("strategy_json"),
        })

    return {
        "schema_version": "daily_verification.v1",
        "date": date,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": {
            "strategy_path": str(strategy_path).replace("\\", "/") if strategy_path else None,
            "strategy_json_path": str(strategy_json_path).replace("\\", "/") if strategy_json_path else None,
            "pool_indicators_path": str(pool_indicators_path).replace("\\", "/") if pool_indicators_path else None,
            "codes_input": codes,
            "depends_on_verification_md": False,
            "script_parsed_strategy_md": (not bool(codes) and not bool(strategy_json_path)),
        },
        "market": {
            "regime_hint": regime,
        },
        "stocks": stocks,
        "warnings": warnings,
    }


def main() -> None:
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Generate verification.json without reading verification.md")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument(
        "--codes",
        help="Comma-separated recommendation codes. Preferred mode: LLM reads strategy.md and passes codes here.",
    )
    parser.add_argument("--regime", help="RegimeHint to store when using --codes")
    parser.add_argument(
        "--strategy-json",
        help="Preferred structured strategy input: predict/{date}/strategy.json",
    )
    parser.add_argument(
        "--pool-indicators",
        help="pool_indicators.json path; default predict/{date}/pool_indicators.json if present",
    )
    parser.add_argument("--strategy", help="Strategy markdown path; fallback only when --codes is omitted")
    parser.add_argument("-o", "--output", help="Output JSON path; default memory/daily/{date}/verification.json")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    args = parser.parse_args()

    strategy_json_path = Path(args.strategy_json) if args.strategy_json else ROOT / "predict" / args.date / "strategy.json"
    if not strategy_json_path.exists():
        strategy_json_path = None
    codes = [c.strip() for c in args.codes.split(",") if c.strip()] if args.codes else None
    strategy_path = None
    if not codes and not strategy_json_path:
        strategy_path = Path(args.strategy) if args.strategy else ROOT / "predict" / args.date / "strategy.md"
    output_path = Path(args.output) if args.output else ROOT / "memory" / "daily" / args.date / "verification.json"
    pool_path = Path(args.pool_indicators) if args.pool_indicators else ROOT / "predict" / args.date / "pool_indicators.json"
    if not pool_path.exists():
        pool_path = None
    if strategy_path and not strategy_path.exists():
        raise SystemExit(f"[ERROR] Strategy file not found: {strategy_path}")

    data = build_verification(
        date=args.date,
        strategy_path=strategy_path,
        codes=codes,
        regime_hint=args.regime,
        pool_indicators_path=pool_path,
        strategy_json_path=strategy_json_path,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2 if args.pretty else None),
        encoding="utf-8",
        newline="\n",
    )
    print(f"Saved {output_path}")
    if data["warnings"]:
        print(f"Warnings: {len(data['warnings'])}")
        for warning in data["warnings"][:20]:
            print(f"  - {warning}")


if __name__ == "__main__":
    main()
