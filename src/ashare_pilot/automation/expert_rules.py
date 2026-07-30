"""Canonical storage and validation for manually authorized expert rules."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "expert_rules.v1"
MAX_RULES = 20
APPLIES_TO = ("DAILY_STRATEGY", "OVERNIGHT_STRATEGY")
DECISION_LAYERS = (
    "RISK_CONTROL",
    "REGIME",
    "ELIGIBILITY",
    "ENTRY_POSITION",
    "RANKING",
)
RULE_FIELDS = {
    "id",
    "name",
    "applies_to",
    "decision_layer",
    "condition",
    "exclusions",
    "action",
}
DRAFT_FIELDS = RULE_FIELDS - {"id"}
RULE_ID_RE = re.compile(r"^E(\d{3,})$")
DOCUMENT_RE = re.compile(
    r"```json\s*\n(?P<payload>\{.*?\})\s*\n```",
    re.DOTALL,
)


class ExpertRuleError(ValueError):
    """Raised when the expert-rule contract is invalid."""


@dataclass(frozen=True, slots=True)
class ExpertRuleStore:
    next_id: int
    rules: tuple[dict[str, Any], ...]

    def as_document(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "next_id": self.next_id,
            "rules": [dict(rule) for rule in self.rules],
        }


def empty_store() -> ExpertRuleStore:
    return ExpertRuleStore(next_id=1, rules=())


def rule_id(number: int) -> str:
    return f"E{number:03d}"


def _non_empty_text(value: Any, path: str, errors: list[str]) -> str | None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path}: must be a non-empty string")
        return None
    return value.strip()


def normalize_draft(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ExpertRuleError("rule draft must be an object")

    errors: list[str] = []
    extra = sorted(set(value) - DRAFT_FIELDS)
    missing = sorted(DRAFT_FIELDS - set(value))
    if extra:
        errors.append(f"rule draft: unexpected fields {extra}")
    if missing:
        errors.append(f"rule draft: missing fields {missing}")

    name = _non_empty_text(value.get("name"), "name", errors)
    condition = _non_empty_text(value.get("condition"), "condition", errors)
    action = _non_empty_text(value.get("action"), "action", errors)

    raw_consumers = value.get("applies_to")
    consumers: list[str] = []
    if not isinstance(raw_consumers, list) or not raw_consumers:
        errors.append("applies_to: must be a non-empty list")
    else:
        if not all(isinstance(item, str) for item in raw_consumers):
            errors.append("applies_to: every item must be a string")
        else:
            invalid = sorted(set(raw_consumers) - set(APPLIES_TO))
            if invalid:
                errors.append(f"applies_to: invalid values {invalid}")
            if len(raw_consumers) != len(set(raw_consumers)):
                errors.append("applies_to: duplicate values are not allowed")
            consumers = [item for item in APPLIES_TO if item in raw_consumers]

    layer = value.get("decision_layer")
    if layer not in DECISION_LAYERS:
        errors.append(
            f"decision_layer: must be one of {list(DECISION_LAYERS)}"
        )

    raw_exclusions = value.get("exclusions")
    exclusions: list[str] = []
    if not isinstance(raw_exclusions, list):
        errors.append("exclusions: must be a list")
    else:
        for index, item in enumerate(raw_exclusions):
            normalized = _non_empty_text(
                item, f"exclusions[{index}]", errors
            )
            if normalized is not None:
                exclusions.append(normalized)

    if errors:
        raise ExpertRuleError("; ".join(errors))

    return {
        "name": name,
        "applies_to": consumers,
        "decision_layer": layer,
        "condition": condition,
        "exclusions": exclusions,
        "action": action,
    }


def validate_store_document(value: Any) -> ExpertRuleStore:
    if not isinstance(value, dict):
        raise ExpertRuleError("expert rule document must be an object")

    errors: list[str] = []
    expected_root = {"schema_version", "next_id", "rules"}
    extra_root = sorted(set(value) - expected_root)
    missing_root = sorted(expected_root - set(value))
    if extra_root:
        errors.append(f"document: unexpected fields {extra_root}")
    if missing_root:
        errors.append(f"document: missing fields {missing_root}")
    if value.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version: must be {SCHEMA_VERSION}")

    next_id = value.get("next_id")
    if (
        not isinstance(next_id, int)
        or isinstance(next_id, bool)
        or next_id < 1
    ):
        errors.append("next_id: must be a positive integer")

    raw_rules = value.get("rules")
    normalized_rules: list[dict[str, Any]] = []
    seen: set[str] = set()
    max_number = 0
    if not isinstance(raw_rules, list):
        errors.append("rules: must be a list")
    else:
        if len(raw_rules) > MAX_RULES:
            errors.append(f"rules: capacity {len(raw_rules)}/{MAX_RULES} exceeded")
        for index, item in enumerate(raw_rules):
            base = f"rules[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{base}: must be an object")
                continue
            extra = sorted(set(item) - RULE_FIELDS)
            missing = sorted(RULE_FIELDS - set(item))
            if extra:
                errors.append(f"{base}: unexpected fields {extra}")
            if missing:
                errors.append(f"{base}: missing fields {missing}")
            current_id = item.get("id")
            match = RULE_ID_RE.fullmatch(current_id) if isinstance(current_id, str) else None
            if match is None:
                errors.append(f"{base}.id: must match E001, E002, ...")
            else:
                number = int(match.group(1))
                if number < 1:
                    errors.append(f"{base}.id: must be E001 or greater")
                if current_id in seen:
                    errors.append(f"{base}.id: duplicate {current_id}")
                seen.add(current_id)
                max_number = max(max_number, number)
            try:
                draft = normalize_draft(
                    {key: item.get(key) for key in DRAFT_FIELDS}
                )
            except ExpertRuleError as exc:
                errors.append(f"{base}: {exc}")
                continue
            if match is not None:
                normalized_rules.append({"id": current_id, **draft})

    if isinstance(next_id, int) and not isinstance(next_id, bool):
        if next_id <= max_number:
            errors.append(
                f"next_id: must be greater than every allocated current ID ({max_number})"
            )

    if errors:
        raise ExpertRuleError("; ".join(errors))

    normalized_rules.sort(key=lambda item: int(item["id"][1:]))
    return ExpertRuleStore(next_id=next_id, rules=tuple(normalized_rules))


def parse_markdown(text: str) -> ExpertRuleStore:
    match = DOCUMENT_RE.search(text)
    if match is None:
        raise ExpertRuleError("EXPERT_RULES.md must contain one json code block")
    if len(DOCUMENT_RE.findall(text)) != 1:
        raise ExpertRuleError("EXPERT_RULES.md must contain exactly one json code block")
    try:
        document = json.loads(match.group("payload"))
    except json.JSONDecodeError as exc:
        raise ExpertRuleError(f"invalid expert rule JSON: {exc}") from exc
    return validate_store_document(document)


def render_markdown(store: ExpertRuleStore) -> str:
    document = json.dumps(
        store.as_document(), ensure_ascii=False, indent=2
    )
    return (
        "# Expert Rules\n\n"
        "> 专家直接授权的自然语言规则。规则存在即生效；仅通过 "
        "`ashare-pilot automation rules expert` 修改。\n"
        "> 生命周期、优先级和边界见 [RULE_GOVERNANCE.md]"
        "(RULE_GOVERNANCE.md) 与 "
        "[ADR-0005](../docs/adr/0005-expert-rule-system.md)。\n\n"
        "```json\n"
        f"{document}\n"
        "```\n"
    )


def load_store(path: Path) -> ExpertRuleStore:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ExpertRuleError(
            f"missing {path}; run 'ashare-pilot automation memory init'"
        ) from exc
    except OSError as exc:
        raise ExpertRuleError(f"cannot read {path}: {exc}") from exc
    return parse_markdown(text)


def atomic_write_store(path: Path, store: ExpertRuleStore) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(
            render_markdown(store), encoding="utf-8", newline="\n"
        )
        temporary.replace(path)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise ExpertRuleError(f"cannot write {path}: {exc}") from exc


def preview_rule(store: ExpertRuleStore, draft: Any) -> dict[str, Any]:
    return {"id": rule_id(store.next_id), **normalize_draft(draft)}


def add_rule(
    path: Path, draft: Any, *, dry_run: bool = False
) -> dict[str, Any]:
    store = load_store(path)
    if len(store.rules) >= MAX_RULES:
        raise ExpertRuleError(
            f"expert rule capacity {len(store.rules)}/{MAX_RULES} reached"
        )
    rule = preview_rule(store, draft)
    if not dry_run:
        updated = ExpertRuleStore(
            next_id=store.next_id + 1,
            rules=(*store.rules, rule),
        )
        atomic_write_store(path, updated)
    return rule


def remove_rule(path: Path, target_id: str, *, confirmed: bool) -> dict[str, Any]:
    store = load_store(path)
    target = next((rule for rule in store.rules if rule["id"] == target_id), None)
    if target is None:
        raise ExpertRuleError(f"expert rule not found: {target_id}")
    if confirmed:
        updated = ExpertRuleStore(
            next_id=store.next_id,
            rules=tuple(rule for rule in store.rules if rule["id"] != target_id),
        )
        atomic_write_store(path, updated)
    return dict(target)


def find_rule(store: ExpertRuleStore, target_id: str) -> dict[str, Any]:
    target = next((rule for rule in store.rules if rule["id"] == target_id), None)
    if target is None:
        raise ExpertRuleError(f"expert rule not found: {target_id}")
    return dict(target)
