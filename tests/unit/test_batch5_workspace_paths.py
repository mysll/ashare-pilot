from __future__ import annotations

import json
from pathlib import Path

from ashare_pilot.cli.app import main
from ashare_pilot.market_data.runtime import use_workspace
from ashare_pilot.strategy._commands.daily.render_report import workspace_root
from ashare_pilot.workspace import Workspace


def make_workspace(path: Path) -> Workspace:
    path.mkdir()
    (path / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
    (path / "config").mkdir()
    return Workspace(path.resolve())


def test_daily_renderer_uses_active_workspace(tmp_path: Path) -> None:
    first = make_workspace(tmp_path / "first")
    second = make_workspace(tmp_path / "second")

    with use_workspace(first):
        assert workspace_root() == first.root
    with use_workspace(second):
        assert workspace_root() == second.root


def test_overnight_build_cli_uses_explicit_workspace_outside_repo(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    workspace = make_workspace(tmp_path / "explicit")
    date = "2026-07-22"
    intraday = workspace.root / "intraday" / date
    intraday.mkdir(parents=True)
    mapper = {
        "schema_version": "intraday_mapper.v1",
        "date": date,
        "generated_at": f"{date}T06:30:00+00:00",
        "pool_summary": {"scoring_policy_version": "convergence_v1"},
        "market_assessment": {"regime": "neutral"},
        "strategy": {"position_cap": "0%"},
        "stocks": [],
    }
    (intraday / "intraday_mapper.json").write_text(
        json.dumps(mapper, ensure_ascii=False), encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        [
            "--workspace",
            str(workspace.root),
            "strategy",
            "overnight",
            "build",
            "--date",
            date,
        ]
    )

    assert exit_code == 0
    output = json.loads((intraday / "overnight_strategy.json").read_text(encoding="utf-8"))
    assert output["schema_version"] == "intraday_overnight_strategy.v1"
    assert output["positions"] == []
    assert "OK: wrote" in capsys.readouterr().out
