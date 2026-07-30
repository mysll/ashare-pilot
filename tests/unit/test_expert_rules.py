from __future__ import annotations

import json
from pathlib import Path

import pytest

from ashare_pilot.automation.expert_rules import (
    ExpertRuleError,
    ExpertRuleStore,
    add_rule,
    empty_store,
    load_store,
    normalize_draft,
    parse_markdown,
    remove_rule,
    render_markdown,
)


def draft(**overrides):
    value = {
        "name": "弱市降低趋势接力",
        "applies_to": ["DAILY_STRATEGY"],
        "decision_layer": "ENTRY_POSITION",
        "condition": "市场状态为 weak，且标的属于趋势接力。",
        "exclusions": ["标的触发更高层硬风控时不适用。"],
        "action": "仓位最多为 LIGHT。",
    }
    value.update(overrides)
    return value


def write_empty(path: Path) -> None:
    path.parent.mkdir(parents=True)
    path.write_text(render_markdown(empty_store()), encoding="utf-8")


def test_add_dry_run_and_remove_preserve_monotonic_id(tmp_path: Path) -> None:
    path = tmp_path / "memory" / "EXPERT_RULES.md"
    write_empty(path)

    preview = add_rule(path, draft(), dry_run=True)
    assert preview["id"] == "E001"
    assert load_store(path).next_id == 1

    first = add_rule(path, draft())
    assert first["id"] == "E001"
    assert load_store(path).next_id == 2

    remove_rule(path, "E001", confirmed=False)
    assert len(load_store(path).rules) == 1

    remove_rule(path, "E001", confirmed=True)
    after_remove = load_store(path)
    assert after_remove.next_id == 2
    assert after_remove.rules == ()

    second = add_rule(path, draft(name="第二条规则"))
    assert second["id"] == "E002"


def test_contract_rejects_unknown_consumers_fields_and_bad_next_id() -> None:
    with pytest.raises(ExpertRuleError, match="invalid values"):
        normalize_draft(draft(applies_to=["OPERATION_GUIDE"]))

    invalid_document = {
        "schema_version": "expert_rules.v1",
        "next_id": 1,
        "rules": [{"id": "E001", **draft()}],
    }
    with pytest.raises(ExpertRuleError, match="next_id"):
        parse_markdown(
            "# Expert Rules\n\n```json\n"
            + json.dumps(invalid_document, ensure_ascii=False)
            + "\n```\n"
        )

    with pytest.raises(ExpertRuleError, match="unexpected fields"):
        normalize_draft({**draft(), "status": "ACTIVE"})


def test_capacity_is_independent_and_hard_capped(tmp_path: Path) -> None:
    path = tmp_path / "memory" / "EXPERT_RULES.md"
    rules = tuple(
        {"id": f"E{index:03d}", **draft(name=f"rule-{index}")}
        for index in range(1, 21)
    )
    path.parent.mkdir(parents=True)
    path.write_text(
        render_markdown(ExpertRuleStore(next_id=21, rules=rules)),
        encoding="utf-8",
    )

    with pytest.raises(ExpertRuleError, match="capacity 20/20"):
        add_rule(path, draft(name="overflow"))
