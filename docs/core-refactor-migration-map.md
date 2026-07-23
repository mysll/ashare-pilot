# Python 核心工程迁移映射

- 状态：Completed（历史迁移映射）
- 日期：2026-07-21
- 关联：[ADR-0002](adr/0002-agent-neutral-core-library.md)
- 目标：为每个旧运行入口指定唯一的新功能归属和 CLI

## 规则

- 新模块均位于 `src/ashare_pilot/`。
- 表中的 CLI 均省略前缀 `ashare-pilot`。
- 旧入口在第一阶段保持原样，并已在第二阶段切换后删除；表格保留用于追溯。
- 叶子命令继承旧入口的参数语义。确切参数映射由对应等价测试锁定。
- 非入口模块不会为了保持旧文件名而暴露 CLI。

## Market Data 与 Indicators

| 旧入口 | 新归属 | 新 CLI |
|--------|--------|--------|
| `.opencode/lib/fetch/fetch_stock.py` | `market_data` | `market-data quote` |
| `.opencode/lib/fetch/fetch_history.py` | `market_data` | `market-data history` |
| `.opencode/lib/fetch/fetch_all_astocks.py` | `market_data` | `market-data stocks all` |
| `.opencode/lib/fetch/fetch_market_breadth.py` | `market_data` | `market-data breadth` |
| `.opencode/lib/fetch/fetch_money_flow.py` | `market_data` | `market-data money-flow` |
| `.opencode/lib/fetch/fetch_board_money_flow.py` | `market_data` | `market-data money-flow board` |
| `.opencode/lib/fetch/fetch_special.py` | `market_data` | `market-data special` |
| `.opencode/lib/fetch/fetch_concept_ranking.py` | `market_data` | `market-data ranking concepts` |
| `.opencode/lib/fetch/fetch_turnover_ranking.py` | `market_data` | `market-data ranking turnover` |
| `.opencode/lib/fetch/fetch_limit_up_pool.py` | `market_data` | `market-data pool limit-up` |
| `.opencode/lib/fetch/fetch_indicators.py` | `indicators` | `indicators calculate` |
| `.opencode/skills/daily-stock-mapping/scripts/fetch_pool_indicators.py` | `indicators` | `indicators pool fetch` |
| `.opencode/skills/intraday-stock-discovery/scripts/enrich_technicals.py` | `indicators` | `indicators pool enrich` |
| `.opencode/scripts/get_cookie.py` | `market_data` | `market-data auth update-cookie` |

以下旧模块迁入 `market_data` 内部实现，不单独暴露 CLI：

- `.opencode/lib/datasources/{base,eastmoney,intraday,kline_cache,sina,sohu,tencent,utils}.py`
- `.opencode/lib/trading_calendar.py`

## News 与 Themes

| 旧入口 | 新归属 | 新 CLI |
|--------|--------|--------|
| `.opencode/skills/daily-news-brief/scripts/fetch_news.py` | `news` | `news fetch` |
| `.opencode/skills/theme-library/scripts/fetch_concepts.py` | `themes` | `themes concepts fetch` |
| `.opencode/skills/theme-library/scripts/fetch_concept_stocks.py` | `themes` | `themes concepts fetch-stocks` |
| `.opencode/skills/theme-library/scripts/build_library.py` | `themes` | `themes library build` |
| `.opencode/skills/theme-library/scripts/query_theme.py` | `themes` | `themes query` |
| `.opencode/skills/intraday-market-scan/scripts/build_concept_dashboard.py` | `themes` | `themes dashboard build` |
| `.opencode/skills/intraday-stock-discovery/scripts/compute_theme_ranking.py` | `themes` | `themes ranking compute` |

`.opencode/skills/theme-library/scripts/datasource.py` 迁入 `themes` 内部实现，不单独
暴露 CLI。

## Mapping

### Daily mapping

| 旧入口 | 新 CLI |
|--------|--------|
| `build_theme_evidence_input.py` | `mapping daily build-theme-evidence` |
| `build_theme_stocks_universe.py` | `mapping daily build-theme-stock-universe` |
| `build_theme_stocks_base.py` | `mapping daily build-theme-stock-base` |
| `build_theme_stocks_json.py` | `mapping daily build-theme-stocks` |
| `validate_themes_json.py` | `mapping daily validate-themes` |
| `validate_theme_stocks_json.py` | `mapping daily validate-theme-stocks` |
| `build_mapper_base.py` | `mapping daily build-mapper-base` |
| `validate_mapper_annotations.py` | `mapping daily validate-annotations` |
| `build_mapper_json.py` | `mapping daily build-mapper` |
| `validate_mapper_json.py` | `mapping daily validate-mapper` |
| `build_strategy_view.py` | `mapping daily build-strategy-view` |
| `build_step2_timing.py` | `mapping daily build-timing` |
| `prepare_daily_mapping.py` | `mapping daily prepare` |
| `finalize_daily_mapping.py` | `mapping daily finalize` |
| `compare_step2_regression.py` | `mapping daily compare-regression` |

