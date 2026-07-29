from __future__ import annotations

import json
from pathlib import Path

from ashare_pilot.cli.app import main
from ashare_pilot.mapping.daily_contract import build_deterministic_mapper_base
from ashare_pilot.mapping.daily_contract import default_predict_dir, default_scope_path
from ashare_pilot.mapping.intraday_contract import cache_dir, intraday_dir
from ashare_pilot.mapping._commands.daily.theme_stock_base import theme_library_dir
from ashare_pilot.market_data.runtime import use_workspace
from ashare_pilot.workspace import Workspace


def make_workspace(path: Path) -> Workspace:
    path.mkdir()
    (path / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
    (path / "config").mkdir()
    (path / "config" / "trading-scope.json").write_text(
        json.dumps({"boards": {}, "overrides": []}), encoding="utf-8"
    )
    return Workspace(path.resolve())


def test_mapping_paths_follow_explicit_workspace(tmp_path: Path) -> None:
    workspace = make_workspace(tmp_path / "mapping-workspace")

    with use_workspace(workspace):
        assert default_predict_dir("2026-07-22") == workspace.root / "predict" / "2026-07-22"
        assert intraday_dir("2026-07-22") == workspace.root / "intraday" / "2026-07-22"
        assert cache_dir("2026-07-22") == workspace.cache_dir / "intraday" / "2026-07-22"
        assert default_scope_path() == workspace.config_dir / "trading-scope.json"
        assert theme_library_dir() == workspace.data_dir / "theme-library"


def test_mapping_paths_switch_without_module_reload(tmp_path: Path) -> None:
    first = make_workspace(tmp_path / "first")
    second = make_workspace(tmp_path / "second")

    with use_workspace(first):
        first_path = default_predict_dir("2026-07-22")
    with use_workspace(second):
        second_path = default_predict_dir("2026-07-22")

    assert first_path.parent.parent == first.root
    assert second_path.parent.parent == second.root


def test_daily_mapper_cli_uses_workspace_outside_repository(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    workspace = make_workspace(tmp_path / "explicit")
    date = "2026-07-22"
    output_dir = workspace.root / "predict" / date
    output_dir.mkdir(parents=True)
    theme_stocks = {
        "schema_version": "daily_theme_stocks.v2",
        "date": date,
        "themes": [
            {
                "name": "银行",
                "rank": 1,
                "final_heat": 70,
                "attention_direction": "bullish",
                "evidence_refs": [],
            }
        ],
        "stocks": [
            {
                "code": "sz000001",
                "name": "平安银行",
                "source_themes": [{"name": "银行", "score": 70}],
                "filter": {"status": "candidate"},
            }
        ],
    }
    pool = {
        "sz000001": {
            "code": "sz000001",
            "raw_observation": {},
            "computed_perception": {},
        }
    }
    with use_workspace(workspace):
        base = build_deterministic_mapper_base(date, pool, theme_stocks)
    (output_dir / "mapper.base.json").write_text(
        json.dumps(base, ensure_ascii=False), encoding="utf-8"
    )
    (output_dir / "mapper.annotations.json").write_text(
        json.dumps(
            {
                "schema_version": "daily_mapper_annotations.v1",
                "date": date,
                "stocks": [
                    {
                        "code": "sz000001",
                        "news_relevance": {
                            "r": "R0",
                            "p": "P0",
                            "confidence": 90,
                            "trace": "none",
                        },
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        [
            "--workspace",
            str(workspace.root),
            "mapping",
            "daily",
            "build-mapper",
            "--date",
            date,
        ]
    )

    assert exit_code == 0
    assert (output_dir / "mapper.json").is_file()
    assert "OK: wrote" in capsys.readouterr().out
