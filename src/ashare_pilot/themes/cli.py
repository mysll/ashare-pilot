"""CLI registration for theme-library commands."""

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


def _group(subparsers, name: str, help_text: str):
    parser = subparsers.add_parser(name, help=help_text)
    parser.set_defaults(handler=_show_group_help, _parser=parser)
    return parser.add_subparsers(dest=f"themes_{name}_command", metavar="COMMAND")


def register_cli(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "themes", help="Concepts and theme intelligence."
    )
    parser.set_defaults(handler=_show_group_help, _parser=parser)
    commands = parser.add_subparsers(dest="themes_command", metavar="COMMAND")

    concepts = _group(commands, "concepts", "Concept-board acquisition.")
    _leaf(
        concepts,
        "fetch",
        "Fetch concept boards.",
        "ashare_pilot.themes._commands.concepts_fetch",
        "ashare-pilot themes concepts fetch",
    )
    _leaf(
        concepts,
        "fetch-stocks",
        "Fetch concept member stocks.",
        "ashare_pilot.themes._commands.concepts_fetch_stocks",
        "ashare-pilot themes concepts fetch-stocks",
    )

    library = _group(commands, "library", "Persistent theme library.")
    _leaf(
        library,
        "build",
        "Build theme-library indexes.",
        "ashare_pilot.themes._commands.library_build",
        "ashare-pilot themes library build",
    )
    _leaf(
        commands,
        "query",
        "Query themes, concepts, and stocks.",
        "ashare_pilot.themes._commands.query",
        "ashare-pilot themes query",
    )

    dashboard = _group(commands, "dashboard", "Intraday concept dashboard.")
    _leaf(
        dashboard,
        "build",
        "Build a multidimensional concept dashboard.",
        "ashare_pilot.themes._commands.dashboard",
        "ashare-pilot themes dashboard build",
    )

    ranking = _group(commands, "ranking", "Bottom-up theme ranking.")
    _leaf(
        ranking,
        "compute",
        "Compute theme ranking from a stock pool.",
        "ashare_pilot.themes._commands.ranking",
        "ashare-pilot themes ranking compute",
    )
