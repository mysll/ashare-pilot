"""Validate the complete deterministic ``daily_themes.v2`` contract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ashare_pilot.mapping.daily_contract import (
    default_predict_dir,
    ensure_doc_date,
    read_json,
)

from .contract import THEMES_SCHEMA, finalize_themes, formal_theme_shape_errors
from .validate_annotations import validate as validate_annotations


def validate(
    doc: dict[str, Any],
    evidence_doc: dict[str, Any],
    annotations_doc: dict[str, Any],
    news_doc: dict[str, Any],
) -> list[str]:
    errors = validate_annotations(annotations_doc, evidence_doc)
    if doc.get("schema_version") != THEMES_SCHEMA:
        errors.append(f"schema_version: must be {THEMES_SCHEMA}")
    if any(
        candidate.get("date") != doc.get("date")
        for candidate in (evidence_doc, annotations_doc, news_doc)
    ):
        errors.append("date: themes, evidence, annotations, and news must match")
    if news_doc.get("schema_version") != "daily_news.v1":
        errors.append("news.schema_version: must be daily_news.v1")
    valid_news_refs = {
        f"news#{item['id']}"
        for item in news_doc.get("items", [])
        if isinstance(item, dict) and isinstance(item.get("id"), int)
    }
    themes = doc.get("themes")
    if not isinstance(themes, list):
        errors.append("themes: must be list")
        themes = []
    for i, theme in enumerate(themes):
        errors.extend(formal_theme_shape_errors(theme, f"themes[{i}]"))
        if not isinstance(theme, dict):
            continue
        for j, ref in enumerate(theme.get("evidence_refs", [])):
            if ref not in valid_news_refs:
                errors.append(
                    f"themes[{i}].evidence_refs[{j}]: missing from news.json"
                )
    if errors:
        return errors
    expected = finalize_themes(evidence_doc, annotations_doc)
    if doc != expected:
        errors.append(
            "themes: deterministic contract differs from evidence + annotations"
        )
    if not any(
        isinstance(item, dict) and item.get("status") == "tradeable"
        for item in doc.get("themes", [])
    ):
        errors.append("themes: must include at least one tradeable theme")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate daily_themes.v2")
    parser.add_argument("path", nargs="?")
    parser.add_argument("--date", required=True)
    parser.add_argument("--evidence")
    parser.add_argument("--annotations")
    parser.add_argument("--news")
    args = parser.parse_args(argv)
    predict = default_predict_dir(args.date)
    paths = {
        "themes": Path(args.path) if args.path else predict / "themes.json",
        "evidence": Path(args.evidence)
        if args.evidence
        else predict / ".theme_evidence_input.json",
        "annotations": Path(args.annotations)
        if args.annotations
        else predict / ".theme_annotations.json",
        "news": Path(args.news) if args.news else predict / "news.json",
    }
    try:
        docs = {name: read_json(path) for name, path in paths.items()}
        if not all(isinstance(doc, dict) for doc in docs.values()):
            raise ValueError("all roots must be objects")
        for name, doc in docs.items():
            ensure_doc_date(doc, args.date, str(paths[name]))
        errors = validate(
            docs["themes"], docs["evidence"], docs["annotations"], docs["news"]
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    if errors:
        print(f"[ERROR] themes failed validation ({len(errors)} errors):", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(f"OK: {paths['themes']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
