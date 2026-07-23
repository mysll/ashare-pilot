"""Public market-data APIs with explicit workspace context."""

from __future__ import annotations

from collections.abc import Sequence

from ashare_pilot.market_data._commands.history import fetch_history as _fetch_history
from ashare_pilot.market_data._commands.quote import (
    fetch_intraday_kline as _fetch_intraday_kline,
    fetch_stocks as _fetch_stocks,
    search_stocks as _search_stocks,
)
from ashare_pilot.market_data._commands.special import (
    fetch_lhb as _fetch_lhb,
    fetch_lhb_stock as _fetch_lhb_stock,
    fetch_rzye as _fetch_rzye,
)
from ashare_pilot.market_data._datasources import (
    EastMoneyDataSource,
    EastMoneyIntradayDataSource,
    SinaDataSource,
)
from ashare_pilot.market_data.runtime import use_workspace
from ashare_pilot.workspace import Workspace


def fetch_quotes(codes: Sequence[str], *, workspace: Workspace) -> list:
    with use_workspace(workspace):
        return _fetch_stocks(list(codes))


def fetch_intraday_kline(
    code: str, *, scale: int = 5, days: int = 1, workspace: Workspace
) -> list:
    with use_workspace(workspace):
        return _fetch_intraday_kline(code, scale=scale, days=days)


def search_stocks(keyword: str, *, workspace: Workspace) -> list:
    with use_workspace(workspace):
        return _search_stocks(keyword)


def fetch_history(
    code: str,
    *,
    start: str | None = None,
    end: str | None = None,
    range_str: str = "3m",
    use_cache: bool = True,
    source: str = "sohu",
    workspace: Workspace,
) -> list:
    with use_workspace(workspace):
        return _fetch_history(
            code,
            start=start,
            end=end,
            range_str=range_str,
            use_cache=use_cache,
            source=source,
        )


def fetch_all_stocks(*, source: str = "eastmoney", workspace: Workspace) -> list:
    """Fetch all A shares without emitting CLI progress text."""

    with use_workspace(workspace):
        if source == "sina":
            return SinaDataSource().fetch_all_stocks()
        results = EastMoneyDataSource().fetch_all_stocks()
        return results if len(results) >= 1000 else SinaDataSource().fetch_all_stocks()


def fetch_market_breadth(
    *, all_stocks: list | None = None, cache_dir: str | None = None,
    workspace: Workspace,
) -> dict:
    with use_workspace(workspace):
        return EastMoneyIntradayDataSource().fetch_market_breadth(
            all_stocks=all_stocks, cache_dir=cache_dir
        )


def fetch_money_flow(*, top: int = 100, workspace: Workspace) -> list:
    with use_workspace(workspace):
        return EastMoneyDataSource().fetch_industry_money_flow(top)


def fetch_stock_money_flow(*, top: int = 100, workspace: Workspace) -> list:
    with use_workspace(workspace):
        return EastMoneyDataSource().fetch_stock_money_flow(page_size=top)


def fetch_board_money_flow(
    board_type: str, *, field: str = "f174", top: int = 20,
    workspace: Workspace,
) -> list:
    with use_workspace(workspace):
        return EastMoneyDataSource().fetch_board_money_flow_by_field(
            field=field, board_type=board_type, top=top
        )


def fetch_special_lhb(
    *, date: str | None = None, code: str | None = None, workspace: Workspace
) -> list | dict | None:
    with use_workspace(workspace):
        return _fetch_lhb_stock(code, date) if code else _fetch_lhb(date)


def fetch_margin_balance(*, top: int = 10, workspace: Workspace) -> list:
    with use_workspace(workspace):
        return _fetch_rzye(top)


def fetch_concept_ranking(*, top: int = 50, workspace: Workspace) -> list:
    with use_workspace(workspace):
        return EastMoneyIntradayDataSource().fetch_concept_ranking(top=top)


def fetch_turnover_ranking(*, top: int = 100, workspace: Workspace) -> list:
    with use_workspace(workspace):
        return EastMoneyIntradayDataSource().fetch_turnover_ranking(top=top)


def fetch_limit_up_pool(*, top: int = 50, workspace: Workspace) -> list:
    with use_workspace(workspace):
        return EastMoneyIntradayDataSource().fetch_limit_up_pool(top=top)
