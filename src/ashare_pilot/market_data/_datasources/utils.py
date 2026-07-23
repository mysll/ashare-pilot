"""Common utility functions for data formatting."""

import re
from typing import Any


RANGE_PATTERN = re.compile(r"^([1-9]\d*)([dwmy])$", re.IGNORECASE)


def parse_range_days(range_str: str) -> int:
    """Convert a range such as 5d, 2w, 3m, or 1y to calendar days."""
    match = RANGE_PATTERN.fullmatch(str(range_str).strip())
    if not match:
        raise ValueError(
            f"Invalid range {range_str!r}; expected a positive integer followed by d, w, m, or y"
        )

    value = int(match.group(1))
    unit = match.group(2).lower()
    multipliers = {"d": 1, "w": 7, "m": 30, "y": 365}
    return value * multipliers[unit]


def format_price(value: Any, precision: int = 2) -> str:
    if value is None or value == "" or value == "-":
        return "0.00"
    try:
        return f"{float(value):.{precision}f}"
    except (ValueError, TypeError):
        return "0.00"


def format_volume(value: Any) -> str:
    if value is None or value == "" or value == "-":
        return "0"
    try:
        vol = float(value)
        if vol >= 100000000:
            return f"{vol / 100000000:.2f}亿"
        if vol >= 10000:
            return f"{vol / 10000:.2f}万手"
        return f"{vol:.0f}手"
    except (ValueError, TypeError):
        return "0"


def format_amount(value: Any) -> str:
    if value is None or value == "" or value == "-":
        return "0"
    try:
        amt = float(value)
        if amt >= 100000000:
            return f"{amt / 100000000:.2f}亿"
        if amt >= 10000:
            return f"{amt / 10000:.2f}万"
        return f"{amt:.0f}"
    except (ValueError, TypeError):
        return "0"


def format_percent(value: Any) -> str:
    if value is None or value == "" or value == "-":
        return "0.00%"
    try:
        return f"{float(value):+.2f}%"
    except (ValueError, TypeError):
        return "0.00%"


def calc_price_precision(*prices: str) -> int:
    max_decimals = 0
    for p in prices:
        if not p:
            continue
        p = str(p).rstrip("0")
        if "." in p:
            decimals = len(p.split(".")[1])
            max_decimals = max(max_decimals, decimals)
    return min(max_decimals, 2) if max_decimals > 3 else max_decimals


def parse_percent(value: str) -> float:
    if not value or value == "-" or value == "None":
        return 0.0
    try:
        return float(value.replace("%", "").replace("+", ""))
    except (ValueError, TypeError):
        return 0.0


def to_yi(value: Any) -> str:
    if value is None:
        return "0.00"
    try:
        return f"{float(value) / 1e8:.2f}"
    except (ValueError, TypeError):
        return "0.00"
