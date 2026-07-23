"""Public theme-library APIs with explicit Workspace context."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

from ashare_pilot.market_data.runtime import use_workspace
from ashare_pilot.workspace import Workspace

if TYPE_CHECKING:
    from ashare_pilot.themes.datasource import ConceptStocksFetchResult


def _query_module():
    return importlib.import_module("ashare_pilot.themes._commands.query")


def query_theme(name: str, *, workspace: Workspace) -> dict | None:
    with use_workspace(workspace):
        return _query_module().query_theme(name)


def query_concept(name: str, *, workspace: Workspace) -> dict | None:
    with use_workspace(workspace):
        return _query_module().query_concept(name)


def query_stock(code: str, *, workspace: Workspace) -> dict | None:
    with use_workspace(workspace):
        return _query_module().query_stock(code)


def query_keyword(
    keyword: str, *, workspace: Workspace
) -> tuple[str, str | None, str | None]:
    with use_workspace(workspace):
        return _query_module().query_keyword(keyword)


def list_themes(*, top: int = 0, workspace: Workspace) -> list:
    with use_workspace(workspace):
        return _query_module().list_themes(top=top)


def theme_library_stats(*, workspace: Workspace) -> dict:
    with use_workspace(workspace):
        return _query_module().show_stats()


def compute_theme_ranking(
    input_data: dict, *, pool_cutoff: int = 40, workspace: Workspace
) -> list:
    with use_workspace(workspace):
        module = importlib.import_module("ashare_pilot.themes._commands.ranking")
        return module.compute_theme_ranking(input_data, pool_cutoff=pool_cutoff)


def build_concept_dashboard(
    *, top: int = 100, cache_dir: str | None = None, workspace: Workspace
) -> dict:
    with use_workspace(workspace):
        module = importlib.import_module("ashare_pilot.themes._commands.dashboard")
        return module.build_dashboard(top=top, cache_dir=cache_dir)


def fetch_concepts(*, workspace: Workspace, **source_options) -> list:
    with use_workspace(workspace):
        module = importlib.import_module("ashare_pilot.themes.datasource")
        source = module.EastMoneyConceptSource(**source_options)
        return source.fetch_concept_sectors()


def fetch_concept_stocks(
    concept_code: str, *, workspace: Workspace, **source_options
) -> ConceptStocksFetchResult:
    with use_workspace(workspace):
        module = importlib.import_module("ashare_pilot.themes.datasource")
        source = module.EastMoneyConceptSource(**source_options)
        return source.fetch_concept_stocks(concept_code)
