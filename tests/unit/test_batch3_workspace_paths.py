from __future__ import annotations

import json
from pathlib import Path

from ashare_pilot.market_data.runtime import use_workspace
from ashare_pilot.themes import query_theme
from ashare_pilot.themes._commands import library_build
from ashare_pilot.workspace import Workspace


def make_workspace(path: Path) -> Workspace:
    path.mkdir()
    (path / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
    (path / "config" / "themes").mkdir(parents=True)
    return Workspace(path.resolve())


def test_theme_query_switches_between_explicit_workspaces(tmp_path: Path) -> None:
    first = make_workspace(tmp_path / "first")
    second = make_workspace(tmp_path / "second")
    for workspace, marker in ((first, "first"), (second, "second")):
        themes = workspace.data_dir / "theme-library" / "themes"
        themes.mkdir(parents=True)
        (themes / "样本主题.json").write_text(
            json.dumps({"name": "样本主题", "marker": marker}, ensure_ascii=False),
            encoding="utf-8",
        )

    assert query_theme("样本主题", workspace=first)["marker"] == "first"
    assert query_theme("样本主题", workspace=second)["marker"] == "second"


def test_library_configuration_is_loaded_from_active_workspace(tmp_path: Path) -> None:
    workspace = make_workspace(tmp_path / "configured")
    config = {
        "themes": {"样本主题": {"concepts": ["样本概念"]}},
        "concept_aliases": {},
        "related_themes": {},
    }
    (workspace.config_dir / "themes" / "theme-config.json").write_text(
        json.dumps(config, ensure_ascii=False), encoding="utf-8"
    )

    with use_workspace(workspace):
        library_build.reload_configuration()
        assert "样本主题" in library_build.THEMES_CONFIG
