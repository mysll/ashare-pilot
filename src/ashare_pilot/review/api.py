"""Public APIs for daily verification and entry backtests."""

from pathlib import Path
from typing import Any

from ashare_pilot.market_data.runtime import use_workspace
from ashare_pilot.review._commands.backtest_entry_band import load_rows, summarize
from ashare_pilot.review._commands.backtest_entry_quality import metrics, parse_file
from ashare_pilot.review._commands.verify import build_verification as _build_verification
from ashare_pilot.review.intraday_shadow_contract import (
    build_contract as _build_intraday_shadow_contract,
)
from ashare_pilot.review.intraday_shadow_contract import validate_contract as validate_intraday_shadow_contract
from ashare_pilot.workspace import Workspace


def build_verification(
    *,
    date: str,
    strategy_path: Path | None,
    codes: list[str] | None,
    regime_hint: str | None,
    pool_indicators_path: Path | None,
    strategy_json_path: Path | None = None,
    workspace: Workspace,
) -> dict[str, Any]:
    with use_workspace(workspace):
        return _build_verification(
            date=date,
            strategy_path=strategy_path,
            codes=codes,
            regime_hint=regime_hint,
            pool_indicators_path=pool_indicators_path,
            strategy_json_path=strategy_json_path,
        )


def build_intraday_shadow_contract(
    *,
    as_of_date: str,
    config_path: Path,
    workspace: Workspace,
    since: str | None = None,
) -> dict[str, Any]:
    with use_workspace(workspace):
        return _build_intraday_shadow_contract(
            as_of_date=as_of_date,
            config_path=config_path,
            since=since,
        )


__all__ = [
    "build_intraday_shadow_contract",
    "build_verification",
    "load_rows",
    "metrics",
    "parse_file",
    "summarize",
    "validate_intraday_shadow_contract",
]
