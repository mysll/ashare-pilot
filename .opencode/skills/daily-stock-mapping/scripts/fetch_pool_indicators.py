#!/usr/bin/env python3
"""Fetch technical indicators and compute feature engineering for a pool of stocks.

Used by daily-stock-mapping Phase 2 Technical Enrichment.
Outputs a flat JSON array with 25 fields per stock:
  - 14 raw indicators (code, price, close, turnover, change_pct, amount,
    rsi, atr, ma20, ma50, macd, macdh, boll_ub, boll_lb)
  - 6 pre-computed features (high20, low20, atr_pct, percent_b, board_streak, seal_quality)
  - 5 scoring fields (limit_up_freq, traditional, sentiment, tech_score, risk_flags)

All numeric fields are float/int — no string-formatted values like "14.38%".

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
    if code.startswith("sz30"):
        return 20.0
    return 10.0


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="Fetch indicators and feature engineering for stock pool"
    )
    parser.add_argument("codes", help="Comma-separated stock codes")
    parser.add_argument("--json", action="store_true", help="Output as flat JSON array")
    parser.add_argument("-o", "--output", metavar="FILE", help="Save output to file")

    args = parser.parse_args()
    codes = [c.strip() for c in args.codes.split(",") if c.strip()]

    results = []
    for code in codes:
        try:
            records = fetch_history(code, range_str="3m")
            if not records:
                print(f"[SKIP] {code}: no data", file=sys.stderr)
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

            # Traditional technical sub-score (6 factors)
            p = row["price"]
            m20 = row.get("ma20")
            m50 = row.get("ma50")
            mh = row.get("macdh")
            rs = row.get("rsi")
            amt = row.get("amount")
            pb = row.get("percent_b")
            ap = row.get("atr_pct")

            def _sc(v, default=50):
                return default if v is None else v

            # MA Trend (22%)
            if m20 is not None and m50 is not None:
                ma_s = 100 if p > m20 > m50 else (60 if p > m20 else 0)
            else:
                ma_s = 50
            # MACD Mom (19%)
            if mh is not None:
                mac_s = 75 if mh > 0 else 25
            else:
                mac_s = 50
            # RSI (13%)
            if rs is not None:
                rsi_s = 100 if 45 <= rs <= 60 else (80 if 60 < rs <= 70 else (70 if 30 <= rs < 45 else (40 if 70 < rs <= 75 else 0)))
            else:
                rsi_s = 50
            # Liquidity (22%) — amount in 万元 → 1亿 = 10000万
            if amt is not None:
                yi = amt / 10000
                liq_s = 100 if yi >= 5 else (70 if yi >= 3 else (40 if yi >= 1 else 0))
            else:
                liq_s = 50
            # BB Position (16%)
            if pb is not None:
                bb_s = 100 if 0.4 <= pb <= 0.6 else (80 if 0.6 < pb <= 0.8 else (70 if 0.2 <= pb < 0.4 else (60 if pb > 0.8 else 20)))
            else:
                bb_s = 50
            # ATR Risk (9%)
            if ap is not None:
                atr_s = 100 if 1.5 <= ap <= 3 else (70 if 3 < ap <= 5 else (60 if ap < 1.5 else 30))
            else:
                atr_s = 50

            traditional = ma_s * 0.22 + mac_s * 0.19 + rsi_s * 0.13 + liq_s * 0.22 + bb_s * 0.16 + atr_s * 0.09
            row["traditional"] = round(traditional, 1)

            # Sentiment sub-score (3 factors)
            bs = row["board_streak"]
            lf = row["limit_up_freq"]
            sq = row["seal_quality"]

            if bs >= 3:  streak_s = 100
            elif bs == 2: streak_s = 85
            elif bs == 1: streak_s = 65
            else:         streak_s = 0

            if lf >= 3:   freq_s = 100
            elif lf == 2:  freq_s = 80
            elif lf == 1:  freq_s = 60
            else:          freq_s = 20

            if sq == "封死":   seal_s = 100
            elif sq == "未封板": seal_s = 60
            elif sq == "炸板":   seal_s = 15
            else:               seal_s = 50

            sentiment = streak_s * 0.50 + freq_s * 0.25 + seal_s * 0.25
            row["sentiment"] = round(sentiment, 1)

            # tech_score
            row["tech_score"] = round(traditional * 0.70 + sentiment * 0.30, 1)

            # risk_flags
            flags = []
            if rs is not None and rs > 75: flags.append("RSI>75")
            if rs is not None and rs < 30: flags.append("RSI<30")
            if ap is not None and ap > 8: flags.append("ATR>8%")
            row["risk_flags"] = flags

            results.append(row)

        except Exception as e:
            print(f"[ERROR] {code}: {e}", file=sys.stderr)
            continue

    # ── Output ─────────────────────────────────────────────
    if args.json:
        output_str = json.dumps(results, ensure_ascii=False, indent=2)
    else:
        if not results:
            output_str = "No data."
        else:
            lines = [
                f"{'Code':<12} {'Price':>8} {'Chg%':>7} {'RSI':>6} {'ATR':>6} "
                f"{'MA20':>8} {'Tech':>6} {'Sent':>5} {'Streak':>6} {'Seal'}"
            ]
            lines.append("-" * len(lines[0]))
            for r in results:
                vals = [
                    r["code"],
                    f"{r.get('price') or 0:>8.2f}",
                    f"{r.get('change_pct') or 0:>7.2f}",
                    f"{r.get('rsi') or 0:>6.1f}",
                    f"{r.get('atr') or 0:>6.2f}",
                    f"{r.get('ma20') or 0:>8.2f}",
                    f"{r.get('tech_score') or 0:>6.1f}",
                    f"{r.get('sentiment') or 0:>5.0f}",
                    f"{r['board_streak']:>6}",
                    r["seal_quality"],
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
