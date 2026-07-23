"""Initialize the zero-history memory skeleton and empty rule templates."""

from __future__ import annotations

import argparse
from pathlib import Path

from ashare_pilot.errors import WorkspaceError
from ashare_pilot.market_data.runtime import workspace_path


TEMPLATE_FILES = (
    "MEMORY.md",
    "RULE_GOVERNANCE.md",
    "PERFORMANCE.md",
    "RULES.md",
    "SHARED_RULES.md",
    "INTRADAY_RULES.md",
    "daily/INDEX.md",
    "intraday/INDEX.md",
)


def initialize_memory(root: Path) -> tuple[list[Path], list[Path]]:
    """Create missing memory templates without overwriting user state."""

    template_root = root / "resources" / "templates" / "memory"
    if not template_root.is_dir():
        raise WorkspaceError(f"Memory templates not found: {template_root}")

    memory_root = root / "memory"
    created: list[Path] = []
    existing: list[Path] = []
    for relative in TEMPLATE_FILES:
        source = template_root / relative
        if not source.is_file():
            raise WorkspaceError(f"Memory template not found: {source}")
        destination = memory_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            existing.append(destination)
            continue
        destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        created.append(destination)
    return created, existing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Initialize memory files and empty rule templates"
    )
    parser.parse_args(argv)
    root = workspace_path()
    created, existing = initialize_memory(root)
    for path in created:
        print(f"CREATED {path.relative_to(root).as_posix()}")
    for path in existing:
        print(f"KEPT {path.relative_to(root).as_posix()}")
    print(
        f"Memory initialized: created={len(created)}, kept={len(existing)}, "
        "rule_templates=3, executable_rules=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
