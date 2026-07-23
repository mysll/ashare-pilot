from __future__ import annotations

import importlib.util
import json
from datetime import datetime as RealDatetime
from pathlib import Path

import pytest

from ashare_pilot.news import (
    build_news_document,
    fetch_daily_news,
    format_brief,
    write_news_outputs,
)
from ashare_pilot.news import fetch as new_fetch

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "news" / "source_items.json"
OLD_PATH = ROOT / ".opencode" / "skills" / "daily-news-brief" / "scripts" / "fetch_news.py"


class FixedDatetime(RealDatetime):
    @classmethod
    def now(cls, tz=None):
        value = cls(2026, 7, 21, 14, 30, 0)
        return value.astimezone() if tz is None else value.replace(tzinfo=tz)


def load_old():
    if not OLD_PATH.exists():
        pytest.skip("legacy implementation removed after equivalence acceptance")
    spec = importlib.util.spec_from_file_location("legacy_fetch_news", OLD_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_normalization_document_and_markdown_are_equivalent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["sources"]
    fetchers = {name: (lambda items=items: items) for name, items in fixture.items()}
    news = fetch_daily_news(source_fetchers=fetchers)
    old = load_old()
    monkeypatch.setattr(old, "datetime", FixedDatetime)
    monkeypatch.setattr(new_fetch, "datetime", FixedDatetime)

    old_doc = old.build_news_document(news, "2026-07-21")
    new_doc = build_news_document(news, "2026-07-21")

    assert new_doc == old_doc
    assert format_brief(new_doc) == old.format_brief(old_doc)
    assert new_doc["items"][0]["title"] == "政策样本"
    assert [item["id"] for item in new_doc["items"]] == [1, 2]


def test_dual_outputs_match_legacy_rendering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["sources"]
    monkeypatch.setattr(new_fetch, "datetime", FixedDatetime)

    json_path, markdown_path = write_news_outputs(
        fixture, tmp_path, report_date="2026-07-21"
    )
    document = json.loads(json_path.read_text(encoding="utf-8"))

    assert json_path.name == "news.json"
    assert markdown_path.name == "news.md"
    assert markdown_path.read_text(encoding="utf-8") == format_brief(document)
    assert json_path.read_bytes().endswith(b"\n")


def test_failed_source_is_empty_and_public_api_is_silent(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def failed() -> list[dict[str, str]]:
        raise RuntimeError("recorded failure")

    result = fetch_daily_news(source_fetchers={"failed": failed})

    assert result == {"failed": []}
    assert capsys.readouterr() == ("", "")
