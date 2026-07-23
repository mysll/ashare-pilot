from __future__ import annotations

import argparse
import sys
from collections.abc import Callable

from ashare_pilot.news import fetch
from ashare_pilot.workspace import Workspace


def _show_group_help(namespace: argparse.Namespace, _workspace: Workspace) -> int:
    parser: argparse.ArgumentParser = namespace._parser
    if namespace._command_args:
        parser.error(f"unrecognized arguments: {' '.join(namespace._command_args)}")
    parser.print_help()
    return 0


def _forward(command_main: Callable[[list[str]], object], prog: str) -> Callable:
    def handler(namespace: argparse.Namespace, _workspace: Workspace | None) -> int:
        previous_prog = sys.argv[0]
        sys.argv[0] = prog
        try:
            result = command_main(namespace._command_args)
        finally:
            sys.argv[0] = previous_prog
        return result if isinstance(result, int) else 0

    return handler


def register_cli(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "news", help="News acquisition and normalization."
    )
    parser.set_defaults(handler=_show_group_help, _parser=parser)
    commands = parser.add_subparsers(dest="news_command", metavar="COMMAND")
    fetch_parser = commands.add_parser(
        "fetch", add_help=False, help="Fetch and normalize daily news."
    )
    fetch_parser.set_defaults(
        handler=_forward(fetch.main, "ashare-pilot news fetch"),
        _parser=fetch_parser,
        _forwarded_leaf=True,
    )
