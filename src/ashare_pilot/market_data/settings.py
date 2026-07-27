"""Validated market-data settings loaded from config/setting.json."""

from __future__ import annotations

import json
from pathlib import Path

from ashare_pilot.market_data.runtime import workspace_path


DEFAULT_STOCK_MONEY_FLOW_MIN_INFLOW_YUAN = 10_000_000


def load_stock_money_flow_min_inflow_yuan(
    config_file: str | Path | None = None,
) -> int:
    """Return the minimum material stock-level main inflow in yuan."""
    path = (
        Path(config_file)
        if config_file is not None
        else workspace_path("config", "setting.json")
    )
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return DEFAULT_STOCK_MONEY_FLOW_MIN_INFLOW_YUAN
    market_data = config.get("market_data", {})
    if not isinstance(market_data, dict):
        raise ValueError("market_data must be an object")
    value = market_data.get(
        "stock_money_flow_min_inflow_yuan",
        DEFAULT_STOCK_MONEY_FLOW_MIN_INFLOW_YUAN,
    )
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(
            "market_data.stock_money_flow_min_inflow_yuan must be an integer"
        )
    if not 0 <= value <= 1_000_000_000:
        raise ValueError(
            "market_data.stock_money_flow_min_inflow_yuan must be between "
            "0 and 1000000000"
        )
    return value
