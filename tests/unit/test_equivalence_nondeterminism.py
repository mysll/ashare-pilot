from __future__ import annotations

import pytest

from tests.equivalence.nondeterminism import (
    APPROVED_NONDETERMINISTIC_FIELDS,
    normalize_nondeterminism,
)


def test_every_allowed_field_has_a_specific_reason() -> None:
    assert APPROVED_NONDETERMINISTIC_FIELDS
    for fields in APPROVED_NONDETERMINISTIC_FIELDS.values():
        assert fields
        for field in fields:
            assert field.path
            assert len(field.reason.split()) >= 5


def test_normalizer_is_copying_strict_and_contract_scoped() -> None:
    source = {"meta": {"timestamp": "now", "value": 1}}

    assert normalize_nondeterminism(source, "concept_dashboard") == {
        "meta": {"value": 1}
    }
    assert source["meta"]["timestamp"] == "now"
    with pytest.raises(KeyError):
        normalize_nondeterminism(source, "not-approved")
    with pytest.raises(AssertionError):
        normalize_nondeterminism({"meta": {}}, "concept_dashboard")
