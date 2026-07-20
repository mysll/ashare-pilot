#!/usr/bin/env python3
"""Static checks for the Markdown rule-governance contract."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MEMORY = ROOT / "memory"
RULE_FILES = {
    "morning": (MEMORY / "RULES.md", 20, "R"),
    "shared": (MEMORY / "SHARED_RULES.md", 15, "R"),
    "intraday": (MEMORY / "INTRADAY_RULES.md", 15, "I"),
}


def section(text: str, heading: str) -> str:
    marker = f"## {heading}"
    if marker not in text:
        raise ValueError(f"missing section: {marker}")
    body = text.split(marker, 1)[1]
    return body.split("\n## ", 1)[0]


def executable_ids(text: str, prefix: str) -> list[str]:
    body = section(text, "可执行规则族")
    pattern = re.compile(rf"^\|\s*({prefix}\d+)\s*\|", re.MULTILINE)
    return pattern.findall(body)


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def main() -> int:
    errors: list[str] = []
    all_canonical: dict[str, str] = {}

    for scope, (path, cap, prefix) in RULE_FILES.items():
        if not path.exists():
            fail(errors, f"{scope}: missing {path.relative_to(ROOT)}")
            continue
        text = path.read_text(encoding="utf-8")
        try:
            ids = executable_ids(text, prefix)
            executable_body = section(text, "可执行规则族")
        except ValueError as exc:
            fail(errors, f"{scope}: {exc}")
            continue
        if len(ids) != len(set(ids)):
            fail(errors, f"{scope}: duplicate executable IDs: {ids}")
        if len(ids) > cap:
            fail(errors, f"{scope}: capacity {len(ids)}/{cap} exceeded")
        if "📝" in executable_body:
            fail(errors, f"{scope}: candidate status appears in executable section")
        for rule_id in ids:
            previous = all_canonical.get(rule_id)
            if previous:
                fail(errors, f"canonical {rule_id} appears in both {previous} and {scope}")
            all_canonical[rule_id] = scope
        if "RULE_GOVERNANCE.md" not in text:
            fail(errors, f"{scope}: missing governance link")

    expected_counts = {"morning": 17, "shared": 11, "intraday": 14}
    for scope, expected in expected_counts.items():
        path, _, prefix = RULE_FILES[scope]
        if path.exists():
            actual = len(executable_ids(path.read_text(encoding="utf-8"), prefix))
            if actual != expected:
                fail(errors, f"{scope}: expected migrated count {expected}, found {actual}")

    governance = MEMORY / "RULE_GOVERNANCE.md"
    if not governance.exists():
        fail(errors, "missing memory/RULE_GOVERNANCE.md")
    else:
        governance_text = governance.read_text(encoding="utf-8")
        required = [
            "CONTRACT",
            "RISK_POLICY",
            "EMPIRICAL",
            "REFERENCE",
            "RETIRED",
            "NO_TRADE_CONFLICT",
            "not_triggered",
            "memory/intraday/{date}/intraday_verification.md",
        ]
        for token in required:
            if token not in governance_text:
                fail(errors, f"governance: missing required token {token!r}")

    intraday_text = (MEMORY / "INTRADAY_RULES.md").read_text(encoding="utf-8")
    try:
        candidate = section(intraday_text, "候选规则（不执行、不计容量）")
    except ValueError as exc:
        fail(errors, f"intraday: {exc}")
        candidate = ""
    for candidate_id in ("I09-v3", "I21.b"):
        if candidate_id not in candidate:
            fail(errors, f"intraday: candidate {candidate_id} missing from candidate section")

    active_intraday = section(intraday_text, "可执行规则族")
    for retired_id in ("I09-v2", "I11-v2", "I15-v2", "I17-v2", "I18", "I21-v2"):
        if re.search(rf"^\|\s*{re.escape(retired_id)}\s*\|", active_intraday, re.MULTILINE):
            fail(errors, f"intraday: retired ID {retired_id} remains executable")

    for path in [p for p, _, _ in RULE_FILES.values()]:
        text = path.read_text(encoding="utf-8")
        if "daily/YYYY-MM-DD/intraday_verification.md" in text:
            fail(errors, f"{path.name}: obsolete intraday verification path")

    for guide in (ROOT / "AGENTS.md", ROOT / "CLAUDE.md", MEMORY / "MEMORY.md"):
        text = guide.read_text(encoding="utf-8")
        if "RULE_GOVERNANCE.md" not in text:
            fail(errors, f"{guide.relative_to(ROOT)}: missing governance navigation")

    if errors:
        for message in errors:
            print(f"ERROR: {message}", file=sys.stderr)
        return 1

    counts = []
    for scope, (path, cap, prefix) in RULE_FILES.items():
        count = len(executable_ids(path.read_text(encoding="utf-8"), prefix))
        counts.append(f"{scope}={count}/{cap}")
    print("Rule governance OK: " + ", ".join(counts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
