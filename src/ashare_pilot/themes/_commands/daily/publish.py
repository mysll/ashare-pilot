"""Validate annotations and atomically publish ``daily_themes.v2``."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time

from ashare_pilot.mapping.daily_contract import (
    default_predict_dir,
    ensure_doc_date,
    read_json,
    write_json,
)

from .contract import finalize_themes
from .timing import (
    annotation_validation_retry_count,
    safe_record_stage,
)
from .validate import validate as validate_contract
from .validate_annotations import validate as validate_annotations


def atomic_write_json(path: Path, doc: dict) -> None:
    """Replace a JSON contract only after its complete content is available."""

    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        write_json(temporary, doc)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def elapsed_since(path: Path) -> float | None:
    try:
        return max(0.0, time.time() - path.stat().st_mtime)
    except OSError:
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate and atomically publish Daily Theme outputs"
    )
    parser.add_argument("--date", required=True)
    parser.add_argument("--evidence")
    parser.add_argument("--annotations")
    parser.add_argument("--news")
    parser.add_argument("--news-md")
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    predict = default_predict_dir(args.date)
    evidence_path = (
        Path(args.evidence)
        if args.evidence
        else predict / ".theme_evidence_input.json"
    )
    annotations_path = (
        Path(args.annotations)
        if args.annotations
        else predict / ".theme_annotations.json"
    )
    news_path = Path(args.news) if args.news else predict / "news.json"
    news_md_path = (
        Path(args.news_md) if args.news_md else predict / "news.md"
    )
    output_path = Path(args.output) if args.output else predict / "themes.json"
    timing_path = predict / "step1_timing.json"

    try:
        if not news_md_path.exists():
            raise ValueError(f"missing news.md: {news_md_path}")
        evidence = read_json(evidence_path)
        annotations = read_json(annotations_path)
        news = read_json(news_path)
        if not all(
            isinstance(doc, dict) for doc in (evidence, annotations, news)
        ):
            raise ValueError(
                "evidence, annotations, and news roots must be objects"
            )
        ensure_doc_date(evidence, args.date, str(evidence_path))
        ensure_doc_date(annotations, args.date, str(annotations_path))
        ensure_doc_date(news, args.date, str(news_path))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    retries = annotation_validation_retry_count(timing_path, evidence_path)
    annotation_errors = validate_annotations(annotations, evidence)
    annotation_themes = annotations.get("themes")
    safe_record_stage(
        timing_path,
        args.date,
        "theme_llm",
        elapsed_since(evidence_path),
        [evidence_path],
        [annotations_path],
        {
            "themes": len(annotation_themes)
            if isinstance(annotation_themes, list)
            else 0
        },
        retries,
        "failed" if annotation_errors else "passed",
    )
    if annotation_errors:
        print(
            "[ERROR] annotations failed validation "
            f"({len(annotation_errors)} errors):",
            file=sys.stderr,
        )
        for error in annotation_errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    finalize_started_at = time.perf_counter()
    try:
        doc = finalize_themes(evidence, annotations)
        contract_errors = validate_contract(doc, evidence, annotations, news)
        if contract_errors:
            raise ValueError(
                "themes contract failed validation:\n"
                + "\n".join(f"  - {error}" for error in contract_errors)
            )
        atomic_write_json(output_path, doc)
        if not all(
            path.exists() for path in (news_path, news_md_path, output_path)
        ):
            raise ValueError(
                "news.json, news.md, and themes.json must all exist"
            )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        safe_record_stage(
            timing_path,
            args.date,
            "theme_finalize",
            time.perf_counter() - finalize_started_at,
            [evidence_path, annotations_path, news_path],
            [],
            {},
            retries,
            "failed",
        )
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    themes = doc.get("themes")
    safe_record_stage(
        timing_path,
        args.date,
        "theme_finalize",
        time.perf_counter() - finalize_started_at,
        [evidence_path, annotations_path, news_path],
        [output_path],
        {
            "themes": len(themes) if isinstance(themes, list) else 0,
        },
        retries,
        "passed",
    )
    print(f"OK: published {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
