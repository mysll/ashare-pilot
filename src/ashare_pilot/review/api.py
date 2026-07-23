"""Public APIs for daily verification and entry backtests."""

from pathlib import Path
from typing import Any

from ashare_pilot.market_data.runtime import use_workspace
from ashare_pilot.review._commands.backtest_entry_band import load_rows, summarize
from ashare_pilot.review._commands.backtest_entry_quality import metrics, parse_file
from ashare_pilot.review._commands.verify import build_verification as _build_verification
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


__all__ = ["build_verification", "load_rows", "metrics", "parse_file", "summarize"]
