"""Top-level argparse application for A-Share Pilot."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from ashare_pilot import __version__
from ashare_pilot.cli.registry import register_commands
from ashare_pilot.errors import ASharePilotError
from ashare_pilot.workspace import resolve_workspace


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ashare-pilot",
        description="Agent-neutral tools for the A-Share Pilot workspace.",
    )
    parser.add_argument(
        "--workspace",
        metavar="PATH",
        help="project workspace (overrides ASHARE_PILOT_WORKSPACE and discovery)",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="capability", metavar="CAPABILITY")
    register_commands(subparsers)
    parser.set_defaults(_parser=parser)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    namespace, command_args = parser.parse_known_args(argv)
    namespace._command_args = command_args

    try:
        handler = getattr(namespace, "handler", None)
        if handler is None:
            if command_args:
                parser.error(f"unrecognized arguments: {' '.join(command_args)}")
            resolve_workspace(namespace.workspace)
            parser.print_help()
            return 0
        if getattr(namespace, "_forwarded_leaf", False) and any(
            argument in ("-h", "--help") for argument in command_args
        ):
            return handler(namespace, None)
        workspace = resolve_workspace(namespace.workspace)
        return handler(namespace, workspace)
    except ASharePilotError as exc:
        print(f"{parser.prog}: error: {exc}", file=sys.stderr)
        return 2


def show_group_help(namespace: argparse.Namespace, _workspace: object) -> int:
    group_parser: argparse.ArgumentParser = namespace._parser
    if namespace._command_args:
        group_parser.error(
            f"unrecognized arguments: {' '.join(namespace._command_args)}"
        )
    group_parser.print_help()
    return 0
