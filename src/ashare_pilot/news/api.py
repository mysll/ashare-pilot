"""Public APIs for deterministic news normalization and output."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from ashare_pilot.news.fetch import (
    NEWS_SOURCES,
    _clean,
    build_news_document,
    format_brief,
)

NewsFetcher = Callable[[], list[dict[str, str]]]


def fetch_daily_news(
    sources: Sequence[str] | None = None,
    *,
    source_fetchers: Mapping[str, NewsFetcher] | None = None,
) -> dict[str, list[dict[str, str]]]:
    """Fetch selected sources without printing progress or warnings.

    ``source_fetchers`` replaces the network boundary for offline tests and
    callers that provide recorded responses.
    """

    available = NEWS_SOURCES if source_fetchers is None else source_fetchers
    selected = list(available) if sources is None else list(sources)
    unknown = [name for name in selected if name not in available]
    if unknown:
        raise ValueError(f"Unknown news sources: {', '.join(unknown)}")

    result: dict[str, list[dict[str, str]]] = {}
    for name in selected:
        try:
            result[name] = [_clean(item) for item in available[name]()]
        except Exception:
            result[name] = []
    return result


def write_news_outputs(
    news: dict[str, list[dict[str, str]]],
    output_dir: str | Path,
    *,
    report_date: str | None = None,
) -> tuple[Path, Path]:
    """Write canonical JSON and readable Markdown, returning both paths."""

    doc: dict[str, Any] = build_news_document(news, report_date)
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / "news.json"
    markdown_path = directory / "news.md"
    json_path.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    markdown_path.write_text(format_brief(doc), encoding="utf-8", newline="\n")
    return json_path, markdown_path
