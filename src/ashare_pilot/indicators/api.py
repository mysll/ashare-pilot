"""Public APIs for indicator calculation and history enrichment."""

from __future__ import annotations

from collections.abc import Sequence

from ashare_pilot.indicators._commands.calculate import (
    DEFAULT_INDICATORS,
    calc_atr,
    calc_bollinger,
    calc_ema,
    calc_macd,
    calc_rsi,
    calc_sma,
    calc_vwma,
    calculate_indicators,
)
from ashare_pilot.market_data.api import fetch_history
from ashare_pilot.workspace import Workspace


def fetch_indicators(
    code: str,
    *,
    indicators: Sequence[str] | None = None,
    start: str | None = None,
    end: str | None = None,
    range_str: str = "3m",
    source: str = "sohu",
    workspace: Workspace,
) -> tuple[list, dict[str, list[float | None]]]:
    """Fetch history and calculate selected indicators without CLI output."""

    records = fetch_history(
        code,
        start=start,
        end=end,
        range_str=range_str,
        source=source,
        workspace=workspace,
    )
    names = list(DEFAULT_INDICATORS if indicators is None else indicators)
    return records, calculate_indicators(records, names)


__all__ = [
    "calc_atr",
    "calc_bollinger",
    "calc_ema",
    "calc_macd",
    "calc_rsi",
    "calc_sma",
    "calc_vwma",
    "calculate_indicators",
    "fetch_indicators",
]
