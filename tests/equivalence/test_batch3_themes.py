from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from ashare_pilot.market_data.runtime import use_workspace
from ashare_pilot.themes import query_stock, query_theme
from ashare_pilot.themes._commands import dashboard, ranking
from ashare_pilot.themes._commands import concepts_fetch
from ashare_pilot.workspace import Workspace
from tests.equivalence.nondeterminism import normalize_nondeterminism

ROOT = Path(__file__).resolve().parents[2]
RANKING_FIXTURE = ROOT / "tests" / "fixtures" / "themes" / "ranking_input.json"


def load_old(name: str, path: Path):
    if not path.exists():
        pytest.skip("legacy implementation removed after equivalence acceptance")
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_copied_theme_queries_match_legacy_library() -> None:
    old = load_old(
        "legacy_query_theme_batch3",
        ROOT / ".opencode" / "skills" / "theme-library" / "scripts" / "query_theme.py",
    )
    workspace = Workspace(ROOT)

    assert query_theme("5G/6G通信", workspace=workspace) == old.query_theme("5G/6G通信")
    assert query_stock("sh600000", workspace=workspace) == old.query_stock("sh600000")


def test_theme_ranking_algorithm_matches_legacy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = json.loads(RANKING_FIXTURE.read_text(encoding="utf-8"))
    old = load_old(
        "legacy_theme_ranking_batch3",
        ROOT / ".opencode" / "skills" / "intraday-stock-discovery" / "scripts" / "compute_theme_ranking.py",
    )
    lookup = fixture["stock_themes"]
    monkeypatch.setattr(old, "query_stock", lambda code: lookup.get(code))
    monkeypatch.setattr(ranking, "query_stock", lambda code: lookup.get(code))

    old_scores = old.compute_theme_ranking(copy.deepcopy(fixture), pool_cutoff=40)
    new_scores = ranking.compute_theme_ranking(copy.deepcopy(fixture), pool_cutoff=40)

    assert new_scores == old_scores
    assert ranking.format_markdown(new_scores, top_n=10, date="2026-07-21") == old.format_markdown(
        old_scores, top_n=10, date="2026-07-21"
    )


def test_dashboard_scoring_matches_legacy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old = load_old(
        "legacy_dashboard_batch3",
        ROOT / ".opencode" / "skills" / "intraday-market-scan" / "scripts" / "build_concept_dashboard.py",
    )
    concepts = [
        {"code":"BK1","name":"主题一","change_pct":"+2.00%","net_inflow":"1.20","up_count":8,"down_count":2},
        {"code":"BK2","name":"主题二","change_pct":"+1.00%","net_inflow":"0.40","up_count":5,"down_count":4}
    ]
    momentum = [
        {"raw":2.0,"limit_up":2,"first_board":1,"continued_board":1,"member_count":10},
        {"raw":0.8,"limit_up":1,"first_board":1,"continued_board":0,"member_count":8},
    ]
    for module in (old, dashboard):
        monkeypatch.setattr(module, "_ds", SimpleNamespace(fetch_concept_ranking=lambda **kw: copy.deepcopy(concepts)))
        monkeypatch.setattr(module, "load_concept_to_stock", lambda: {})
        monkeypatch.setattr(module, "load_lianban_set", lambda mapping: set())
        monkeypatch.setattr(module, "compute_momentum", lambda *a, **kw: copy.deepcopy(momentum))

    old_result = old.build_dashboard(top=2)
    new_result = dashboard.build_dashboard(top=2)

    assert normalize_nondeterminism(
        new_result, "concept_dashboard"
    ) == normalize_nondeterminism(old_result, "concept_dashboard")


def test_concept_fetch_cli_and_files_match_legacy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    datasource = load_old(
        "datasource",
        ROOT / ".opencode" / "skills" / "theme-library" / "scripts" / "datasource.py",
    )
    monkeypatch.setitem(sys.modules, "datasource", datasource)
    old = load_old(
        "legacy_fetch_concepts_batch3",
        ROOT / ".opencode" / "skills" / "theme-library" / "scripts" / "fetch_concepts.py",
    )
    concepts = [
        {
            "code": "BK0001",
            "name": "样本概念",
            "change_pct": 1.25,
            "stock_count": 3,
            "lead_stock": "样本股份",
        }
    ]

    class Source:
        def __init__(self, **_kwargs):
            pass

        def fetch_concept_sectors(self, **_kwargs):
            return copy.deepcopy(concepts)

    cache = tmp_path / "cache"
    metadata = tmp_path / "metadata"
    for module in (old, concepts_fetch):
        monkeypatch.setattr(module, "CACHE_DIR", cache)
        monkeypatch.setattr(module, "METADATA_DIR", metadata)
        monkeypatch.setattr(module, "EastMoneyConceptSource", Source)

    monkeypatch.setattr(sys, "argv", ["fetch_concepts.py", "--json"])
    old.main()
    old_output = capsys.readouterr()
    old_cache = (cache / "concepts.json").read_text(encoding="utf-8")
    old_list = (metadata / "concept_list.json").read_text(encoding="utf-8")

    concepts_fetch.main(["--json"])
    new_output = capsys.readouterr()

    assert new_output == old_output
    assert (cache / "concepts.json").read_text(encoding="utf-8") == old_cache
    assert (metadata / "concept_list.json").read_text(encoding="utf-8") == old_list
