from __future__ import annotations

import importlib

import pytest


PUBLIC_CONTRACTS = {
    "market_data": {
        "fetch_quotes", "fetch_history", "fetch_all_stocks", "fetch_market_breadth",
        "fetch_money_flow", "fetch_board_money_flow", "fetch_special_lhb",
        "fetch_margin_balance", "fetch_concept_ranking", "fetch_turnover_ranking",
        "fetch_limit_up_pool",
    },
    "news": {"fetch_daily_news", "write_news_outputs"},
    "indicators": {"calculate_indicators", "fetch_indicators"},
    "themes": {
        "fetch_concepts", "fetch_concept_stocks", "query_theme",
        "build_concept_dashboard", "compute_theme_ranking",
    },
    "mapping": {
        "build_daily_mapper", "merge_daily_mapper",
        "merge_intraday_mapper", "build_scan_pool", "validate_daily_mapper",
        "validate_intraday_annotations",
    },
    "strategy": {
        "build_daily_llm_input", "compute_trade_profile", "finalize_daily_strategy",
        "build_overnight_strategy", "compute_scores", "validate_overnight_strategy",
    },
    "operations": {
        "build_operation_decision", "build_stock_snapshot",
        "validate_operation_decision", "render_operation_guide",
    },
    "review": {
        "build_intraday_shadow_contract", "build_verification", "load_rows",
        "summarize", "parse_file", "metrics", "validate_intraday_shadow_contract",
    },
    "automation": {"check_rule_governance", "initialize_memory", "load_scheduler_config", "run_intraday_pipeline"},
}


@pytest.mark.parametrize(("capability", "required"), PUBLIC_CONTRACTS.items())
def test_capability_exports_a_deliberate_callable_public_api(
    capability: str, required: set[str]
) -> None:
    module = importlib.import_module(f"ashare_pilot.{capability}")
    exported = set(module.__all__)

    assert required <= exported
    assert all(not name.startswith("_") for name in exported)
    for name in required:
        assert callable(getattr(module, name))
