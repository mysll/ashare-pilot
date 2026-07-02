#!/usr/bin/env python3
"""Calculate technical indicators for stock data.

Fetches historical K-line data and calculates technical indicators.
Supports: A stocks (sh/sz only).

Usage:
    python fetch_indicators.py sh600519                    # Default indicators
    python fetch_indicators.py sz000001 --indicators rsi,macd,close_50_sma
    python fetch_indicators.py sh600519 --range 6m --json
    python fetch_indicators.py sh600519 --csv -o output.csv  # Save as CSV
    python fetch_indicators.py --list                      # List available indicators
"""

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from lib.fetch.fetch_history import fetch_history, to_csv


def calc_sma(data: list[float], period: int) -> list[float | None]:
    """Calculate Simple Moving Average."""
    result = [None] * len(data)
    for i in range(period - 1, len(data)):
        result[i] = sum(data[i - period + 1 : i + 1]) / period
    return result


def calc_ema(data: list[float], period: int) -> list[float | None]:
    """Calculate Exponential Moving Average."""
    result = [None] * len(data)
    if len(data) < period:
        return result

    # First EMA value is SMA
    result[period - 1] = sum(data[:period]) / period
    multiplier = 2 / (period + 1)

    for i in range(period, len(data)):
        result[i] = (data[i] - result[i - 1]) * multiplier + result[i - 1]

    return result


