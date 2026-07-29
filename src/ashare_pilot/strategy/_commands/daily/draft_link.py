"""Python-owned linkage between the current Step 3 input and its LLM draft."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .llm_input import canonical_sha256

INPUT_HASH_FILENAME = ".strategy_llm_input.sha256"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def write_input_hash(path: Path, compact: dict[str, Any]) -> str:
    """Atomically persist the canonical input fingerprint beside the input."""
    digest = canonical_sha256(compact)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(digest + "\n", encoding="ascii", newline="\n")
    temporary.replace(path)
    return digest


def validate_draft_link(
    compact: dict[str, Any],
    draft_path: Path,
    input_hash_path: Path,
) -> list[str]:
    """Verify the Python fingerprint and reject drafts predating current prepare."""
    errors: list[str] = []
    try:
        recorded_hash = input_hash_path.read_text(encoding="ascii").strip()
    except FileNotFoundError:
        return [f"input fingerprint: missing {input_hash_path.name}; rerun strategy daily prepare"]

    if not SHA256_RE.fullmatch(recorded_hash):
        errors.append(f"input fingerprint: {input_hash_path.name} is not a lowercase SHA-256")
    elif recorded_hash != canonical_sha256(compact):
        errors.append("input fingerprint: does not match current compact input; rerun strategy daily prepare")

    if not draft_path.exists():
        errors.append(f"draft linkage: missing {draft_path.name}")
    elif draft_path.stat().st_mtime_ns <= input_hash_path.stat().st_mtime_ns:
        errors.append("draft linkage: draft was not written after current prepare; regenerate the draft")
    return errors
