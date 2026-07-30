from pathlib import Path

import pytest

from ashare_pilot.cli.app import main


def make_workspace(path: Path) -> Path:
    path.mkdir()
    (path / "pyproject.toml").write_text("[project]\nname = 'fixture'\n", encoding="utf-8")
    (path / "config").mkdir()
    return path


def test_global_help_does_not_require_workspace(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["--help"])

    assert raised.value.code == 0
    output = capsys.readouterr().out
    assert "Agent-neutral tools" in output
    assert "market-data" in output


def test_unknown_command_uses_argparse_error(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["not-a-command"])

    assert raised.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_workspace_error_returns_two(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main(["--workspace", str(tmp_path)])

    assert exit_code == 2
    assert "Expected both pyproject.toml and config/" in capsys.readouterr().err


def test_capability_group_uses_explicit_workspace(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    workspace = make_workspace(tmp_path / "workspace")

    exit_code = main(["--workspace", str(workspace), "market-data"])

    assert exit_code == 0
    assert "Market data and calendars" in capsys.readouterr().out


@pytest.mark.parametrize(
    "removed_command",
    ["validate-annotations", "finalize", "validate"],
)
def test_removed_daily_theme_commands_are_not_public(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    removed_command: str,
) -> None:
    workspace = make_workspace(tmp_path / "workspace")

    with pytest.raises(SystemExit) as raised:
        main(
            [
                "--workspace",
                str(workspace),
                "themes",
                "daily",
                removed_command,
            ]
        )

    assert raised.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


@pytest.mark.parametrize(
    "command",
    [
        ["market-data", "quote"],
        ["market-data", "history"],
        ["market-data", "stocks", "all"],
        ["market-data", "breadth"],
        ["market-data", "money-flow"],
        ["market-data", "money-flow", "board"],
        ["market-data", "special"],
        ["market-data", "ranking", "concepts"],
        ["market-data", "ranking", "turnover"],
        ["market-data", "pool", "limit-up"],
        ["market-data", "auth", "update-cookie"],
        ["news", "fetch"],
        ["indicators", "calculate"],
        ["indicators", "pool", "fetch"],
        ["indicators", "pool", "enrich"],
        ["themes", "concepts", "fetch"],
        ["themes", "concepts", "fetch-stocks"],
        ["themes", "library", "build"],
        ["themes", "query"],
        ["themes", "dashboard", "build"],
        ["themes", "ranking", "compute"],
        ["themes", "daily", "prepare"],
        ["themes", "daily", "publish"],
        ["mapping", "daily", "build-theme-stock-universe"],
        ["mapping", "daily", "build-theme-stock-base"],
        ["mapping", "daily", "build-theme-stocks"],
        ["mapping", "daily", "validate-theme-stocks"],
        ["mapping", "daily", "build-mapper-base"],
        ["mapping", "daily", "validate-annotations"],
        ["mapping", "daily", "build-mapper"],
        ["mapping", "daily", "validate-mapper"],
        ["mapping", "daily", "build-strategy-view"],
        ["mapping", "daily", "build-timing"],
        ["mapping", "daily", "prepare"],
        ["mapping", "daily", "finalize"],
        ["mapping", "daily", "compare-regression"],
        ["mapping", "intraday", "build-scan-pool"],
        ["mapping", "intraday", "enrich-compute-pool"],
        ["mapping", "intraday", "build-mapper-base"],
        ["mapping", "intraday", "validate-annotations"],
        ["mapping", "intraday", "build-mapper"],
        ["mapping", "intraday", "validate-mapper"],
        ["strategy", "daily", "build-llm-input"],
        ["strategy", "daily", "compute-trade-profile"],
        ["strategy", "daily", "normalize-selection"],
        ["strategy", "daily", "validate-draft"],
        ["strategy", "daily", "validate"],
        ["strategy", "daily", "build-timing"],
        ["strategy", "daily", "prepare"],
        ["strategy", "daily", "finalize"],
        ["strategy", "daily", "render-report"],
        ["strategy", "daily", "compare-shadow"],
        ["strategy", "overnight", "score"],
        ["strategy", "overnight", "build"],
        ["strategy", "overnight", "validate"],
        ["strategy", "overnight", "render-report"],
        ["operations", "snapshot", "build"],
        ["operations", "snapshot", "validate"],
        ["operations", "decision", "build"],
        ["operations", "decision", "validate"],
        ["operations", "guide", "render"],
        ["operations", "guide", "run"],
        ["review", "daily", "verify"],
        ["review", "daily", "backtest-entry-band"],
        ["review", "daily", "backtest-entry-quality"],
        ["review", "intraday", "shadow", "build"],
        ["review", "intraday", "shadow", "validate"],
        ["automation", "rules", "check"],
        ["automation", "rules", "expert"],
        ["automation", "memory", "init"],
        ["automation", "scheduler", "run"],
        ["automation", "intraday", "run"],
    ],
)
def test_migrated_leaf_help_is_reachable(
    command: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as raised:
        main([*command, "--help"])

    assert raised.value.code == 0
    assert f"ashare-pilot {' '.join(command)}" in capsys.readouterr().out


def test_unknown_market_data_command_is_an_argparse_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["market-data", "not-a-command"])

    assert raised.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_leaf_help_does_not_require_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ASHARE_PILOT_WORKSPACE", raising=False)

    with pytest.raises(SystemExit) as raised:
        main(["market-data", "quote", "--help"])

    assert raised.value.code == 0
    assert "ashare-pilot market-data quote" in capsys.readouterr().out


def test_expert_rule_cli_add_preview_remove_and_never_reuse_id(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    workspace = make_workspace(tmp_path / "workspace")
    memory = workspace / "memory"
    memory.mkdir()
    template = (
        Path(__file__).resolve().parents[2]
        / "resources"
        / "templates"
        / "memory"
        / "EXPERT_RULES.md"
    )
    (memory / "EXPERT_RULES.md").write_text(
        template.read_text(encoding="utf-8"), encoding="utf-8"
    )
    base = [
        "--workspace",
        str(workspace),
        "automation",
        "rules",
        "expert",
    ]
    fields = [
        "--name",
        "弱市降低趋势接力",
        "--applies-to",
        "DAILY_STRATEGY",
        "--decision-layer",
        "ENTRY_POSITION",
        "--condition",
        "市场状态为 weak。",
        "--action",
        "仓位最多为 LIGHT。",
    ]

    assert main([*base, "add", *fields, "--dry-run"]) == 0
    assert '"id": "E001"' in capsys.readouterr().out
    assert '"rules": []' in (memory / "EXPERT_RULES.md").read_text(
        encoding="utf-8"
    )

    assert main([*base, "add", *fields]) == 0
    assert '"id": "E001"' in capsys.readouterr().out

    assert main([*base, "remove", "E001"]) == 0
    assert "Preview only" in capsys.readouterr().out
    assert "E001" in (memory / "EXPERT_RULES.md").read_text(encoding="utf-8")

    assert main([*base, "remove", "E001", "--yes"]) == 0
    assert "Removed E001" in capsys.readouterr().out

    assert main([*base, "add", *fields]) == 0
    assert '"id": "E002"' in capsys.readouterr().out
