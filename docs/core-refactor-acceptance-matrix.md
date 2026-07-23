# Python 核心工程最终验收矩阵

- 状态：Completed
- 日期：2026-07-22
- 关联：[ADR-0002](adr/0002-agent-neutral-core-library.md)
- 入口来源：[迁移映射](core-refactor-migration-map.md)

## 用途

本矩阵是第一阶段最终验收和第二阶段切换的历史入口清单。每个旧运行入口必须
恰好对应一个新 CLI，并完成以下五类离线证据：

- `N`：正常输入及规范化产物等价；
- `B`：边界或缺失输入等价；
- `F`：预期失败、错误文本和退出码等价；
- `C`：通过统一 `ashare-pilot` CLI 验证参数、stdout 和 stderr；
- `A`：入口所属一级能力具有明确、可调用且经过测试的公开 Python API；编排型
  CLI 不要求机械暴露一个与命令同名的包装函数。

状态含义：`OPEN` 表示至少一类证据缺失；`PASS` 表示 `N/B/F/C/A` 全部有自动化
证据。`--help` 可达性只证明命令已注册，不计为 `C` 完成。

## Market Data 与 Indicators

| ID | 旧入口 | 新 CLI | 公共 API | N | B | F | C | A | 状态 |
|----|--------|--------|----------|---|---|---|---|---|------|
| MD01 | `fetch_stock.py` | `market-data quote` | `fetch_quotes` / `fetch_intraday_kline` / `search_stocks` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| MD02 | `fetch_history.py` | `market-data history` | `fetch_history` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| MD03 | `fetch_all_astocks.py` | `market-data stocks all` | `fetch_all_stocks` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| MD04 | `fetch_market_breadth.py` | `market-data breadth` | `fetch_market_breadth` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| MD05 | `fetch_money_flow.py` | `market-data money-flow` | `fetch_money_flow` / `fetch_stock_money_flow` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| MD06 | `fetch_board_money_flow.py` | `market-data money-flow board` | `fetch_board_money_flow` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| MD07 | `fetch_special.py` | `market-data special` | `fetch_special_lhb` / `fetch_margin_balance` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| MD08 | `fetch_concept_ranking.py` | `market-data ranking concepts` | `fetch_concept_ranking` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| MD09 | `fetch_turnover_ranking.py` | `market-data ranking turnover` | `fetch_turnover_ranking` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| MD10 | `fetch_limit_up_pool.py` | `market-data pool limit-up` | `fetch_limit_up_pool` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| MD11 | `get_cookie.py` | `market-data auth update-cookie` | `market_data` 公共认证/数据访问边界 | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| IN01 | `fetch_indicators.py` | `indicators calculate` | `fetch_indicators` / `calculate_indicators` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| IN02 | `fetch_pool_indicators.py` | `indicators pool fetch` | 复用 `fetch_indicators` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| IN03 | `enrich_technicals.py` | `indicators pool enrich` | `calculate_indicators` / `fetch_indicators` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |

## News 与 Themes

| ID | 旧入口 | 新 CLI | 公共 API | N | B | F | C | A | 状态 |
|----|--------|--------|----------|---|---|---|---|---|------|
| NW01 | `fetch_news.py` | `news fetch` | `fetch_daily_news` / `write_news_outputs` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| TH01 | `fetch_concepts.py` | `themes concepts fetch` | `fetch_concepts` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| TH02 | `fetch_concept_stocks.py` | `themes concepts fetch-stocks` | `fetch_concept_stocks` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| TH03 | `build_library.py` | `themes library build` | `themes` 构建与查询公共能力 | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| TH04 | `query_theme.py` | `themes query` | `query_theme` 等查询 API | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| TH05 | `build_concept_dashboard.py` | `themes dashboard build` | `build_concept_dashboard` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| TH06 | `compute_theme_ranking.py` | `themes ranking compute` | `compute_theme_ranking` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |

## Mapping

| ID | 旧入口 | 新 CLI | 公共 API | N | B | F | C | A | 状态 |
|----|--------|--------|----------|---|---|---|---|---|------|
| MP01 | `build_theme_evidence_input.py` | `mapping daily build-theme-evidence` | `build_theme_evidence` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| MP02 | `build_theme_stocks_universe.py` | `mapping daily build-theme-stock-universe` | `mapping` 主题池公共能力 | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| MP03 | `build_theme_stocks_base.py` | `mapping daily build-theme-stock-base` | `build_daily_mapper` / `publish_theme_stocks` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| MP04 | `build_theme_stocks_json.py` | `mapping daily build-theme-stocks` | `publish_theme_stocks` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| MP05 | `validate_themes_json.py` | `mapping daily validate-themes` | `validate_themes` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| MP06 | `validate_theme_stocks_json.py` | `mapping daily validate-theme-stocks` | `validate_theme_stocks` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| MP07 | `build_mapper_base.py` | `mapping daily build-mapper-base` | `build_daily_mapper` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| MP08 | `validate_mapper_annotations.py` | `mapping daily validate-annotations` | `validate_daily_annotations` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| MP09 | `build_mapper_json.py` | `mapping daily build-mapper` | `merge_daily_mapper` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| MP10 | `validate_mapper_json.py` | `mapping daily validate-mapper` | `validate_daily_mapper` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| MP11 | `build_strategy_view.py` | `mapping daily build-strategy-view` | `build_strategy_view` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| MP12 | `build_step2_timing.py` | `mapping daily build-timing` | `mapping` 合同公共能力 | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| MP13 | `prepare_daily_mapping.py` | `mapping daily prepare` | `build_theme_evidence` / `build_daily_mapper` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| MP14 | `finalize_daily_mapping.py` | `mapping daily finalize` | `merge_daily_mapper` / validators | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| MP15 | `compare_step2_regression.py` | `mapping daily compare-regression` | `mapping` 合同公共能力 | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| MP16 | `build_scan_pool.py` | `mapping intraday build-scan-pool` | `build_scan_pool` / `compute_quick_score` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| MP17 | `enrich_compute_pool.py` | `mapping intraday enrich-compute-pool` | `mapping` 盘中候选池公共能力 | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| MP18 | `build_intraday_mapper_base.py` | `mapping intraday build-mapper-base` | `merge_intraday_mapper` 前置合同能力 | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| MP19 | `validate_intraday_mapper_annotations.py` | `mapping intraday validate-annotations` | `validate_intraday_annotations` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| MP20 | `build_intraday_mapper_json.py` | `mapping intraday build-mapper` | `merge_intraday_mapper` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| MP21 | `validate_intraday_mapper_json.py` | `mapping intraday validate-mapper` | `reasoning_invariant_errors` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |

