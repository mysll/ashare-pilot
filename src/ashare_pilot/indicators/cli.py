"""CLI registration for indicator commands."""

from __future__ import annotations

import argparse
import importlib
import sys

from ashare_pilot.market_data.runtime import use_workspace
from ashare_pilot.workspace import Workspace


def _show_group_help(namespace: argparse.Namespace, _workspace: Workspace) -> int:
    parser: argparse.ArgumentParser = namespace._parser
    if namespace._command_args:
        parser.error(f"unrecognized arguments: {' '.join(namespace._command_args)}")
    parser.print_help()
    return 0


def _forward(module_name: str, prog: str):
    def handler(namespace: argparse.Namespace, workspace: Workspace | None) -> int:
        previous_prog = sys.argv[0]
        sys.argv[0] = prog
        try:
            if workspace is None:
                module = importlib.import_module(module_name)
                result = module.main(namespace._command_args)
            else:
                with use_workspace(workspace):
                    module = importlib.import_module(module_name)
                    result = module.main(namespace._command_args)
        finally:
            sys.argv[0] = previous_prog
        return result if isinstance(result, int) else 0

    return handler


def _leaf(subparsers, name: str, help_text: str, module_name: str, prog: str):
    parser = subparsers.add_parser(name, add_help=False, help=help_text)
    parser.set_defaults(
        handler=_forward(module_name, prog),
        _parser=parser,
        _forwarded_leaf=True,
    )
    return parser


def register_cli(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "indicators", help="Indicators and derived features."
    )
    parser.set_defaults(handler=_show_group_help, _parser=parser)
    commands = parser.add_subparsers(dest="indicators_command", metavar="COMMAND")
    _leaf(
        commands,
        "calculate",
        "Calculate indicators for one stock.",
        "ashare_pilot.indicators._commands.calculate",
        "ashare-pilot indicators calculate",
    )

    pool = commands.add_parser("pool", help="Pool indicator operations.")
    pool.set_defaults(handler=_show_group_help, _parser=pool)
    pool_commands = pool.add_subparsers(dest="indicator_pool_command", metavar="COMMAND")
    _leaf(
        pool_commands,
        "fetch",
        "Fetch indicators for a stock pool.",
        "ashare_pilot.indicators._commands.pool_fetch",
        "ashare-pilot indicators pool fetch",
    )
    _leaf(
        pool_commands,
        "enrich",
        "Enrich a compute pool with technicals.",
        "ashare_pilot.indicators._commands.pool_enrich",
        "ashare-pilot indicators pool enrich",
    )
