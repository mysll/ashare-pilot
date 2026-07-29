"""Finalize validated Daily Theme annotations into ``themes.json``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
import time

from ashare_pilot.mapping.daily_contract import (
    default_predict_dir,
    ensure_doc_date,
    read_json,
    write_json,
)

from .contract import finalize_themes
from .timing import recorded_annotation_retry_count, safe_record_stage
from .validate_annotations import validate as validate_annotations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Finalize Daily Theme contract")
    parser.add_argument("--date", required=True)
    parser.add_argument("--evidence")
    parser.add_argument("--annotations")
    parser.add_argument("--output")
    parser.add_argument(
        "--validation-retries",
        type=int,
        choices=(0, 1),
        default=0,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--record-timing",
        action="store_true",
        help="Automatically record the theme_finalize stage",
    )
    args = parser.parse_args(argv)
    started_at = time.perf_counter()
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
    output_path = Path(args.output) if args.output else predict / "themes.json"
    try:
        evidence = read_json(evidence_path)
        annotations = read_json(annotations_path)
        if not isinstance(evidence, dict) or not isinstance(annotations, dict):
            raise ValueError("evidence and annotations roots must be objects")
        ensure_doc_date(evidence, args.date, str(evidence_path))
        ensure_doc_date(annotations, args.date, str(annotations_path))
        errors = validate_annotations(annotations, evidence)
        if errors:
            raise ValueError(
                "theme annotations failed validation:\n"
                + "\n".join(f"  - {error}" for error in errors)
            )
        doc = finalize_themes(evidence, annotations)
        if not any(item["status"] == "tradeable" for item in doc["themes"]):
            raise ValueError("themes.json must include at least one tradeable theme")
        write_json(output_path, doc)
    except (OSError, ValueError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    if args.record_timing:
        safe_record_stage(
            predict / "step1_timing.json",
            args.date,
            "theme_finalize",
            time.perf_counter() - started_at,
            [evidence_path, annotations_path],
            [output_path],
            {
                "themes": len(doc.get("themes", []))
                if isinstance(doc.get("themes"), list)
                else 0
            },
            recorded_annotation_retry_count(
                predict / "step1_timing.json", evidence_path
            ),
        )
    print(f"OK: wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
