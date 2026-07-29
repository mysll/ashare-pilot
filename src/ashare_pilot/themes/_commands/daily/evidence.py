"""Build compact provenance-rich input for the Daily Theme LLM."""

from __future__ import annotations

import argparse
from pathlib import Path
import time
from typing import Any

from ashare_pilot.news.api import fetch_daily_news, write_news_outputs
from ashare_pilot.mapping.daily_contract import (
    clean_text,
    default_predict_dir,
    ensure_doc_date,
    read_json,
    write_json,
)
from ashare_pilot.market_data.runtime import workspace_path

from .contract import EVIDENCE_SCHEMA
from .timing import safe_record_stage


def theme_library_dir() -> Path:
    return workspace_path() / "data" / "theme-library"


def terms_for_theme(theme: dict[str, Any]) -> list[dict[str, str]]:
    values: list[tuple[str, Any]] = [("name", theme.get("name"))]
    for key, kind in (
        ("aliases", "alias"),
        ("keywords", "keyword"),
        ("concepts", "concept"),
    ):
        for value in theme.get(key, []) if isinstance(theme.get(key), list) else []:
            values.append((kind, value))
    for item in (
        theme.get("concept_weights", [])
        if isinstance(theme.get("concept_weights"), list)
        else []
    ):
        if isinstance(item, dict):
            values.append(("concept", item.get("name")))
    seen: set[tuple[str, str]] = set()
    result = []
    for kind, value in values:
        term = clean_text(value)
        key = (kind, (term or "").lower())
        if not term or key in seen:
            continue
        seen.add(key)
        result.append({"kind": kind, "term": term})
    return result


def compact_news(items: list[Any]) -> list[dict[str, Any]]:
    by_title: dict[str, dict[str, Any]] = {}
    for item in items:
        if (
            not isinstance(item, dict)
            or not clean_text(item.get("title"))
            or not isinstance(item.get("id"), int)
        ):
            continue
        title = clean_text(item["title"])
        assert title is not None
        key = title.casefold()
        ref = f"news#{item['id']}"
        if key not in by_title:
            by_title[key] = {
                "refs": [ref],
                "category": item.get("category"),
                "source": item.get("source"),
                "title": title,
            }
            desc = clean_text(item.get("desc"))
            if desc:
                by_title[key]["desc"] = desc
        else:
            by_title[key]["refs"].append(ref)
    return list(by_title.values())


def build_input(news_doc: dict[str, Any], library: Path) -> dict[str, Any]:
    compact = compact_news(
        news_doc.get("items", []) if isinstance(news_doc.get("items"), list) else []
    )
    theme_rows = []
    for path in sorted((library / "themes").glob("*.json")):
        data = read_json(path)
        if not isinstance(data, dict) or not clean_text(data.get("name")):
            continue
        terms = terms_for_theme(data)
        evidence = []
        matched_concepts: set[str] = set()
        for item in compact:
            text = f"{item.get('title', '')} {item.get('desc', '')}".casefold()
            matches = [
                term for term in terms if term["term"].casefold() in text
            ]
            if not matches:
                continue
            evidence.append({**item, "matches": matches})
            matched_concepts.update(
                match["term"] for match in matches if match["kind"] == "concept"
            )
        if evidence:
            theme_rows.append(
                {
                    "name": data["name"],
                    "matched_concepts": sorted(matched_concepts),
                    "evidence": evidence,
                    "market_signals": {
                        "available": False,
                        "trace": "no structured theme market signal",
                    },
                }
            )
    return {
        "schema_version": EVIDENCE_SCHEMA,
        "date": news_doc.get("date"),
        "themes": theme_rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare Daily Theme evidence")
    parser.add_argument("--date", required=True)
    parser.add_argument("--news")
    parser.add_argument("--theme-library")
    parser.add_argument("--output")
    parser.add_argument(
        "--fetch-news",
        action="store_true",
        help="Fetch and write canonical news before preparing Theme evidence",
    )
    parser.add_argument(
        "--record-timing",
        action="store_true",
        help="Automatically record the theme_prepare stage",
    )
    args = parser.parse_args(argv)
    if args.fetch_news and args.news:
        parser.error("--fetch-news cannot be combined with --news")
    predict = default_predict_dir(args.date)
    record_timing = args.fetch_news or args.record_timing
    if args.fetch_news:
        fetch_started_at = time.perf_counter()
        news_path, news_md_path = write_news_outputs(
            fetch_daily_news(),
            predict,
            report_date=args.date,
        )
        news = read_json(news_path)
        safe_record_stage(
            predict / "step1_timing.json",
            args.date,
            "news_fetch",
            time.perf_counter() - fetch_started_at,
            [],
            [news_path, news_md_path],
            {
                "news": len(news.get("items", []))
                if isinstance(news, dict)
                and isinstance(news.get("items"), list)
                else 0
            },
        )
    else:
        news_path = Path(args.news) if args.news else predict / "news.json"
        news = read_json(news_path) if news_path.exists() else None
    prepare_started_at = time.perf_counter()
    if not news_path.exists():
        parser.error(f"missing news.json: {news_path}")
    if not isinstance(news, dict):
        parser.error("news.json root must be object")
    ensure_doc_date(news, args.date, str(news_path))
    if news.get("schema_version") != "daily_news.v1":
        parser.error("news.json schema_version must be daily_news.v1")
    output = (
        Path(args.output) if args.output else predict / ".theme_evidence_input.json"
    )
    doc = build_input(
        news,
        Path(args.theme_library)
        if args.theme_library
        else theme_library_dir(),
    )
    write_json(output, doc)
    if record_timing:
        safe_record_stage(
            predict / "step1_timing.json",
            args.date,
            "theme_prepare",
            time.perf_counter() - prepare_started_at,
            [news_path],
            [output],
            {
                "themes": len(doc.get("themes", []))
                if isinstance(doc.get("themes"), list)
                else 0
            },
        )
    print(f"OK: wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