## Strategy

| ID | 旧入口 | 新 CLI | 公共 API | N | B | F | C | A | 状态 |
|----|--------|--------|----------|---|---|---|---|---|------|
| ST01 | `build_strategy_llm_input.py` | `strategy daily build-llm-input` | `build_daily_llm_input` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| ST02 | `compute_trade_profile.py` | `strategy daily compute-trade-profile` | `compute_trade_profile` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| ST03 | `normalize_strategy_selection.py` | `strategy daily normalize-selection` | `normalize_selection` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| ST04 | `validate_strategy_draft.py` | `strategy daily validate-draft` | `validate_draft` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| ST05 | `validate_strategy_json.py` | `strategy daily validate` | `validate_daily_strategy` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| ST06 | `build_step3_timing.py` | `strategy daily build-timing` | `strategy` 合同公共能力 | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| ST07 | `prepare_daily_strategy.py` | `strategy daily prepare` | `build_daily_llm_input` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| ST08 | `finalize_daily_strategy.py` | `strategy daily finalize` | `finalize_daily_strategy`（核心合同） | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| ST09 | `render_daily_report_html.py` | `strategy daily render-report` | `render_daily_report` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| ST10 | `compare_strategy_shadow.py` | `strategy daily compare-shadow` | `strategy` 合同公共能力 | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| ST11 | `score_overnight.py` | `strategy overnight score` | `compute_scores` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| ST12 | `build_overnight_strategy_json.py` | `strategy overnight build` | `build_overnight_strategy` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| ST13 | `validate_overnight_strategy_json.py` | `strategy overnight validate` | `validate_overnight_strategy` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| ST14 | `render_overnight_strategy_html.py` | `strategy overnight render-report` | `render_overnight_report` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |

## Operations、Review 与 Automation

| ID | 旧入口 | 新 CLI | 公共 API | N | B | F | C | A | 状态 |
|----|--------|--------|----------|---|---|---|---|---|------|
| OP01 | `build_operation_snapshot.py` | `operations snapshot build` | `build_stock_snapshot` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| OP02 | `validate_operation_snapshot.py` | `operations snapshot validate` | `validate_operation_snapshot` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| OP03 | `build_operation_decision.py` | `operations decision build` | `build_operation_decision` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| OP04 | `validate_operation_decision.py` | `operations decision validate` | `validate_operation_decision` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| OP05 | `render_operation_guide_html.py` | `operations guide render` | `render_operation_guide` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| OP06 | `run_operation_guide.py` | `operations guide run` | `operations` 决策与渲染公共能力 | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| RV01 | `generate_verification_json.py` | `review daily verify` | `build_verification` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| RV02 | `entry_band_shadow_backtest.py` | `review daily backtest-entry-band` | `load_rows` / `summarize` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| RV03 | `entry_quality_backtest.py` | `review daily backtest-entry-quality` | `parse_file` / `metrics` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| AU01 | `check_rule_governance.py` | `automation rules check` | `check_rule_governance` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| AU02 | `cron-daemon.py` | `automation scheduler run` | `load_scheduler_config` / `scheduler` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |
| AU03 | `run_intraday_pipeline.py` | `automation intraday run` | `run_intraday_pipeline` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS |

## 汇总

- 旧运行入口：68。
- 唯一新 CLI：68。
- 当前 `PASS`：68。
- 当前 `OPEN`：0。

逐入口证据由 `tests/equivalence/acceptance_evidence.py` 集中注册。自动化测试验证
入口数量、唯一性、五类证据完整性、测试节点存在性和所有 `PASS` 状态，防止文档
与实现再次分离。

第二阶段已于 2026-07-22 完成。旧实现及其重复测试已删除；运行时 Skill、批处理
和文档命令均改用统一 CLI。依赖旧实现的动态等价测试在旧基线删除后明确跳过，
矩阵记录的 PASS 是切换前已完成并锁定的验收证据。

## 已修复的旧链路缺陷

以下缺陷已于 2026-07-22 获得双轨修复授权，并由逐入口 CLI 合同测试锁定。相关
入口仍需完成矩阵中的其他证据后才能转为 `PASS`。

| 入口 | 原缺陷 | 双轨修复 | 回归证据 |
|------|--------|----------|----------|
| ST02 | `compute_trade_profile.py --help` 因帮助文本中的 `%` 未转义而以 `ValueError` 退出 | 旧、新帮助文本均正确转义 `%` | `test_leaf_help_preserves_option_contract` | ✓ | ✓ | ✓ | ✓ | ✓ | PASS || ✓ | ✓ | AU01 | `check_rule_governance.py` 不解析参数，任意未知参数被静默忽略 | 旧、新入口均使用 argparse，未知参数返回退出码 2 | `test_leaf_unknown_argument_preserves_failure_boundary` |
|| ✓ | ✓ 
