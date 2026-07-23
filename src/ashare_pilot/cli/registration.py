"""Helpers shared by capability-specific CLI registrars."""

from __future__ import annotations

import argparse


def add_capability_group(
    subparsers: argparse._SubParsersAction, name: str, help_text: str
) -> argparse.ArgumentParser:
    from ashare_pilot.cli.app import show_group_help

    parser = subparsers.add_parser(name, help=help_text, description=help_text)
    parser.set_defaults(handler=show_group_help, _parser=parser)
    return parser
