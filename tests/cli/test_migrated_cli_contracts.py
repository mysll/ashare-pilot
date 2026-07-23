from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "docs" / "core-refactor-acceptance-matrix.md"
ENTRY_ROW = re.compile(
    r"^\| (?P<id>(?:MD|IN|NW|TH|MP|ST|OP|RV|AU)\d{2}) "
    r"\| `(?P<legacy>[^`]+\.py)` \| `(?P<cli>[^`]+)` \|",
    re.MULTILINE,
)
OPTION = re.compile(r"(?<![\w-])(?:--[a-zA-Z0-9][a-zA-Z0-9-]*|-[a-zA-Z])(?![\w-])")

def entries() -> list[tuple[str, str, str]]:
    return [match.groups() for match in ENTRY_ROW.finditer(MATRIX.read_text(encoding="utf-8"))]


def legacy_path(entry_id: str, filename: str) -> Path:
    number = int(entry_id[2:])
    if entry_id.startswith("MD"):
        base = ".opencode/scripts" if entry_id == "MD11" else ".opencode/lib/fetch"
    elif entry_id == "IN01":
        base = ".opencode/lib/fetch"
    elif entry_id == "IN02":
        base = ".agents/skills/daily-stock-mapping/scripts"
    elif entry_id == "IN03":
        base = ".agents/skills/intraday-stock-discovery/scripts"
    elif entry_id == "NW01":
        base = ".agents/skills/daily-news-brief/scripts"
    elif entry_id.startswith("TH"):
        skill = {
            1: "theme-library",
            2: "theme-library",
            3: "theme-library",
            4: "theme-library",
            5: "intraday-market-scan",
            6: "intraday-stock-discovery",
        }[number]
        base = f".agents/skills/{skill}/scripts"
    elif entry_id.startswith("MP"):
        if number <= 15:
            skill = "daily-stock-mapping"
        elif number == 16:
            skill = "intraday-market-scan"
        elif number == 17:
            skill = "intraday-stock-discovery"
        else:
            skill = "intraday-strategy"
        base = f".agents/skills/{skill}/scripts"
    elif entry_id.startswith("ST"):
        skill = "daily-strategy" if number <= 10 else "intraday-strategy"
        base = f".agents/skills/{skill}/scripts"
    elif entry_id.startswith("OP"):
        base = ".agents/skills/intraday-operation-guide/scripts"
    elif entry_id.startswith("RV"):
        base = ".agents/skills/daily-trading-review/scripts"
    elif entry_id.startswith("AU"):
        base = ".opencode/scripts"
    else:  # pragma: no cover - guarded by ENTRY_ROW
        raise AssertionError(f"unknown entry ID: {entry_id}")
    return ROOT / base / filename


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def old_command(entry_id: str, filename: str, *arguments: str) -> list[str]:
    path = legacy_path(entry_id, filename)
    if not path.exists():
        pytest.skip("legacy CLI removed after the accepted phase-two cutover")
    return [sys.executable, str(path), *arguments]


def new_command(cli: str, *arguments: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "ashare_pilot",
        "--workspace",
        str(ROOT),
        *cli.split(),
        *arguments,
    ]


@pytest.mark.parametrize(("entry_id", "filename", "cli"), entries())
def test_leaf_help_preserves_option_contract(
    entry_id: str, filename: str, cli: str
) -> None:
    old = run(old_command(entry_id, filename, "--help"))
    new = run(new_command(cli, "--help"))

    assert old.returncode == new.returncode == 0
    assert set(OPTION.findall(new.stdout)) == set(OPTION.findall(old.stdout))
    assert not old.stderr
    assert not new.stderr


@pytest.mark.parametrize(("entry_id", "filename", "cli"), entries())
def test_leaf_unknown_argument_preserves_failure_boundary(
    entry_id: str, filename: str, cli: str
) -> None:
    argument = "--acceptance-matrix-invalid-option"
    old = run(old_command(entry_id, filename, argument))
    new = run(new_command(cli, argument))

    assert old.returncode == new.returncode == 2
    assert old.stdout == new.stdout == ""
    old_error = old.stderr.rstrip().rsplit(": error: ", 1)[-1]
    new_error = new.stderr.rstrip().rsplit(": error: ", 1)[-1]
    assert new_error == old_error