以上文件切换前位于 `.opencode/skills/daily-stock-mapping/scripts/`。
`mapper_json_lib.py` 迁入 `mapping` 内部实现，不单独暴露 CLI。

### Intraday mapping

| 旧入口 | 新 CLI |
|--------|--------|
| `.opencode/skills/intraday-market-scan/scripts/build_scan_pool.py` | `mapping intraday build-scan-pool` |
| `.opencode/skills/intraday-stock-discovery/scripts/enrich_compute_pool.py` | `mapping intraday enrich-compute-pool` |
| `.opencode/skills/intraday-strategy/scripts/build_intraday_mapper_base.py` | `mapping intraday build-mapper-base` |
| `.opencode/skills/intraday-strategy/scripts/validate_intraday_mapper_annotations.py` | `mapping intraday validate-annotations` |
| `.opencode/skills/intraday-strategy/scripts/build_intraday_mapper_json.py` | `mapping intraday build-mapper` |
| `.opencode/skills/intraday-strategy/scripts/validate_intraday_mapper_json.py` | `mapping intraday validate-mapper` |

`intraday_mapper_json_lib.py` 迁入 `mapping` 内部实现，不单独暴露 CLI。

## Strategy

### Daily strategy

| 旧入口 | 新 CLI |
|--------|--------|
| `build_strategy_llm_input.py` | `strategy daily build-llm-input` |
| `compute_trade_profile.py` | `strategy daily compute-trade-profile` |
| `normalize_strategy_selection.py` | `strategy daily normalize-selection` |
| `validate_strategy_draft.py` | `strategy daily validate-draft` |
| `validate_strategy_json.py` | `strategy daily validate` |
| `build_step3_timing.py` | `strategy daily build-timing` |
| `prepare_daily_strategy.py` | `strategy daily prepare` |
| `finalize_daily_strategy.py` | `strategy daily finalize` |
| `render_daily_report_html.py` | `strategy daily render-report` |
| `compare_strategy_shadow.py` | `strategy daily compare-shadow` |

以上文件切换前位于 `.opencode/skills/daily-strategy/scripts/`。

### Overnight strategy

| 旧入口 | 新 CLI |
|--------|--------|
| `score_overnight.py` | `strategy overnight score` |
| `build_overnight_strategy_json.py` | `strategy overnight build` |
| `validate_overnight_strategy_json.py` | `strategy overnight validate` |
| `render_overnight_strategy_html.py` | `strategy overnight render-report` |

以上文件切换前位于 `.opencode/skills/intraday-strategy/scripts/`。Mapper 相关入口
归入前述 `mapping intraday`，不因原目录名而归入 strategy。

## Operations

| 旧入口 | 新 CLI |
|--------|--------|
| `build_operation_snapshot.py` | `operations snapshot build` |
| `validate_operation_snapshot.py` | `operations snapshot validate` |
| `build_operation_decision.py` | `operations decision build` |
| `validate_operation_decision.py` | `operations decision validate` |
| `render_operation_guide_html.py` | `operations guide render` |
| `run_operation_guide.py` | `operations guide run` |

以上文件切换前位于 `.opencode/skills/intraday-operation-guide/scripts/`。
`market_confirmation.py`、`mechanical_classification.py`、`operation_time.py`、
`operation_transition.py`、`portfolio_allocation.py` 和 `theme_confirmation.py`
迁入 `operations` 内部实现，不单独暴露 CLI。

## Review

| 旧入口 | 新 CLI |
|--------|--------|
| `.opencode/skills/daily-trading-review/scripts/generate_verification_json.py` | `review daily verify` |
| `.opencode/skills/daily-trading-review/scripts/entry_band_shadow_backtest.py` | `review daily backtest-entry-band` |
| `.opencode/skills/daily-trading-review/scripts/entry_quality_backtest.py` | `review daily backtest-entry-quality` |

## Automation

| 旧入口 | 新 CLI |
|--------|--------|
| `.opencode/scripts/check_rule_governance.py` | `automation rules check` |
| `.opencode/scripts/cron-daemon.py` | `automation scheduler run` |
| `.opencode/scripts/run_intraday_pipeline.py` | `automation intraday run` |

## 第二阶段检查

切换时应使用文件清单和命令清单做双向核对：

- 每个旧运行入口必须有且仅有一个新 CLI。
- 每个新 CLI 必须有离线等价测试。
- 每个非入口模块必须有明确的新功能归属。
- 不允许 `.opencode` 中残留生产 Python 实现或由 Skill 调用旧路径。