def calc_macd(
    closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """Calculate MACD, Signal, and Histogram."""
    ema_fast = calc_ema(closes, fast)
    ema_slow = calc_ema(closes, slow)

    macd_line = [None] * len(closes)
    for i in range(len(closes)):
        if ema_fast[i] is not None and ema_slow[i] is not None:
            macd_line[i] = ema_fast[i] - ema_slow[i]

    # Calculate signal line (EMA of MACD)
    valid_macd = [v if v is not None else 0 for v in macd_line]
    signal_line = calc_ema(valid_macd, signal)

    # Align signal with MACD
    first_valid = next((i for i, v in enumerate(macd_line) if v is not None), len(macd_line))
    for i in range(first_valid + signal - 1):
        signal_line[i] = None

    histogram = [None] * len(closes)
    for i in range(len(closes)):
        if macd_line[i] is not None and signal_line[i] is not None:
            histogram[i] = macd_line[i] - signal_line[i]

    return macd_line, signal_line, histogram


def calc_rsi(closes: list[float], period: int = 14) -> list[float | None]:
    """Calculate Relative Strength Index."""
    result = [None] * len(closes)
    if len(closes) < period + 1:
        return result

    gains = []
    losses = []

    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(0, change))
        losses.append(max(0, -change))

    # First RSI value
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    if avg_loss == 0:
        result[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        result[period] = 100 - (100 / (1 + rs))

    # Subsequent RSI values using smoothed averages
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            result[i + 1] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[i + 1] = 100 - (100 / (1 + rs))

    return result


def calc_bollinger(
    closes: list[float], period: int = 20, std_dev: float = 2.0
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """Calculate Bollinger Bands (Middle, Upper, Lower)."""
    import math

    middle = calc_sma(closes, period)
    upper = [None] * len(closes)
    lower = [None] * len(closes)

    for i in range(period - 1, len(closes)):
        if middle[i] is not None:
            window = closes[i - period + 1 : i + 1]
            variance = sum((x - middle[i]) ** 2 for x in window) / (period - 1)
            std = math.sqrt(variance)
            upper[i] = middle[i] + std_dev * std
            lower[i] = middle[i] - std_dev * std

    return middle, upper, lower


def calc_atr(
    highs: list[float], lows: list[float], closes: list[float], period: int = 14
) -> list[float | None]:
    """Calculate Average True Range."""
    import math

    result = [None] * len(closes)
    if len(closes) < period + 1:
        return result

    true_ranges = []
    for i in range(1, len(closes)):
        tr1 = highs[i] - lows[i]
        tr2 = abs(highs[i] - closes[i - 1])
        tr3 = abs(lows[i] - closes[i - 1])
        true_ranges.append(max(tr1, tr2, tr3))

    # First ATR value
    result[period] = sum(true_ranges[:period]) / period

    # Subsequent ATR values
    for i in range(period, len(true_ranges)):
        result[i + 1] = (result[i] * (period - 1) + true_ranges[i]) / period

    return result


def calc_vwma(
    closes: list[float], volumes: list[float], period: int = 20
) -> list[float | None]:
    """Calculate Volume Weighted Moving Average."""
    result = [None] * len(closes)

    for i in range(period - 1, len(closes)):
        pv_sum = sum(closes[j] * volumes[j] for j in range(i - period + 1, i + 1))
        v_sum = sum(volumes[i - period + 1 : i + 1])
        if v_sum > 0:
            result[i] = pv_sum / v_sum

    return result


# Available indicators mapping
INDICATORS = {
    # Moving Averages
    "close_10_ema": lambda d: calc_ema(d["closes"], 10),
    "close_50_sma": lambda d: calc_sma(d["closes"], 50),
    "close_200_sma": lambda d: calc_sma(d["closes"], 200),
    # MACD
    "macd": lambda d: calc_macd(d["closes"])[0],
    "macds": lambda d: calc_macd(d["closes"])[1],
    "macdh": lambda d: calc_macd(d["closes"])[2],
    # Momentum
    "rsi": lambda d: calc_rsi(d["closes"], 14),
    # Volatility
    "boll": lambda d: calc_bollinger(d["closes"])[0],
    "boll_ub": lambda d: calc_bollinger(d["closes"])[1],
    "boll_lb": lambda d: calc_bollinger(d["closes"])[2],
    "atr": lambda d: calc_atr(d["highs"], d["lows"], d["closes"], 14),
    # Volume
    "vwma": lambda d: calc_vwma(d["closes"], d["volumes"], 20),
}

# Default indicator set for analysis
DEFAULT_INDICATORS = [
    "close_50_sma",
    "close_200_sma",
    "macd",
    "macds",
    "rsi",
    "boll",
    "boll_ub",
    "boll_lb",
]


def parse_value(v: str | float | None) -> float | None:
    """Parse string value to float, return None for empty/invalid."""
    if v is None or v == "" or v == "-":
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def calculate_indicators(
    records: list[dict[str, Any]], indicators: list[str]
) -> dict[str, list[float | None]]:
    """Calculate specified indicators for historical data."""
    closes = [parse_value(r.get("close")) for r in records]
    highs = [parse_value(r.get("high")) for r in records]
    lows = [parse_value(r.get("low")) for r in records]
    volumes = [parse_value(r.get("volume")) or 0 for r in records]

    # Replace None with 0 for calculation stability
    closes = [v if v is not None else 0 for v in closes]
    highs = [v if v is not None else 0 for v in highs]
    lows = [v if v is not None else 0 for v in lows]

    data = {"closes": closes, "highs": highs, "lows": lows, "volumes": volumes}

    results = {}
    for ind in indicators:
        if ind in INDICATORS:
            results[ind] = INDICATORS[ind](data)
        else:
            print(f"Warning: Unknown indicator '{ind}'", file=sys.stderr)

    return results


def format_value(v: float | None) -> str:
    """Format indicator value for display."""
    if v is None:
        return "-"
    return f"{v:.2f}"


def print_indicators(
    records: list[dict[str, Any]],
    indicators: dict[str, list[float | None]],
    stock_code: str,
) -> None:
    """Print data with indicators in table format."""
    if not records:
        print("No data.")
        return

    ind_names = list(indicators.keys())

    # Header
    print(f"Stock: {stock_code}  Records: {len(records)}  Indicators: {', '.join(ind_names)}")
    print("-" * (12 + 10 * (5 + len(ind_names))))

    # Column headers
    header = f"{'Date':<12} {'Open':>10} {'Close':>10} {'High':>10} {'Low':>10}"
    for ind in ind_names:
        header += f" {ind:>12}"
    print(header)

    # Data rows (show last 30 records)
    start_idx = max(0, len(records) - 30)
    for i in range(start_idx, len(records)):
        r = records[i]
        row = f"{r['date']:<12} {r['open']:>10} {r['close']:>10} {r['high']:>10} {r['low']:>10}"
        for ind in ind_names:
            row += f" {format_value(indicators[ind][i]):>12}"
        print(row)


def to_json_output(
    records: list[dict[str, Any]],
    indicators: dict[str, list[float | None]],
    stock_code: str,
) -> list[dict[str, Any]]:
    """Combine records with indicators for JSON output."""
    result = []
    for i, r in enumerate(records):
        row = {
            "date": r["date"],
            "open": r["open"],
            "close": r["close"],
            "high": r["high"],
            "low": r["low"],
            "volume": r["volume"],
            "change_pct": r["change_pct"],
        }
        for ind_name, ind_values in indicators.items():
            row[ind_name] = ind_values[i]
        result.append(row)
    return result


def to_csv_output(
    records: list[dict[str, Any]],
    indicators: dict[str, list[float | None]],
    stock_code: str,
) -> str:
    """Convert records with indicators to CSV format."""
    import io

    output = io.StringIO(newline="")
    ind_names = list(indicators.keys())

    # Fieldnames
    fieldnames = ["date", "open", "close", "high", "low", "volume", "change_pct"] + ind_names

    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for i, r in enumerate(records):
        row = {
            "date": r["date"],
            "open": r["open"],
            "close": r["close"],
            "high": r["high"],
            "low": r["low"],
            "volume": r["volume"],
            "change_pct": r["change_pct"],
        }
        for ind_name, ind_values in indicators.items():
            val = ind_values[i]
            row[ind_name] = format_value(val) if val is not None else ""
        writer.writerow(row)

    return output.getvalue()


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="Calculate technical indicators for stock data"
    )
    parser.add_argument("code", help="Stock code (sh/sz only, e.g., sh600519)")
    parser.add_argument(
        "--range",
        choices=["1y", "6m", "3m", "1m", "1w"],
        default="3m",
        help="Time range (default: 3m)",
    )
    parser.add_argument(
        "--start",
        help="Start date (YYYYMMDD), overrides --range",
    )
    parser.add_argument(
        "--end",
        help="End date (YYYYMMDD), default: today",
    )
    parser.add_argument(
        "--indicators",
        help="Comma-separated list of indicators (default: common set)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON array",
    )
    parser.add_argument(
        "--csv",
        action="store_true",
        help="Output as CSV format",
    )
    parser.add_argument(
        "-o", "--output",
        metavar="FILE",
        help="Save output to file (JSON if --json, CSV if --csv, else TXT)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available indicators",
    )

    args = parser.parse_args()

    # List indicators
    if args.list:
        print("Available indicators:")
        for name, func in INDICATORS.items():
            print(f"  {name}")
        return

    # Fetch historical data
    records = fetch_history(args.code, args.start, args.end, args.range)
    if not records:
        print("No data available.", file=sys.stderr)
        return

    # Determine which indicators to calculate
    if args.indicators:
        ind_list = [i.strip() for i in args.indicators.split(",")]
    else:
        ind_list = DEFAULT_INDICATORS

    # Calculate indicators
    indicators = calculate_indicators(records, ind_list)

    # Build output string
    output_str = ""
    if args.json:
        output = to_json_output(records, indicators, args.code)
        output_str = json.dumps(output, ensure_ascii=False, indent=2)
    elif args.csv:
        output_str = to_csv_output(records, indicators, args.code)
    else:
        lines = []
        ind_names = list(indicators.keys())
        lines.append(f"Stock: {args.code}  Records: {len(records)}  Indicators: {', '.join(ind_names)}")
        lines.append("-" * (12 + 10 * (5 + len(ind_names))))
        header = f"{'Date':<12} {'Open':>10} {'Close':>10} {'High':>10} {'Low':>10}"
        for ind in ind_names:
            header += f" {ind:>12}"
        lines.append(header)
        start_idx = max(0, len(records) - 30)
        for i in range(start_idx, len(records)):
            r = records[i]
            row = f"{r['date']:<12} {r['open']:>10} {r['close']:>10} {r['high']:>10} {r['low']:>10}"
            for ind in ind_names:
                row += f" {format_value(indicators[ind][i]):>12}"
            lines.append(row)
        output_str = "\n".join(lines)

    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            f.write(output_str)
        print(f"Saved to {args.output}")
    else:
        print(output_str)


if __name__ == "__main__":
    main()
