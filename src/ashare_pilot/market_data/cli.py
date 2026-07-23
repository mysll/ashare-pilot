from __future__ import annotations

import argparse
import sys
from collections.abc import Callable

from ashare_pilot.market_data._commands import (
    auth,
    board_money_flow,
    breadth,
    concept_ranking,
    history,
    limit_up_pool,
    money_flow,
    quote,
    special,
    stocks_all,
    turnover_ranking,
)
from ashare_pilot.market_data.runtime import use_workspace
from ashare_pilot.workspace import Workspace


def _show_group_help(namespace: argparse.Namespace, _workspace: Workspace) -> int:
    parser: argparse.ArgumentParser = namespace._parser
    if namespace._command_args:
        parser.error(f"unrecognized arguments: {' '.join(namespace._command_args)}")
    parser.print_help()
    return 0


def _forward(
    command_main: Callable[[list[str]], object], prog: str
) -> Callable:
    def handler(namespace: argparse.Namespace, workspace: Workspace | None) -> int:
        previous_prog = sys.argv[0]
        sys.argv[0] = prog
        try:
            if workspace is None:
                result = command_main(namespace._command_args)
            else:
                with use_workspace(workspace):
                    result = command_main(namespace._command_args)
        finally:
            sys.argv[0] = previous_prog
        return result if isinstance(result, int) else 0

    return handler


def _group(
    subparsers: argparse._SubParsersAction, name: str, help_text: str
) -> tuple[argparse.ArgumentParser, argparse._SubParsersAction]:
    parser = subparsers.add_parser(name, help=help_text, description=help_text)
    parser.set_defaults(handler=_show_group_help, _parser=parser)
    return parser, parser.add_subparsers(dest=f"{name}_command", metavar="COMMAND")


def _leaf(
    subparsers: argparse._SubParsersAction,
    name: str,
    help_text: str,
    command_main: Callable[[list[str]], object],
    prog: str,
) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(name, add_help=False, help=help_text)
    parser.set_defaults(
        handler=_forward(command_main, prog),
        _parser=parser,
        _forwarded_leaf=True,
    )
    return parser


def register_cli(subparsers: argparse._SubParsersAction) -> None:
    _, commands = _group(subparsers, "market-data", "Market data and calendars.")
    _leaf(commands, "quote", "Real-time quotes and stock search.", quote.main, "ashare-pilot market-data quote")
    _leaf(commands, "history", "Historical daily K-line data.", history.main, "ashare-pilot market-data history")
    _leaf(commands, "breadth", "A-share market breadth.", breadth.main, "ashare-pilot market-data breadth")
    _leaf(commands, "special", "Dragon-Tiger and margin data.", special.main, "ashare-pilot market-data special")

    _, stocks = _group(commands, "stocks", "Whole-market stock lists.")
    _leaf(stocks, "all", "All A-share real-time quotes.", stocks_all.main, "ashare-pilot market-data stocks all")

    money_parser = commands.add_parser(
        "money-flow", add_help=False, help="Industry or stock money flow."
    )
    money_parser.set_defaults(
        handler=_forward(money_flow.main, "ashare-pilot market-data money-flow"),
        _parser=money_parser,
        _forwarded_leaf=True,
    )
    money_commands = money_parser.add_subparsers(
        dest="money_flow_command", metavar="COMMAND"
    )
    _leaf(
        money_commands,
        "board",
        "Concept and industry board money flow.",
        board_money_flow.main,
        "ashare-pilot market-data money-flow board",
    )

    _, ranking = _group(commands, "ranking", "Market rankings.")
    _leaf(ranking, "concepts", "Concept-board ranking.", concept_ranking.main, "ashare-pilot market-data ranking concepts")
    _leaf(ranking, "turnover", "Turnover ranking.", turnover_ranking.main, "ashare-pilot market-data ranking turnover")

    _, pool = _group(commands, "pool", "Market event pools.")
    _leaf(pool, "limit-up", "Limit-up stock pool.", limit_up_pool.main, "ashare-pilot market-data pool limit-up")

    _, auth_group = _group(commands, "auth", "Market-data authentication.")
    _leaf(auth_group, "update-cookie", "Update East Money cookies.", auth.main, "ashare-pilot market-data auth update-cookie")
