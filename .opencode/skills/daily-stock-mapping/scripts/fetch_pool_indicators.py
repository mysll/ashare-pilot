#!/usr/bin/env python3
"""Fetch technical indicators and compute feature engineering for a pool of stocks. V5.

Used by daily-stock-mapping Phase 2 Technical Enrichment.
Outputs V5 nested JSON (raw_observation + computed_perception) with per-field confidence:
  - raw_observation (19 fields): {value, confidence} per field  (raw data = 100% confidence)
  - computed_perception: tech_score / traditional / sentiment / risk_type / risk_flags
    each with {value, confidence, trace} where confidence reflects data completeness
  - On fetch failure: {"code", "fetch_failed": true, "raw_observation": {}, "computed_perception": {}}

All numeric values are float/int — no string-formatted values like "14.38%".

Usage:
    python fetch_pool_indicators.py sh600519,sz000001,sz002156 --json
    python fetch_pool_indicators.py sh600519,sz000001 --json -o results.json
"""

import argparse
import json
import sys
from pathlib import Path

_scripts_dir = Path(__file__).resolve().parent.parent.parent / "stock-analysis" / "scripts"
sys.path.insert(0, str(_scripts_dir))
from fetch_history import fetch_history  # noqa: E402
from fetch_indicators import calculate_indicators  # noqa: E402

INDICATOR_LIST = [
    "rsi", "macd", "macdh", "close_50_sma",
    "boll", "boll_ub", "boll_lb", "atr",
]

# Map indicator field names → pipeline-friendly output names
_INDICATOR_RENAME = {
    "boll": "ma20",
    "close_50_sma": "ma50",
}


def _to_float(val):
    """Convert string value to float, stripping '%' and ','. Returns None on failure."""
    if val is None or val == "" or val == "-":
        return None
    if isinstance(val, (int, float)):
        return float(val)
    try:
        return float(str(val).replace("%", "").replace(",", ""))
    except (ValueError, TypeError):
        return None


def _get_board_limit(code: str) -> float:
    """Return limit-up threshold for a stock board."""
    if code.startswith("sz30") or code.startswith("sh688"):
        return 20.0
    if code.startswith("bj"):
        return 30.0
    return 10.0


# ── V5 risk_type mapping ──
_RISK_TYPE_MAP = {
    "RSI>75": "overbought",
    "RSI<30": "oversold_opportunity",
    "MA双熊": "trend_weak",
    "炸板": "broken_board",
}


def _map_risk_type(flags):
    """Map V4-U risk_flags to V5 risk_type list."""
    types = []
    for f in flags:
        t = _RISK_TYPE_MAP.get(f)
        if t and t not in types:
            types.append(t)
    return types


# V5 raw_observation field list (order preserved)
_RAW_FIELDS = [
    "price", "close", "turnover", "change_pct", "amount",
    "rsi", "macd", "macdh", "ma20", "ma50", "ma5",
    "boll_ub", "boll_lb", "atr",
    "high20", "low20", "atr_pct", "percent_b",
    "board_streak", "seal_quality", "limit_up_freq",
    "prev_close", "dist_ma20_atr", "position_state", "yesterday_limit_up",
    "vol_ratio_5d", "market_sentiment",
]


def _to_v5_nested(code, row, trad_present_count):
    """Convert V4-U flat row to V5 nested {raw_observation, computed_perception}."""
    # ── raw_observation ──
    raw = {}
    for f in _RAW_FIELDS:
        v = row.get(f)
        raw[f] = {"value": v, "confidence": 100 if v is not None else 0}

    # ── computed_perception ──
    ts = row.get("tech_score")
    trad = row.get("traditional")
    sent = row.get("sentiment")
    risk_flags = row.get("risk_flags", [])
    risk_types = _map_risk_type(risk_flags)

    # tech_score confidence = present factors / 6
    ts_conf = round(trad_present_count / 6 * 100) if ts is not None else 0
    ts_trace = f"present_factors={trad_present_count}/6; renormalized; trad{trad}×0.70+sent{sent}×0.30={ts}" if ts is not None else None

    # traditional trace
    trad_trace = f"present_factors={trad_present_count}/6; weights renormalized" if trad is not None else None

    cp = {
        "tech_score": {"value": ts, "confidence": ts_conf, "trace": ts_trace} if ts is not None else {"value": None, "confidence": 0, "trace": None},
        "traditional": {"value": trad, "confidence": ts_conf, "trace": trad_trace} if trad is not None else {"value": None, "confidence": 0, "trace": None},
        "sentiment": {"value": sent, "confidence": 100 if sent is not None else 0},
        "risk_type": {"value": risk_types, "confidence": 100},
        "risk_flags": {"value": risk_flags, "confidence": 100},
    }

    return {
        "code": code,
        "fetch_failed": False,
        "raw_observation": raw,
        "computed_perception": cp,
    }


