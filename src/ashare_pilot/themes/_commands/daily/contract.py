"""Contracts and deterministic calculations for ``daily_themes.v2``."""

from __future__ import annotations

import re
from typing import Any


EVIDENCE_SCHEMA = "theme_evidence_input.tmp.v2"
ANNOTATIONS_SCHEMA = "daily_theme_annotations.v1"
THEMES_SCHEMA = "daily_themes.v2"
ATTENTION_DIRECTIONS = {"bullish", "mixed", "panic", "neutral", "unknown"}
EMOTION_COEFFICIENTS = {
    "bullish": 1.0,
    "mixed": 0.8,
    "panic": 0.5,
    "neutral": 0.8,
    "unknown": 0.8,
}
POLICY_BONUSES = {
    "none": 0,
    "local": 2,
    "ministry": 5,
    "state_council": 8,
    "national_strategy": 10,
}
POLICY_COEFFICIENTS = {"bullish": 1.0, "neutral": 0.5, "bearish": 0.0}
CATALYST_TYPES = {
    "landmark_ipo",
    "first_national_policy",
    "bellwether_product_or_breakthrough",
    "major_national_contract",
}
MATCH_KINDS = {"name", "alias", "keyword", "concept"}
NEWS_REF_RE = re.compile(r"^news#([1-9]\d*|0)$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
NUMERIC_TOLERANCE = 0.005
FORMAL_THEME_FIELDS = {
    "rank",
    "name",
    "status",
    "confidence",
    "attention_direction",
    "score",
    "catalyst",
    "matched_concepts",
    "evidence_refs",
    "reason",
}
FORMAL_SCORE_FIELDS = {
    "market_action",
    "emotion_raw",
    "emotion_coefficient",
    "news_density",
    "capital",
    "base_heat",
    "policy",
    "final_heat",
}
FORMAL_POLICY_FIELDS = {
    "tier",
    "polarity",
    "bonus",
    "coefficient",
    "evidence_ref",
}


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def round_score(value: float) -> float:
    """Apply the only rounding rule used by the v2 Theme contract."""

    return round(float(value) + 1e-12, 2)


def score_components(
    market_action: float,
    emotion_raw: float,
    attention_direction: str,
    distinct_evidence_count: int,
    capital: float,
    policy_tier: str,
    policy_polarity: str,
) -> dict[str, Any]:
    emotion_coefficient = EMOTION_COEFFICIENTS[attention_direction]
    news_density = round_score(min(distinct_evidence_count, 10) / 10 * 100)
    base_heat = round_score(
        market_action * 0.45
        + emotion_raw * emotion_coefficient * 0.30
        + news_density * 0.15
        + capital * 0.10
    )
    policy_bonus = POLICY_BONUSES[policy_tier]
    policy_coefficient = POLICY_COEFFICIENTS[policy_polarity]
    policy_adjusted_heat = round_score(
        base_heat + policy_bonus * policy_coefficient
    )
    return {
        "emotion_coefficient": emotion_coefficient,
        "news_density": news_density,
        "base_heat": base_heat,
        "policy_bonus": policy_bonus,
        "policy_coefficient": policy_coefficient,
        "policy_adjusted_heat": policy_adjusted_heat,
    }


def evidence_groups(theme: dict[str, Any], accepted_refs: set[str]) -> list[dict[str, Any]]:
    """Return distinct accepted evidence rows (title-deduplicated by prepare)."""

    return [
        item
        for item in theme.get("evidence", [])
        if isinstance(item, dict)
        and accepted_refs.intersection(
            ref for ref in item.get("refs", []) if isinstance(ref, str)
        )
    ]


def matched_concepts_for(
    theme: dict[str, Any], accepted_refs: set[str]
) -> list[str]:
    concepts: set[str] = set()
    for item in evidence_groups(theme, accepted_refs):
        for match in item.get("matches", []):
            if (
                isinstance(match, dict)
                and match.get("kind") == "concept"
                and isinstance(match.get("term"), str)
                and match["term"].strip()
            ):
                concepts.add(match["term"].strip())
    return sorted(concepts)


def annotation_catalyst(annotation: dict[str, Any]) -> dict[str, str] | None:
    catalyst = annotation.get("catalyst")
    if not isinstance(catalyst, dict):
        return None
    return {
        "type": str(catalyst.get("type") or ""),
        "evidence_ref": str(catalyst.get("evidence_ref") or ""),
    }


def finalize_themes(
    evidence_doc: dict[str, Any], annotations_doc: dict[str, Any]
) -> dict[str, Any]:
    """Build the sole formal Theme contract from validated intermediate docs."""

    evidence_by_name = {
        item["name"]: item
        for item in evidence_doc["themes"]
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    annotations = [
        item for item in annotations_doc["themes"] if isinstance(item, dict)
    ]

    scored: list[dict[str, Any]] = []
    for annotation in annotations:
        name = annotation["name"]
        evidence_theme = evidence_by_name[name]
        accepted_refs = set(annotation["accepted_refs"])
        groups = evidence_groups(evidence_theme, accepted_refs)
        parts = score_components(
            annotation["market_action"],
            annotation["emotion_raw"],
            annotation["attention_direction"],
            len(groups),
            annotation["capital"],
            annotation["policy_tier"],
            annotation["policy_polarity"],
        )
        catalyst = annotation_catalyst(annotation)
        scored.append(
            {
                "name": name,
                "confidence": annotation["confidence"],
                "attention_direction": annotation["attention_direction"],
                "market_action": annotation["market_action"],
                "emotion_raw": annotation["emotion_raw"],
                "capital": annotation["capital"],
                "policy_tier": annotation["policy_tier"],
                "policy_polarity": annotation["policy_polarity"],
                "policy_ref": annotation["policy_ref"],
                "catalyst": catalyst,
                "accepted_refs": sorted(accepted_refs, key=news_ref_sort_key),
                "matched_concepts": matched_concepts_for(
                    evidence_theme, accepted_refs
                ),
                "reason": annotation["reason"],
                **parts,
            }
        )

    catalyst_candidates = [
        item
        for item in scored
        if item["catalyst"] is not None
        and item["attention_direction"] in {"bullish", "neutral"}
    ]
    catalyst_candidates.sort(
        key=lambda item: (
            -item["policy_adjusted_heat"],
            -item["confidence"],
            item["name"],
        )
    )
    promoted_names = {item["name"] for item in catalyst_candidates[:2]}

    for item in scored:
        item["final_heat"] = round_score(
            max(
                item["policy_adjusted_heat"],
                57 if item["name"] in promoted_names else 0,
            )
        )

    scored.sort(
        key=lambda item: (-item["final_heat"], -item["confidence"], item["name"])
    )
    tradeable_names = {
        item["name"]
        for item in [
            row
            for row in scored
            if row["confidence"] >= 60 and row["final_heat"] >= 55
        ][:20]
    }

    output: list[dict[str, Any]] = []
    for rank, item in enumerate(scored, start=1):
        if item["confidence"] < 60:
            status = "discarded"
        elif item["name"] in tradeable_names:
            status = "tradeable"
        elif (
            40 <= item["final_heat"] < 55
            and (
                item["attention_direction"] == "bullish"
                or item["market_action"] >= 50
            )
        ):
            status = "watch"
        else:
            status = "discarded"
        catalyst = (
            item["catalyst"] if item["name"] in promoted_names else None
        )
        output.append(
            {
                "rank": rank,
                "name": item["name"],
                "status": status,
                "confidence": item["confidence"],
                "attention_direction": item["attention_direction"],
                "score": {
                    "market_action": item["market_action"],
                    "emotion_raw": item["emotion_raw"],
                    "emotion_coefficient": item["emotion_coefficient"],
                    "news_density": item["news_density"],
                    "capital": item["capital"],
                    "base_heat": item["base_heat"],
                    "policy": {
                        "tier": item["policy_tier"],
                        "polarity": item["policy_polarity"],
                        "bonus": item["policy_bonus"],
                        "coefficient": item["policy_coefficient"],
                        "evidence_ref": item["policy_ref"],
                    },
                    "final_heat": item["final_heat"],
                },
                "catalyst": catalyst,
                "matched_concepts": item["matched_concepts"],
                "evidence_refs": item["accepted_refs"],
                "reason": item["reason"],
            }
        )
    return {
        "schema_version": THEMES_SCHEMA,
        "date": evidence_doc["date"],
        "themes": output,
    }


def news_ref_sort_key(value: str) -> tuple[int, str]:
    match = NEWS_REF_RE.fullmatch(value)
    return (int(match.group(1)), value) if match else (2**31, value)


def numbers_match(left: Any, right: Any) -> bool:
    return (
        is_number(left)
        and is_number(right)
        and abs(float(left) - float(right)) <= NUMERIC_TOLERANCE
    )


def formal_theme_shape_errors(item: Any, path: str) -> list[str]:
    if not isinstance(item, dict):
        return [f"{path}: must be object"]
    errors: list[str] = []
    missing = sorted(FORMAL_THEME_FIELDS - set(item))
    unexpected = sorted(set(item) - FORMAL_THEME_FIELDS)
    if missing:
        errors.append(f"{path}: missing fields {missing}")
    if unexpected:
        errors.append(f"{path}: unexpected fields {unexpected}")
    rank = item.get("rank")
    if not isinstance(rank, int) or isinstance(rank, bool) or rank < 1:
        errors.append(f"{path}.rank: must be positive integer")
    if not isinstance(item.get("name"), str) or not item["name"].strip():
        errors.append(f"{path}.name: required")
    if item.get("status") not in {"tradeable", "watch", "discarded"}:
        errors.append(f"{path}.status: invalid enum")
    confidence = item.get("confidence")
    if not is_number(confidence) or not 0 <= confidence <= 100:
        errors.append(f"{path}.confidence: must be number in [0, 100]")
    if item.get("attention_direction") not in ATTENTION_DIRECTIONS:
        errors.append(f"{path}.attention_direction: invalid enum")
    score = item.get("score")
    if not isinstance(score, dict):
        errors.append(f"{path}.score: must be object")
    else:
        score_missing = sorted(FORMAL_SCORE_FIELDS - set(score))
        score_unexpected = sorted(set(score) - FORMAL_SCORE_FIELDS)
        if score_missing:
            errors.append(f"{path}.score: missing fields {score_missing}")
        if score_unexpected:
            errors.append(f"{path}.score: unexpected fields {score_unexpected}")
        final_heat = score.get("final_heat")
        if not is_number(final_heat) or not 0 <= final_heat <= 100:
            errors.append(
                f"{path}.score.final_heat: must be number in [0, 100]"
            )
        policy = score.get("policy")
        if not isinstance(policy, dict):
            errors.append(f"{path}.score.policy: must be object")
        else:
            policy_missing = sorted(FORMAL_POLICY_FIELDS - set(policy))
            policy_unexpected = sorted(set(policy) - FORMAL_POLICY_FIELDS)
            if policy_missing:
                errors.append(
                    f"{path}.score.policy: missing fields {policy_missing}"
                )
            if policy_unexpected:
                errors.append(
                    f"{path}.score.policy: unexpected fields {policy_unexpected}"
                )
    refs = item.get("evidence_refs")
    if not isinstance(refs, list) or not all(
        isinstance(ref, str) and NEWS_REF_RE.fullmatch(ref) for ref in refs
    ):
        errors.append(f"{path}.evidence_refs: must be canonical news ref list")
    concepts = item.get("matched_concepts")
    if not isinstance(concepts, list) or not all(
        isinstance(value, str) for value in concepts
    ):
        errors.append(f"{path}.matched_concepts: must be string list")
    if not isinstance(item.get("reason"), str):
        errors.append(f"{path}.reason: must be string")
    return errors
