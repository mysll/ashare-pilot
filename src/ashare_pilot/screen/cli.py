"""CLI registration for deterministic side-car screens."""

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
            module = importlib.import_module(module_name)
            if workspace is None:
                result = module.main(namespace._command_args)
            else:
                with use_workspace(workspace):
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
        "screen", help="Deterministic side-car stock screens (informational only)."
    )
    parser.set_defaults(handler=_show_group_help, _parser=parser)
    commands = parser.add_subparsers(dest="screen_command", metavar="COMMAND")

    _leaf(
        commands,
        "limit-up-cluster",
        "Screen stocks inside limit-up concept clusters.",
        "ashare_pilot.screen._commands.limit_up_cluster",
        "ashare-pilot screen limit-up-cluster",
    )
