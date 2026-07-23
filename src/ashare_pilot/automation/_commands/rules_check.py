#!/usr/bin/env python3
"""Static checks for the Markdown rule-governance contract."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from ashare_pilot.market_data.runtime import workspace_path


def rule_files(root: Path) -> dict[str, tuple[Path, int, str]]:
    memory = root / "memory"
    return {
        "morning": (memory / "RULES.md", 20, "R"),
        "shared": (memory / "SHARED_RULES.md", 15, "R"),
        "intraday": (memory / "INTRADAY_RULES.md", 15, "I"),
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


def check_rule_governance(root: Path) -> list[str]:
    errors: list[str] = []
    all_canonical: dict[str, str] = {}
    memory = root / "memory"
    files = rule_files(root)

    for scope, (path, cap, prefix) in files.items():
        if not path.exists():
            fail(errors, f"{scope}: missing {path.relative_to(root)}")
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

    governance = memory / "RULE_GOVERNANCE.md"
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

    intraday_path = memory / "INTRADAY_RULES.md"
    intraday_text = intraday_path.read_text(encoding="utf-8") if intraday_path.exists() else ""
    try:
        candidate = section(intraday_text, "候选规则（不执行、不计容量）")
    except ValueError as exc:
        fail(errors, f"intraday: {exc}")
        candidate = ""
    for path in [p for p, _, _ in files.values() if p.exists()]:
        text = path.read_text(encoding="utf-8")
        if "daily/YYYY-MM-DD/intraday_verification.md" in text:
            fail(errors, f"{path.name}: obsolete intraday verification path")

    for guide in (root / "AGENTS.md", root / "CLAUDE.md", memory / "MEMORY.md"):
        if not guide.exists():
            fail(errors, f"{guide.relative_to(root)}: missing governance navigation")
            continue
        text = guide.read_text(encoding="utf-8")
        if "RULE_GOVERNANCE.md" not in text:
            fail(errors, f"{guide.relative_to(root)}: missing governance navigation")

    return errors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check Markdown rule governance")
    parser.parse_args(argv)
    root = workspace_path()
    files = rule_files(root)
    errors = check_rule_governance(root)

    if errors:
        for message in errors:
            print(f"ERROR: {message}", file=sys.stderr)
        return 1

    counts = []
    for scope, (path, cap, prefix) in files.items():
        count = len(executable_ids(path.read_text(encoding="utf-8"), prefix))
        counts.append(f"{scope}={count}/{cap}")
    print("Rule governance OK: " + ", ".join(counts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
