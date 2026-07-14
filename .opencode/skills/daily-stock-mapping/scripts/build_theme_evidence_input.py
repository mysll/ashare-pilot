#!/usr/bin/env python3
"""Build compact high-recall, non-contract theme evidence input."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from build_theme_stocks_base import theme_library_dir
from mapper_json_lib import clean_text, default_predict_dir, ensure_doc_date, read_json, utc_now_iso, write_json


HIGH_PRIORITY = {"policy", "flash", "sentiment", "market", "market_action"}


def terms_for_theme(theme: dict[str, Any]) -> set[str]:
    values = [theme.get("name")]
    for key in ("aliases", "keywords", "concepts"):
        if isinstance(theme.get(key), list):
            values.extend(theme[key])
    for item in theme.get("concept_weights", []) if isinstance(theme.get("concept_weights"), list) else []:
        if isinstance(item, dict):
            values.append(item.get("name"))
    return {str(value).strip().lower() for value in values if clean_text(value)}


def compact_news(items: list[Any]) -> list[dict[str, Any]]:
    by_title: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict) or not clean_text(item.get("title")) or not isinstance(item.get("id"), int):
            continue
        title = clean_text(item["title"])
        key = title.lower()
        if key not in by_title:
            by_title[key] = {"ids": [f"news#{item['id']}"], "category": item.get("category"), "source": item.get("source"), "title": title}
            desc = clean_text(item.get("desc"))
            if desc:
                by_title[key]["desc"] = desc
        else:
            by_title[key]["ids"].append(f"news#{item['id']}")
    return list(by_title.values())


def build_input(news_doc: dict[str, Any], library: Path) -> dict[str, Any]:
    compact = compact_news(news_doc.get("items", []))
    theme_rows = []
    matched_ids: set[str] = set()
    for path in sorted((library / "themes").glob("*.json")):
        data = read_json(path)
        if not isinstance(data, dict) or not clean_text(data.get("name")):
            continue
        terms = terms_for_theme(data)
        hits = []
        for item in compact:
            text = f"{item.get('title', '')} {item.get('desc', '')}".lower()
            if any(term in text for term in terms):
                hits.append(item)
                matched_ids.update(item["ids"])
        if hits:
            theme_rows.append({"name": data["name"], "items": hits})
    unmatched = [item for item in compact if item.get("category") in HIGH_PRIORITY and not matched_ids.intersection(item["ids"])]
    return {
        "schema_version": "theme_evidence_input.tmp.v1",
        "date": news_doc.get("date"),
        "generated_at": utc_now_iso(),
        "non_contract": True,
        "themes": theme_rows,
        "unmatched_high_priority": unmatched,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build compact theme evidence input")
    parser.add_argument("--date", required=True)
    parser.add_argument("--news")
    parser.add_argument("--theme-library")
    parser.add_argument("--output")
    args = parser.parse_args()
    predict = default_predict_dir(args.date)
    news_path = Path(args.news) if args.news else predict / "news.json"
    doc = read_json(news_path)
    if not isinstance(doc, dict):
        raise SystemExit("[ERROR] news.json root must be object")
    ensure_doc_date(doc, args.date, str(news_path))
    result = build_input(doc, Path(args.theme_library) if args.theme_library else theme_library_dir())
    output = Path(args.output) if args.output else predict / ".theme_evidence_input.json"
    write_json(output, result)
    print(f"OK: wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
