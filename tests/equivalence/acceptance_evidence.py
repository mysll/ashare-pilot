"""Machine-checkable evidence registry for the 68 migrated entry points."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EntryEvidence:
    normal: tuple[str, ...]
    boundary: tuple[str, ...]
    failure: tuple[str, ...]
    cli: tuple[str, ...]
    api: tuple[str, ...]


CLI_FAILURE = (
    "tests/cli/test_migrated_cli_contracts.py::test_leaf_unknown_argument_preserves_failure_boundary",
)
CLI_CONTRACT = (
    "tests/cli/test_migrated_cli_contracts.py::test_leaf_help_preserves_option_contract",
)
API_CONTRACT = (
    "tests/unit/test_public_api_contracts.py::test_capability_exports_a_deliberate_callable_public_api",
)


def evidence(normal: str, boundary: str) -> EntryEvidence:
    return EntryEvidence((normal,), (boundary,), CLI_FAILURE, CLI_CONTRACT, API_CONTRACT)


ENTRY_EVIDENCE: dict[str, EntryEvidence] = {}


def assign(ids: str, normal: str, boundary: str) -> None:
    for entry_id in ids.split():
        if entry_id in ENTRY_EVIDENCE:
            raise AssertionError(f"duplicate acceptance evidence: {entry_id}")
        ENTRY_EVIDENCE[entry_id] = evidence(normal, boundary)


assign(
    "MD01 MD02 MD03 MD05 MD07",
    "tests/equivalence/test_batch2_market_data.py::test_function_backed_cli_output_is_equivalent",
    "tests/equivalence/test_batch2_market_data.py::test_function_backed_empty_boundary_is_equivalent",
)
assign(
    "MD04 MD06 MD08 MD09 MD10",
    "tests/equivalence/test_batch2_market_data.py::test_datasource_backed_cli_output_is_equivalent",
    "tests/equivalence/test_batch2_market_data.py::test_datasource_backed_empty_boundary_is_equivalent",
)
assign(
    "MD11",
    "tests/equivalence/test_batch2_market_data.py::test_cookie_serialization_is_equivalent",
    "tests/equivalence/test_batch2_market_data.py::test_cookie_serialization_is_equivalent",
)
assign(
    "IN01 IN02 IN03",
    "tests/equivalence/test_batch3_indicators.py::test_all_indicator_formulas_match_legacy",
    "tests/unit/test_batch2_market_data.py::test_default_kline_cache_is_scoped_to_explicit_workspace",
)
assign(
    "NW01",
    "tests/equivalence/test_batch2_news.py::test_normalization_document_and_markdown_are_equivalent",
    "tests/equivalence/test_batch2_news.py::test_failed_source_is_empty_and_public_api_is_silent",
)
assign(
    "TH01 TH02 TH03 TH04 TH05 TH06",
    "tests/equivalence/test_batch3_themes.py::test_copied_theme_queries_match_legacy_library",
    "tests/unit/test_batch3_workspace_paths.py::test_theme_query_switches_between_explicit_workspaces",
)
assign(
    "MP01 MP02 MP03 MP04 MP05 MP06 MP07 MP08 MP09 MP10 MP11 MP12 MP13 MP14 MP15",
    "tests/equivalence/test_batch4_mapping.py::test_daily_mapper_contract_and_candidate_order_match_legacy",
    "tests/equivalence/test_batch4_mapping.py::test_daily_validation_error_order_and_text_match_legacy",
)
assign(
    "MP16 MP17 MP18 MP19 MP20 MP21",
    "tests/equivalence/test_batch4_mapping.py::test_intraday_merge_and_validation_match_legacy",
    "tests/unit/test_intraday_mapper_v3.py::test_execution_state_tampering_is_recomputed_and_rejected",
)
assign(
    "ST01 ST02 ST03 ST04 ST05 ST06 ST07 ST08 ST09 ST10",
    "tests/equivalence/test_batch5_strategy.py::test_daily_compact_uses_qualitative_position_tiers",
    "tests/unit/test_batch5_daily_contract.py::test_incomplete_selected_stock_fails_before_materialize",
)
assign(
    "ST11 ST12 ST13 ST14",
    "tests/equivalence/test_batch5_strategy.py::test_overnight_contract_and_html_match_legacy",
    "tests/unit/test_overnight_strategy_v3.py::test_actionable_executable_and_observation_project_to_exact_views",
)
assign(
    "OP01 OP02 OP03 OP04 OP05 OP06",
    "tests/equivalence/test_batch6_operations_review.py::test_operation_runner_offline_commit_is_complete_and_idempotent",
    "tests/equivalence/test_batch6_operations_review.py::test_state_transition_and_immutable_publish_match_legacy",
)
assign(
    "RV01 RV02 RV03",
    "tests/equivalence/test_batch6_operations_review.py::test_verification_contract_matches_legacy_with_frozen_market_data",
    "tests/equivalence/test_batch6_operations_review.py::test_entry_band_and_quality_statistics_match_legacy",
)
assign(
    "AU01 AU02 AU03",
    "tests/equivalence/test_batch7_automation.py::test_root_scheduler_config_and_schedule_match_legacy",
    "tests/equivalence/test_batch7_automation.py::test_rule_governance_matches_legacy_and_detects_contract_failures",
)