def _raw_num(raw, field, default=0):
    """Extract numeric value from V5 raw_observation[field]."""
    entry = raw.get(field, {})
    v = entry.get("value") if isinstance(entry, dict) else entry
    return v if v is not None else default


def main():
    import time
    _t0 = time.time()

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="Fetch indicators and feature engineering for stock pool"
    )
    parser.add_argument("codes", help="Comma-separated stock codes")
    parser.add_argument("--json", action="store_true", help="Output as flat JSON array")
    parser.add_argument("-o", "--output", metavar="FILE", help="Save output to file")
    parser.add_argument(
        "--source", choices=["sohu", "sina"], default="sina",
        help="Data source (default: sina)"
    )

    args = parser.parse_args()
    codes = [c.strip() for c in args.codes.split(",") if c.strip()]

    results = []
    for code in codes:
        try:
            records = fetch_history(code, range_str="3m", source=args.source)
            if not records:
                print(f"[SKIP] {code}: no data", file=sys.stderr)
                # P0-7 / V5: placeholder for Observation Pool routing
                results.append({
                    "code": code, "fetch_failed": True,
                    "raw_observation": {}, "computed_perception": {},
                })
                continue

            indicators = calculate_indicators(records, INDICATOR_LIST)
            last_idx = len(records) - 1
            last = records[last_idx]

            # ── Raw indicators ──────────────────────────────
            row: dict = {"code": code}

            # Price / K-line fields (float, no string formatting)
            close_val = _to_float(last["close"])
            row["price"] = close_val
            row["close"] = close_val
            row["turnover"] = _to_float(last.get("turnover"))
            row["change_pct"] = _to_float(last.get("change_pct"))
            row["amount"] = _to_float(last.get("amount"))

            # Indicator fields with renamed keys
            for ind_name in INDICATOR_LIST:
                output_name = _INDICATOR_RENAME.get(ind_name, ind_name)
                row[output_name] = indicators[ind_name][last_idx]

            # ── Feature engineering ─────────────────────────

            # high20 / low20
            window = records[-20:]
            highs = [_to_float(r["high"]) for r in window]
            lows = [_to_float(r["low"]) for r in window]
            highs = [v for v in highs if v is not None]
            lows = [v for v in lows if v is not None]
            row["high20"] = max(highs) if highs else None
            row["low20"] = min(lows) if lows else None

            # atr_pct
            atr_val = row.get("atr")
            row["atr_pct"] = (atr_val / close_val * 100) if (
                atr_val is not None and close_val is not None and close_val != 0
            ) else None

            # percent_b
            ub = row.get("boll_ub")
            lb = row.get("boll_lb")
            row["percent_b"] = (close_val - lb) / (ub - lb) if (
                ub is not None and lb is not None and
                close_val is not None and ub != lb
            ) else None

            # board_streak: consecutive limit-up days ending at last record
            board_limit = _get_board_limit(code)
            threshold = board_limit * 0.95
            streak = 0
            for i in range(last_idx, -1, -1):
                pct = _to_float(records[i].get("change_pct"))
                if pct is not None and pct >= threshold:
                    streak += 1
                else:
                    break
            row["board_streak"] = streak

            # seal_quality: only meaningful if last day was limit-up
            last_pct = row["change_pct"]
            if last_pct is not None and last_pct >= threshold:
                high_val = _to_float(last.get("high"))
                if high_val is not None and high_val > 0 and close_val is not None:
                    ratio = close_val / high_val
                    if ratio >= 0.999:
                        row["seal_quality"] = "封死"
                    elif ratio >= 0.98:
                        row["seal_quality"] = "未封板"
                    else:
                        row["seal_quality"] = "炸板"
                else:
                    row["seal_quality"] = "—"
            else:
                row["seal_quality"] = "—"

            # ── Scoring (formula-based, no LLM reasoning) ────

            # limit_up_freq: total limit-up days in last 10 records
            freq = 0
            for i in range(max(0, last_idx - 9), last_idx + 1):
                pct = _to_float(records[i].get("change_pct"))
                if pct is not None and pct >= threshold:
                    freq += 1
            row["limit_up_freq"] = freq

            # ── V1.1 Trade Profile fields ────────────────────

            # ma5: 5-day simple moving average from last 5 daily closes
            ma5_window = records[-5:]
            ma5_closes = [_to_float(r["close"]) for r in ma5_window]
            ma5_closes = [v for v in ma5_closes if v is not None]
            row["ma5"] = sum(ma5_closes) / len(ma5_closes) if ma5_closes else None

            # prev_close: yesterday's close
            if last_idx > 0:
                row["prev_close"] = _to_float(records[last_idx - 1].get("close"))
            else:
                row["prev_close"] = None

            # dist_ma20_atr: distance from MA20 in ATR multiples
            atr_v = row.get("atr")
            m20_v = row.get("ma20")
            row["dist_ma20_atr"] = (close_val - m20_v) / atr_v if (
                close_val is not None and m20_v is not None and
                atr_v is not None and atr_v != 0
            ) else None

            # position_state: PULLBACK | TREND | EXTENDED | GAP_UP
            da = row["dist_ma20_atr"]
            hs = row.get("high20")
            bs_val = row["board_streak"]
            if da is not None:
                if da <= 1.0:
                    row["position_state"] = "PULLBACK"
                elif da <= 2.5:
                    row["position_state"] = "TREND"
                else:
                    row["position_state"] = "EXTENDED"
                if (bs_val is not None and bs_val >= 2 and
                        hs is not None and close_val is not None and
                        close_val >= hs * 0.98):
                    row["position_state"] = "EXTENDED"
            else:
                row["position_state"] = None

            # yesterday_limit_up: whether yesterday hit limit-up (>= 95% of board limit)
            if last_idx > 0:
                prev_pct = _to_float(records[last_idx - 1].get("change_pct"))
                row["yesterday_limit_up"] = (
                    prev_pct is not None and prev_pct >= threshold
                )
            else:
                row["yesterday_limit_up"] = False

            # Traditional technical sub-score (6 factors)
            p = row["price"]
            m20 = row.get("ma20")
            m50 = row.get("ma50")
            mh = row.get("macdh")
            # prev_mh used for MACD acceleration detection (P0-1)
            prev_mh = None
            _macdh_series = indicators.get("macdh")
            if _macdh_series and last_idx > 0:
                prev_mh = _to_float(_macdh_series[last_idx - 1])
            rs = row.get("rsi")
            amt = row.get("amount")
            pb = row.get("percent_b")
            ap = row.get("atr_pct")

            # MA Trend (22%) — P0-2: 加 "P<ma20, ma20>ma50=40" 回踩中期多头分支
            if m20 is not None and m50 is not None and p is not None:
                if p > m20 > m50:
                    ma_s = 100
                elif p > m20:           # P>m20 但 ma20<=ma50
                    ma_s = 60
                elif m20 > m50:         # P<=ma20 但中期多头 → 回踩
                    ma_s = 40
                else:                   # P<ma20 且 ma20<ma50 → 双熊
                    ma_s = 0
            else:
                ma_s = None

            # MACD Mom (19%) — P0-1: 5 级评分（加速/正/crossing/负/deepening）
            if mh is None:
                mac_s = None
            elif mh > 0 and prev_mh is not None and mh > prev_mh:
                mac_s = 100              # 加速 (histogram 正且递增)
            elif mh > 0:
                mac_s = 75               # macdh > 0
            elif abs(mh) < 0.05:         # crossing 0（阈值 0.05，Open Question）
                mac_s = 50
            elif mh < 0 and prev_mh is not None and mh < prev_mh:
                mac_s = 0                # deepening（负且 |mh| 递增）
            else:                        # mh < 0 但非 deepening
                mac_s = 25

            # RSI (13%)
            if rs is None:
                rsi_s = None
            elif 45 <= rs <= 60:
                rsi_s = 100
            elif 60 < rs <= 70:
                rsi_s = 80
            elif 30 <= rs < 45:
                rsi_s = 70
            elif 70 < rs <= 75:
                rsi_s = 40
            else:                        # >75 或 <30
                rsi_s = 0

            # Liquidity (22%) — amount in 万元 → 1亿 = 10000万
            if amt is None:
                liq_s = None
            else:
                yi = amt / 10000
                if yi >= 5:    liq_s = 100
                elif yi >= 3:  liq_s = 70
                elif yi >= 1:  liq_s = 40
                else:          liq_s = 0

            # BB Position (16%)
            if pb is None:
                bb_s = None
            elif 0.4 <= pb <= 0.6:
                bb_s = 100
            elif 0.6 < pb <= 0.8:
                bb_s = 80
            elif 0.2 <= pb < 0.4:
                bb_s = 70
            elif pb > 0.8:
                bb_s = 60
            else:
                bb_s = 20

            # ATR Risk (9%)
            if ap is None:
                atr_s = None
            elif 1.5 <= ap <= 3:
                atr_s = 100
            elif 3 < ap <= 5:
                atr_s = 70
            elif ap < 1.5:
                atr_s = 60
            else:                          # >5
                atr_s = 30

            # P0-4: 缺失因子按权重重归一，不再静默填 50
            trad_factors = [
                (0.22, ma_s), (0.19, mac_s), (0.13, rsi_s),
                (0.22, liq_s), (0.16, bb_s), (0.09, atr_s),
            ]
            trad_present = [(w, s) for w, s in trad_factors if s is not None]
            if trad_present:
                total_w = sum(w for w, _ in trad_present)
                traditional = sum(s * w / total_w for w, s in trad_present)
                row["traditional"] = round(traditional, 1)
            else:
                traditional = None
                row["traditional"] = None
            trad_present_count = len(trad_present)

            # ── Market Sentiment (非板情绪因子) ─────────────────
            # F1: Turnover Rate score
            tov = row.get("turnover")
            if tov is not None:
                if tov >= 10:       tov_s = 100
                elif tov >= 5:      tov_s = 85
                elif tov >= 3:      tov_s = 70
                elif tov >= 1:      tov_s = 55
                elif tov >= 0.5:    tov_s = 35
                else:               tov_s = 20
            else:
                tov_s = 50

            # F2: High20 Proximity score
            h20 = row.get("high20")
            p   = row.get("price")
            if h20 is not None and p is not None and h20 > 0:
                h20_ratio = p / h20
                if   h20_ratio >= 0.99:  h20_s = 100
                elif h20_ratio >= 0.95:  h20_s = 85
                elif h20_ratio >= 0.88:  h20_s = 65
                elif h20_ratio >= 0.75:  h20_s = 45
                else:                    h20_s = 25
            else:
                h20_s = 50

            # F3: Volume Ratio (5-day avg amount ratio)
            if len(records) >= 6:
                prev_amounts = [_to_float(records[i].get("amount")) for i in range(last_idx - 5, last_idx)]
                prev_amounts = [a for a in prev_amounts if a is not None and a > 0]
                if prev_amounts:
                    avg_amt_5d = sum(prev_amounts) / len(prev_amounts)
                    vol_ratio = (row["amount"] or 0) / avg_amt_5d
                else:
                    vol_ratio = None
            else:
                vol_ratio = None

            if vol_ratio is not None:
                if   vol_ratio >= 2.0:  vol_s = 100
                elif vol_ratio >= 1.5:  vol_s = 85
                elif vol_ratio >= 1.2:  vol_s = 70
                elif vol_ratio >= 0.8:  vol_s = 50
                elif vol_ratio >= 0.5:  vol_s = 35
                else:                   vol_s = 20
            else:
                vol_s = 50

            row["vol_ratio_5d"] = round(vol_ratio, 3) if vol_ratio is not None else None
            market_sentiment = round(tov_s * 0.40 + h20_s * 0.35 + vol_s * 0.25, 1)
            row["market_sentiment"] = market_sentiment

            # ── Board Sentiment (vs4 formula, unchanged) ──────
            bs = row["board_streak"]
            lf = row["limit_up_freq"]
            sq = row["seal_quality"]

            if bs >= 3:    streak_s = 100
            elif bs == 2: streak_s = 85
            elif bs == 1: streak_s = 65
            else:         streak_s = 0

            if lf >= 3:    freq_s = 100
            elif lf == 2:  freq_s = 80
            elif lf == 1:  freq_s = 60
            else:          freq_s = 0

            if sq == "封死":    seal_s = 100
            elif sq == "未封板": seal_s = 60
            elif sq == "炸板":   seal_s = 15
            else:               seal_s = 0

            board_sentiment = streak_s * 0.50 + freq_s * 0.25 + seal_s * 0.25
            sentiment = round(max(board_sentiment, market_sentiment), 1)
            row["sentiment"] = sentiment

            # tech_score — traditional 缺失则 tech_score=None
            if traditional is None:
                row["tech_score"] = None
            else:
                row["tech_score"] = round(traditional * 0.70 + sentiment * 0.30, 1)

            # risk_flags — P0-3: 删除"流动性<3亿"注入（hard filter 已在 SKILL 层处理）
            flags = []
            if rs is not None and rs > 75: flags.append("RSI>75")
            if rs is not None and rs < 30: flags.append("RSI<30")
            if ap is not None and ap > 8: flags.append("ATR>8%")
            if m20 is not None and m50 is not None and p is not None:
                if p < m20 and m20 < m50:
                    flags.append("MA双熊")
            if sq == "炸板":
                flags.append("炸板")
            row["risk_flags"] = flags

            # ── V5 nested conversion ──
            result = _to_v5_nested(code, row, trad_present_count)
            results.append(result)

        except Exception as e:
            print(f"[ERROR] {code}: {e}", file=sys.stderr)
            # P0-7 / V5: placeholder row for SKILL Observation Pool routing
            results.append({
                "code": code, "fetch_failed": True,
                "raw_observation": {}, "computed_perception": {},
            })
            continue

    # ── Output ─────────────────────────────────────────────
    _elapsed = time.time() - _t0
    print(f"[DONE] {len(results)}/{len(codes)} stocks in {_elapsed:.1f}s", file=sys.stderr)
    if args.json:
        output_str = json.dumps(results, ensure_ascii=False, indent=2)
    else:
        if not results:
            output_str = "No data."
        else:
            lines = [
                f"{'Code':<12} {'Price':>8} {'Chg%':>7} {'RSI':>6} {'ATR':>6} "
                f"{'MA20':>8} {'Tech':>6} {'Conf%':>6} {'Streak':>6} {'RiskType'}"
            ]
            lines.append("-" * len(lines[0]))
            for r in results:
                if r.get("fetch_failed"):
                    lines.append(f"{r['code']:<12}  [indicators_fetch_failed]")
                    continue
                raw = r.get("raw_observation", {})
                cp = r.get("computed_perception", {})
                ts = cp.get("tech_score", {})
                ts_v = ts.get("value")
                ts_conf = ts.get("confidence", 0)
                rt = cp.get("risk_type", {}).get("value", [])
                rt_fmt = ",".join(rt) if rt else "—"
                ts_fmt = f"{ts_v:>6.1f}" if ts_v is not None else f"{'--':>6}"
                conf_fmt = f"{ts_conf:>5.0f}%" if ts_conf else f"{'--':>6}"
                vals = [
                    r["code"],
                    f"{_raw_num(raw, 'price'):>8.2f}",
                    f"{_raw_num(raw, 'change_pct'):>7.2f}",
                    f"{_raw_num(raw, 'rsi'):>6.1f}",
                    f"{_raw_num(raw, 'atr'):>6.2f}",
                    f"{_raw_num(raw, 'ma20'):>8.2f}",
                    ts_fmt,
                    conf_fmt,
                    f"{_raw_num(raw, 'board_streak'):>6.0f}",
                    rt_fmt,
                ]
                lines.append(" ".join(vals))
            output_str = "\n".join(lines)

    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            f.write(output_str)
        print(f"Saved to {args.output}")
    else:
        print(output_str)


if __name__ == "__main__":
    main()
