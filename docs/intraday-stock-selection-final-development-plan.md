# Intraday 双池选股最终开发计划

- 版本：1.0
- 日期：2026-07-27
- 状态：Implemented
- 权威决策：[ADR-0004](adr/0004-intraday-selection-pools-contract.md)
- 领域语言：[Intraday 选股领域术语表](intraday-stock-selection-glossary.md)
- 现状基线：[当前 Intraday 选股、评分与过滤流程](current-intraday-stock-selection.md)
- 评审来源：[系统评审与改造建议](current-intraday-stock-selection-review.md)、[改进提案](intraday-stock-selection-improvement-proposal.md)

## 1. 目标

将当前混合“可执行候选”和“观察候选”的 Opportunity Pool 重构为确定性的双池合同：

```text
executable_pool
  只包含数据可评分且全部执行资格通过的股票

observation_pool
  包含确定性不可执行或个股关键评分数据不完整的观察股票
```

本期完成后必须达到：

1. 封板、板块排除、关键报价缺失、资金或技术资格失败的股票不再占执行池名额；
2. 执行池从 Scored Pool 按原分数顺序持续补位，最多 30 只；
3. A/B/C/D 只表达唯一 Scored Pool 的相对排名，不再决定执行池入选；
4. 缺失资金或技术数据不再通过默认 raw 或中位数替换获得分数；
5. 基础策略政策、代码合同和学习规则在文档及代码所有权上分离；
6. Compute、Mapper、Reasoning 和最终报告使用 v2 双池 Schema；
7. 没有合适股票时正常输出空推荐和零仓位。

## 2. 非目标

本期明确不做：

- 通用 `run_id`、原子发布、缓存哈希或旧缓存隔离；
- 全流水线统一 fail-fast 重构；
- QuickScore 公式、三路召回顺序或 `source_pool` 单标签调整；
- `amount` 加入 QuickScore；
- 统一最低 OvernightScore；
- 九维权重标定；
- Theme Ranking 进入生产评分；
- I10、I14 阈值回测；
- 学习规则新增、升级或退役；
- 收益率、胜率或回撤作为本次上线门槛；
- 旧 Schema、旧字段、旧 CLI 参数兼容。

本期只对 ADR-0004 列出的必需数据和合同增加明确中断条件。

## 3. 目标数据流

```text
全市场快照（必须 complete）
  ├─ 市场宽度
  ├─ Concept Dashboard（可 unavailable）
  └─ Scan Pool
       ├─ 涨停池
       ├─ 成交额榜（可 unavailable）
       └─ 涨幅池
             ↓ 同一 trading-scope 过滤
          Scan Pool >= compute_pool_size
             ↓ QuickScore，公式不变
          Compute Pool Top 120
             ↓ 报价 + VWAP + 资金流
             ↓ 技术指标
             ↓ execution_state
             ↓ Theme Ranking（必须成功）
          Scoreability Gate
             ├─ 数据完整 → Scored Pool
             │              ↓ 九维 V1.3
             │           唯一 rank/rank_tier
             │              ↓ Execution Eligibility
             │              ├─ 通过 → Executable Pool Top 30
             │              └─ 失败 → Scored Observation
             └─ 数据不完整 → Unscored Observation
                                      ↓ 合并、排序、Top 30
                            selection_pools.json
                                      ↓
                         intraday_mapper.base.v2
                                      ↓
                     executable / observation annotations
                                      ↓
                           intraday_mapper.v2
                                      ↓
                 recommendations / eligible_watchlist / observations
                                      ↓
                       overnight_strategy.v2 + HTML
```

## 4. 不变量

以下条件必须由代码和测试强制，不能只写在 Skill 或提示词中：

### 4.1 Executable Pool

每只股票必须同时满足：

```text
score_status == "scored"
execution_state.eligible == true
money_flow.main_net_inflow_yuan >= configured_min_inflow
technicals available
trend_raw >= 0.3
VWAP valid
(
  price >= VWAP
  OR i14_exemption == "cautious_hold"
)
i14_exemption != "watch"
```

执行池：

- 按 `overnight_score DESC, code ASC`；
- 最多 30 只；
- 不按 `rank_tier` 过滤；
- 不使用观察股填充；
- 可以为空。

### 4.2 Observation Pool

观察池由以下集合合并：

- Scored Pool 中未通过执行资格的股票；
- Scoreability Gate 未通过的股票。

观察股必须包含：

```json
{
  "score_status": "scored|unscored",
  "observation_reasons": ["..."],
  "primary_observation_reason": "...",
  "overnight_score": 52.3,
  "rank": 18,
  "rank_tier": "B"
}
```

未评分股票的 `overnight_score`、`rank`、`rank_tier` 必须为 `null` 或不存在，禁止
填 0、50 或其它代理值。

观察池：

- 已评分股票优先；
- 已评分股票按 `overnight_score DESC, code ASC`；
- 未评分股票按 `quick_score DESC, code ASC`；
- 最多 30 只；
- 根级摘要保存截断前原因计数。

### 4.3 Rank

- 只存在一套 `rank/rank_tier/tier`；
- rank 在 Scored Pool 内生成；
- `tier == rank_tier`；
- A/B/C/D 定义保持不变；
- tier 不参与执行池入选；
- tier 不得机械映射为 Tradeability。

### 4.4 LLM 所有权

LLM 不得生成或覆盖：

- 行情、VWAP、资金、技术；
- OvernightScore、score trace、rank、tier；
- floor、Scoreability、Executability；
- execution_state；
- primary_theme、themes、Theme shadow；
- 双池归属；
- 确定性止损价格。

## 5. Canonical Schema

### 5.1 `selection_pools.json`

目标路径：

```text
.cache/intraday/{date}/selection_pools.json
```

根合同：

```json
{
  "schema_version": "intraday_selection_pools.v1",
  "date": "2026-07-27",
  "generated_at": "2026-07-27T06:45:00+00:00",
  "scoring_version": "V1.3_SelectionPools",
  "scoring_policy_version": "selection_pools_v1",
  "configured_limits": {
    "compute_pool_size": 120,
    "executable_pool_size": 30,
    "observation_pool_size": 30,
    "money_flow_min_inflow_yuan": 5000000,
    "trend_raw_floor": 0.3
  },
  "recall_quality": {
    "limit_up": {"status": "complete", "count": 60},
    "turnover": {"status": "unavailable", "count": 0, "error": "rate_limited"},
    "gain_range": {"status": "complete", "count": 214}
  },
  "data_quality": {
    "all_stocks": {},
    "indices": {},
    "money_flow": {},
    "technicals": {},
    "vwap": {},
    "themes": {}
  },
  "regime_snapshot": {},
  "scored_pool_summary": {
    "scoreable_count": 104,
    "unscoreable_count": 16,
    "score_stats": {},
    "rank_tier_counts": {}
  },
  "pool_summary": {
    "executable_count": 18,
    "observation_total_before_limit": 102,
    "observation_count": 30,
    "observation_truncated_count": 72,
    "observation_reason_counts": {},
    "no_executable_candidates": false
  },
  "executable_pool": [],
  "observation_pool": []
}
```

删除：

- `opportunity_pool`;
- `leader_watch`;
- `premium_candidates`;
- `early_breakout`;
- `floor_rejected` 作为独立候选池；
- 空池 degraded fallback。

### 5.2 `intraday_mapper.base.json`

```json
{
  "schema_version": "intraday_mapper_base.v2",
  "date": "2026-07-27",
  "source_files": {
    "selection_pools": ".cache/intraday/2026-07-27/selection_pools.json",
    "theme_ranking": ".cache/intraday/2026-07-27/theme_ranking.json"
  },
  "market": {},
  "themes": {},
  "pool_summary": {},
  "executable_stocks": [],
  "observation_stocks": []
}
```

每只股票由 Python 附加：

- `market_board`;
- `primary_theme`;
- `themes`;
- `theme_support_shadow`;
- 重新计算并核对的 `execution_state`。

### 5.3 `intraday_mapper.annotations.json`

```json
{
  "schema_version": "intraday_mapper_annotations.v2",
  "date": "2026-07-27",
  "market_assessment": {
    "reasoning_trace": "..."
  },
  "executable_annotations": [
    {
      "code": "sh600000",
      "tradeability": "Suitable",
      "direction": "谨慎持有",
      "trading_strategy": "趋势跟随",
      "risk_severity": "medium",
      "expected_premium": "...",
      "key_reason": "...",
      "position_plan": "...",
      "t_plus_1_plan": {
        "auction_condition": "...",
        "open_strategy": "...",
        "stop_loss_basis": "ma5",
        "take_profit": "..."
      },
      "rules_applied": [],
      "reasoning_trace": "..."
    }
  ],
  "observation_annotations": [
    {
      "code": "sz000001",
      "observation_summary": "...",
      "watch_condition": "...",
      "risk_note": "..."
    }
  ],
  "strategy": {
    "position_cap": "..."
  }
}
```

覆盖要求：

- `executable_annotations` 代码集合必须严格等于 base 的
  `executable_stocks`；
- `observation_annotations` 代码集合必须严格等于 base 的
  `observation_stocks`；
- 两个集合不得重叠；
- Observation annotation 出现任何执行字段即验证失败。

### 5.4 `intraday_mapper.json`

```json
{
  "schema_version": "intraday_mapper.v2",
  "date": "2026-07-27",
  "market": {},
  "themes": {},
  "pool_summary": {},
  "executable_stocks": [],
  "observation_stocks": [],
  "market_assessment": {},
  "strategy": {},
  "annotation_coverage": {
    "executable": {"expected": 18, "annotated": 18},
    "observation": {"expected": 30, "annotated": 30}
  }
}
```

`reasoning` 只合并到 executable stock；`observation_reasoning` 只合并到
observation stock。

### 5.5 `overnight_strategy.json`

```json
{
  "schema_version": "intraday_overnight_strategy.v2",
  "date": "2026-07-27",
  "market_assessment": {},
  "strategy": {},
  "data_quality": {},
  "recommendations": [],
  "eligible_watchlist": [],
  "observations": []
}
```

投影规则：

```text
executable + actionable Direction
  → recommendations

executable + 非行动 Direction
  → eligible_watchlist

observation pool
  → observations
```

`recommendations` 中所有股票必须再次通过
`reasoning_invariant_errors()`。`eligible_watchlist` 必须使用
`stop_loss_basis=not_applicable`。`observations` 不得包含 Direction、Tradeability、
仓位或止损。

## 6. 数据质量与中断矩阵

| 数据/阶段 | 成功条件 | 不满足时行为 |
|-----------|----------|--------------|
| 全市场快照 | `status=complete` | 中断 |
| 上证指数 | `sh000001` 存在且价格/涨幅有效 | 中断 |
| 深证成指 | `sz399001` 存在且价格/涨幅有效 | 中断 |
| 辅助指数 | 可用多少保存多少 | 继续，记录 unavailable |
| 涨停池 | 从完整全市场快照确定性生成 | 正常 |
| 成交额榜 | complete 或 unavailable | unavailable 可继续 |
| 涨幅池 | 从完整全市场快照确定性生成 | 正常 |
| Scan Pool | 数量 `>= compute_pool_size` | 中断 |
| Concept Dashboard | complete 或显式 unavailable | unavailable 可继续 |
| 个股资金流 | complete/threshold_reached/partial | 按股票处理 |
| 资金流整体 | 至少一个目标股票有有效资金数据且状态非 unavailable | unavailable 中断 |
| 个股技术 | 有效或 `no_data` | `no_data` 仅观察 |
| 技术整体 | 至少一个股票有效 | 全部无效中断 |
| Theme Ranking | v2 合同构建成功 | 中断 |
| 个股 VWAP | 有效或缺失 | 缺失仅观察 |
| VWAP 整体 | 至少一个股票 `vwap>0` | 全部无效中断 |
| Scored Pool | 至少一只可评分股票 | 为空中断 |
| Executable Pool | 0～30 均合法 | 空池正常输出 |

可选数据失败必须覆盖本轮输出文件为显式 unavailable 合同。本期不实现通用旧缓存
检查，但不得在已知本轮可选命令失败时继续把旧内容解释为本轮成功。

## 7. 评分改造

### 7.1 V1.3 字段

权重：

```python
WEIGHTS_V1_3 = {
    "source_capital_proxy": 0.18,
    "capital_continuity": 0.18,
    "tail_strength": 0.14,
    "position_advantage": 0.09,
    "risk_penalty": 0.10,
    "intensity": 0.09,
    "conviction": 0.09,
    "consistency": 0.05,
    "trend_quality": 0.08,
}
```

`extract_theme_raw()` 重命名为 `extract_source_capital_proxy_raw()`，公式保持：

```text
source_pool base × 0.7
  + sigmoid(main_net_inflow, center=1亿, steepness=1.5) × 0.3
```

删除：

- `WEIGHTS_V1_1`;
- `WEIGHTS_V1_2`;
- `theme_continuity` 新输出；
- V1.1 五维 CLI 描述。

### 7.2 Scoreability Gate

新增纯函数：

```python
assess_scoreability(stock) -> {
    "scoreable": bool,
    "reasons": list[str],
}
```

至少验证：

- 价格、最高价、最低价等评分必需报价存在；
- 股票级资金流 `available=true`；
- main/super-large/large/medium/small 字段是有限数值；
- technicals 存在且不是 `no_data`；
- Trend raw 所需字段存在；
- QuickScore/换手率/量比等输入可解析。

缺失不能进入 I11 median replacement。对矛盾源字段也不得伪造正常值；标记为
unscored observation。

V1.3 新输出不执行 I11 missing median replacement，也不依赖 I11 的替换标记。
历史产物保持原样但不由新合同读取。若未来需要异常修复，必须单独定义带数据来源和
置信区间的政策版本。

### 7.3 Execution Eligibility

新增纯函数：

```python
assess_execution_eligibility(
    stock,
    configured_min_inflow_yuan,
) -> {
    "eligible": bool,
    "reasons": list[str],
}
```

只消费确定性字段，不读 LLM 或学习规则。

资金判断必须使用 `main_net_inflow_yuan`，不得用格式化的“亿”字符串与人民币配置值
直接比较。

### 7.4 Pool Builder

新增纯函数：

```python
build_selection_pools(
    compute_pool,
    *,
    executable_limit=30,
    observation_limit=30,
    configured_min_inflow_yuan,
    regime,
) -> dict
```

处理顺序：

1. 计算 Scoreability；
2. 只对 scoreable 股票执行九维评分；
3. 生成唯一 rank/rank_tier/tier；
4. 对 scored 股票执行 execution eligibility；
5. 形成 executable candidates；
6. 合并 scored/unscored observations；
7. 稳定排序和截断；
8. 生成原因统计与数据质量摘要；
9. 验证池互斥和字段不变量。

## 8. Theme Shadow

在 `mapping.intraday_contract` 增加：

```python
build_theme_support_shadow(
    stock_relations,
    primary_theme_name,
    theme_ranking,
) -> dict
```

完整 shadow 必须来自同一 `theme_ranking.json`：

- `primary_theme`;
- `member_role`;
- `membership_weight`;
- `core_heat`;
- `diffusion_heat`;
- `theme_rank`.

缺失分类：

| 原因 | `available` |
|------|:-----------:|
| 股票无主题关系 | false |
| primary theme 不在 Top 15 动态排名 | false |
| 主题成员关系不完整 | false |
| 动态 heat 字段缺失 | false |
| 完整匹配 | true |

Shadow 不得被复制到 annotations，也不得进入任何评分函数。

## 9. 实施阶段

### Phase 0：冻结合同与测试骨架

涉及：

- `docs/adr/0004-intraday-selection-pools-contract.md`
- `docs/intraday-stock-selection-glossary.md`
- 本文
- `tests/fixtures/`

任务：

- [x] 从现有缓存提取最小、脱敏、版本化的双池冻结 fixture；
- [x] fixture 至少覆盖：封板占位、partial 未覆盖、个股技术缺失、VWAP 缺失、
      I14 watch/cautious_hold、空执行池；
- [x] 为 v1 → v2 行为变化写预期清单，不保存旧 Schema 兼容器；
- [x] 新增 Schema 常量和测试辅助构建器。

完成标准：

- 不访问网络即可重现全部关键分支；
- 每个 fixture 记录来源日期和覆盖场景；
- 测试先以缺少实现而失败。

### Phase 1：统一交易范围与召回质量

涉及：

- 新增 `src/ashare_pilot/market_data/trading_scope.py`
- `src/ashare_pilot/mapping/_commands/intraday/scan_pool.py`
- `src/ashare_pilot/mapping/intraday_contract.py`
- `src/ashare_pilot/market_data/_datasources/intraday.py`
- `tests/unit/test_intraday_board_codes.py`
- 新增 `tests/unit/test_intraday_recall_quality.py`

任务：

- [x] 将 `load_trading_scope()`、`scope_decision()` 移入共享模块；
- [x] Scan 与 execution_state 共同调用共享函数；
- [x] 删除 Scan 简化前缀过滤实现；
- [x] 保持同一 `config/trading-scope.json`；
- [x] 为 limit-up、turnover、gain-range 输出 status/count/error；
- [x] 成交额榜异常不再静默返回正常空列表；
- [x] Scan 输出 `recall_quality`；
- [x] Scan Pool 小于 Compute Pool 目标时返回非零；
- [x] override、最长前缀、未知前缀结果在两阶段完全一致。

完成标准：

- 同一代码在 Scan 和 execution 中得到相同 scope 决策；
- turnover unavailable 时其它两路足够可继续；
- turnover unavailable 且 Scan Pool 不足目标时中断；
- QuickScore 和单标签 source_pool 回归测试不变。

### Phase 2：数据质量合同

涉及：

- `src/ashare_pilot/automation/_commands/intraday.py`
- `src/ashare_pilot/mapping/_commands/intraday/compute_pool.py`
- `src/ashare_pilot/indicators/_commands/pool_enrich.py`
- `src/ashare_pilot/themes/_commands/dashboard.py`
- 相关数据源质量对象
- `tests/unit/test_intraday_all_stocks_retry.py`
- `tests/unit/test_stock_money_flow_pagination.py`
- 新增 `tests/unit/test_intraday_required_data.py`

任务：

- [x] Phase 0 全市场快照非 complete 时立即非零返回；
- [x] 验证 indices 中 `sh000001`、`sz399001` 的存在和有限数值；
- [x] 辅助指数缺失写入 quality，不阻断；
- [x] Concept Dashboard 失败写显式 unavailable JSON；
- [x] money flow unavailable 时 enrich 或 automation 非零返回；
- [x] partial 未覆盖股票设置 `minimum_filter_applied=true`，语义等同低于配置门槛；
- [x] partial 未覆盖股票不进入资金中位数替换；
- [x] technical enrich 增加 complete/partial/unavailable 摘要；
- [x] 技术有效数为 0 时非零返回；
- [x] 个股 no_data 保留，不给默认 Trend raw；
- [x] 统计有效 VWAP 数量；全为 0 时 score 命令非零返回；
- [x] Theme Ranking 命令失败时 automation 停止；
- [x] 必需命令失败时，即使同路径已有文件，也不得继续执行依赖阶段；
- [x] 不实现通用 run_id 或原子发布。

完成标准：

- 中断矩阵每一行有独立测试；
- 可选失败总能产出本轮 unavailable 合同；
- 不再存在“资金整体缺失但继续生成正常分数”；
- 不再存在“技术整体缺失但所有股票 Trend=0.5”。

### Phase 3：Scoreability、V1.3 与双池

涉及：

- `src/ashare_pilot/strategy/_commands/overnight/score.py`
- 建议新增 `src/ashare_pilot/strategy/intraday_selection.py`
- `src/ashare_pilot/automation/_commands/intraday.py`
- `src/ashare_pilot/strategy/cli.py`
- 新增 `src/ashare_pilot/strategy/_commands/overnight/validate_selection.py`
- `tests/unit/test_batch5_overnight_contract.py`
- `tests/unit/test_stock_money_flow_pagination.py`
- 新增 `tests/unit/test_intraday_selection_pools.py`

任务：

- [x] 实现 Scoreability Gate；
- [x] V1.3 删除缺失字段的 I11 median replacement；
- [x] 重命名 `theme_continuity` 为 `source_capital_proxy`；
- [x] 保持 raw 公式和 18% 权重；
- [x] 只对 scoreable 股票生成分数和唯一 rank；
- [x] 将 execution_state 生成前置；
- [x] 实现资金配置门槛、Trend 0.3、VWAP/I14 分流；
- [x] I14 watch 只进观察池；
- [x] I14 cautious_hold 可进执行池并保留 ceiling；
- [x] tier 不参与执行池过滤；
- [x] 删除 degraded 空池 fallback；
- [x] 构建 Observation Top 30 和原因统计；
- [x] 输出 `selection_pools.json`；
- [x] CLI 参数改为：
  - `--executable-pool-size`；
  - `--observation-pool-size`；
- [x] automation 参数改为：
  - `--executable-size`；
  - `--observation-size`；
- [x] 删除旧 opportunity 参数；
- [x] 新增 `strategy overnight validate-selection`；
- [x] automation 输出摘要改为 executable/observation 数量。

完成标准：

- executable pool 内无封板、无缺失、无低于资金门槛股票；
- observation 与 executable 代码集合互斥；
- D-tier 可在前方大量不可执行时进入 executable pool；
- executable 为空返回 0；
- scored pool 为空返回非零；
- 输出中不存在 `theme_continuity` 和旧 Opportunity 子池。

### Phase 4：Mapper v2 与 Theme Shadow

涉及：

- `src/ashare_pilot/mapping/intraday_contract.py`
- `src/ashare_pilot/mapping/_commands/intraday/mapper_base.py`
- `src/ashare_pilot/mapping/_commands/intraday/validate_annotations.py`
- `src/ashare_pilot/mapping/_commands/intraday/mapper.py`
- `src/ashare_pilot/mapping/_commands/intraday/validate_mapper.py`
- `tests/unit/test_adr0003_theme_evidence.py`
- `tests/unit/test_batch5_overnight_contract.py`
- 新增 `tests/unit/test_intraday_mapper_v2.py`

任务：

- [x] mapper base 必需输入改为 `selection_pools.json`；
- [x] 删除 Opportunity 子池合并函数；
- [x] 分别投影 executable_stocks、observation_stocks；
- [x] 对两池股票重算 execution_state 并比对；
- [x] 不一致时 mapper base 非零退出；
- [x] 附加 primary_theme、themes、market_board；
- [x] 实现 Theme shadow；
- [x] annotations 升级 v2；
- [x] 分离 executable/observation annotation validator；
- [x] Observation annotation 出现执行字段时失败；
- [x] executable annotation 继续执行 stop loss、I14 ceiling、封板和板块不变量；
- [x] 两个 annotation 数组要求精确覆盖；
- [x] mapper 升级 v2 并分别合并 reasoning；
- [x] mapper validator 校验池互斥、覆盖和字段所有权。

完成标准：

- LLM 无法把观察股升级到 executable；
- LLM 无法为观察股创建仓位或止损；
- execution_state 篡改仍被重算发现；
- Theme shadow 缺失状态不会伪造 0.5；
- mapper v2 不包含旧根级 `stocks`。

### Phase 5：Overnight Strategy v2 与 HTML

涉及：

- `src/ashare_pilot/strategy/_commands/overnight/build.py`
- `src/ashare_pilot/strategy/_commands/overnight/validate.py`
- `src/ashare_pilot/strategy/_commands/overnight/render_report.py`
- `tests/unit/test_batch5_workspace_paths.py`
- 新增 `tests/unit/test_overnight_strategy_v2.py`

任务：

- [x] build 只接受 `intraday_mapper.v2`；
- [x] executable actionable → recommendations；
- [x] executable non-actionable → eligible_watchlist；
- [x] observation → observations；
- [x] recommendations 重新执行交易不变量；
- [x] eligible_watchlist 强制 `not_applicable` stop；
- [x] observations 删除全部执行字段；
- [x] 三个视图代码集合互斥；
- [x] recommendations ∪ eligible_watchlist 精确覆盖 executable；
- [x] observations 精确覆盖 observation pool；
- [x] 空 executable 正常生成三个空/观察视图和零仓位；
- [x] HTML 分区展示：
  - 可行动推荐；
  - 合格但观望；
  - 确定性观察池；
  - 数据质量与召回降级；
  - Theme shadow；
- [x] HTML 不把 rank tier 渲染成买入等级。

完成标准：

- JSON validator 通过后才允许 render；
- HTML 渲染失败不改变已验证 JSON 内容；
- 观察表没有买入、止损或仓位文案；
- 空推荐日的 HTML 明确显示“无合适执行候选”，不显示系统故障。

### Phase 6：Skill、规则边界和文档

涉及：

- `.agents/skills/intraday-market-analysis/SKILL.md`
- `.agents/skills/intraday-strategy/SKILL.md`
- `.agents/skills/intraday-stock-discovery/SKILL.md`
- `memory/INTRADAY_RULES.md`
- `memory/RULE_GOVERNANCE.md`
- `docs/current-intraday-stock-selection.md`
- CLI/API 文档及命令示例

任务：

- [x] Skill 输入从 opportunity_pool 改为 selection_pools；
- [x] Reasoning prompt 明确两个 annotation 数组；
- [x] 删除 A/B/C 控制 Opportunity 入选的旧描述；
- [x] 删除 Theme Continuity 名称；
- [x] 明确 Theme shadow 不进分；
- [x] 明确 observation 不允许执行字段；
- [x] 将 INTRADAY_RULES 的 Compute Contract 条目迁移为 ADR-0004 的系统政策引用；
- [x] 学习规则文件只保留学习规则及必要 reference；
- [x] RULE_GOVERNANCE 明确基础策略政策不属于 learned rule 生命周期；
- [x] 保持现有 learned rules 内容和状态，不借迁移修改阈值；
- [x] 更新现状文档为 v2 流程；
- [x] 删除旧 CLI 参数和 JSON 示例。

完成标准：

- 新项目规则表为空时完整运行；
- 全文搜索不再把 `source_capital_proxy` 解释为主题热度；
- 活跃文档和 Skill 不再引用 `opportunity_pool.json`；
- 历史 `docs/superpowers/` 计划可保留旧术语，但明确不作为当前合同。

### Phase 7：冻结回放与收口

冻结日期至少包括：

- 2026-07-20；
- 2026-07-21；
- 2026-07-22；
- 2026-07-23；
- 2026-07-24；
- 2026-07-27。

任务：

- [x] 使用已保存 Compute 数据离线重建 selection pools；
- [x] 记录每日电梯：
  - scoreable/unscoreable；
  - executable；
  - observation；
  - 封板移出执行池数量；
  - 资金/技术/VWAP 原因数量；
- [x] 验证 149 个旧 Opportunity 中的不可交易股票不再进入 executable；
- [x] 解释 Scoreability 样本变化导致的 rank 变化；
- [x] 验证 source_capital_proxy raw 与旧 theme_continuity raw 在相同输入上相等；
- [x] 验证 Theme shadow 不改变任何分数；
- [x] 重建 mapper、strategy 和 HTML；
- [x] 运行完整测试；
- [x] 更新本文 checklist 和状态。

完成标准：

- 所有 executable 股票满足不变量；
- 所有旧封板占位案例进入 observation；
- 无兼容代码路径；
- 无网络测试；
- 无未解释的 Schema 或数量差异。

## 10. 测试矩阵

### 10.1 召回与范围

- [x] trading scope override 在 Scan/Execution 一致；
- [x] 最长前缀一致；
- [x] turnover unavailable + Scan 足量成功；
- [x] turnover unavailable + Scan 不足失败；
- [x] all-stocks partial 失败；
- [x] QuickScore 结果与本期前相同。

### 10.2 Scoreability

- [x] 完整字段可评分；
- [x] money flow partial 未覆盖不可评分；
- [x] 任一资金分档字段缺失不可评分；
- [x] technical no_data 不可评分；
- [x] 关键报价缺失不可评分；
- [x] VWAP 缺失仍可评分但不可执行；
- [x] 缺失股票没有 score/rank；
- [x] 不调用 I11 missing median replacement。

### 10.3 Executability

- [x] 封板只观察；
- [x] board excluded 不进入 Compute 或 executable；
- [x] 资金等于配置门槛通过；
- [x] 资金低于配置门槛失败；
- [x] threshold_reached 未覆盖失败；
- [x] partial 未覆盖按低于门槛处理；
- [x] Trend raw 等于 0.3 通过；
- [x] Trend raw 小于 0.3 失败；
- [x] VWAP 缺失失败；
- [x] 跌破 VWAP无 I14 失败；
- [x] I14 watch 只观察；
- [x] I14 cautious_hold 可执行且 ceiling 保留。

### 10.4 Pool

- [x] 前 30 名全部封板时向后补 executable；
- [x] D-tier 可补入 executable；
- [x] tier 不参与过滤；
- [x] executable 和 observation 互斥；
- [x] observation 原因完整且主原因稳定；
- [x] observation Top 30 截断和统计正确；
- [x] executable 空池成功；
- [x] scored 空池失败。

### 10.5 Schema 与 LLM 边界

- [x] selection pools v1 validator；
- [x] mapper base v2；
- [x] annotations 精确覆盖；
- [x] observation annotation 禁止执行字段；
- [x] executable annotation 禁止 compute 字段；
- [x] execution_state 篡改失败；
- [x] mapper v2 池互斥；
- [x] strategy v2 三视图精确投影；
- [x] 空规则文件成功；
- [x] learned rule 只能降级，不能升级 observation。

### 10.6 Hard Stop

- [x] all-stocks partial；
- [x] 上证缺失；
- [x] 深证缺失；
- [x] Scan 不足；
- [x] money flow unavailable；
- [x] technicals 全部 unavailable；
- [x] Theme Ranking 失败；
- [x] VWAP 全部无效；
- [x] Scored Pool 为空；
- [x] optional Concept Dashboard unavailable 继续。

## 11. 建议测试命令

开发中先运行聚焦测试：

```bash
set PYTHONIOENCODING=utf-8
uv run --frozen python -m pytest -q \
  tests/unit/test_intraday_selection_pools.py \
  tests/unit/test_intraday_mapper_v2.py \
  tests/unit/test_overnight_strategy_v2.py \
  tests/unit/test_intraday_required_data.py \
  tests/unit/test_intraday_recall_quality.py
```

再运行相关回归：

```bash
set PYTHONIOENCODING=utf-8
uv run --frozen python -m pytest -q \
  tests/unit/test_batch5_overnight_contract.py \
  tests/unit/test_stock_money_flow_pagination.py \
  tests/unit/test_intraday_board_codes.py \
  tests/unit/test_intraday_all_stocks_retry.py \
  tests/unit/test_adr0003_theme_evidence.py \
  tests/equivalence/test_batch4_mapping.py \
  tests/equivalence/test_batch5_strategy.py \
  tests/equivalence/test_batch7_automation.py
```

最终运行：

```bash
set PYTHONIOENCODING=utf-8
uv run --frozen python -m pytest -q
uv run --frozen ashare-pilot automation rules check
```

在 Bash 环境中使用：

```bash
PYTHONIOENCODING=utf-8 uv run --frozen python -m pytest -q
```

## 12. 目标 CLI

Compute：

```bash
uv run --frozen ashare-pilot automation intraday run \
  --date YYYY-MM-DD \
  --compute-pool-size 120 \
  --executable-size 30 \
  --observation-size 30
```

单独构建双池：

```bash
uv run --frozen ashare-pilot strategy overnight score \
  .cache/intraday/YYYY-MM-DD/compute_pool_enriched.json \
  --breadth .cache/intraday/YYYY-MM-DD/market_breadth.json \
  --indices .cache/intraday/YYYY-MM-DD/indices.json \
  --executable-pool-size 30 \
  --observation-pool-size 30 \
  --json \
  -o .cache/intraday/YYYY-MM-DD/selection_pools.json
```

验证与发布：

```bash
uv run --frozen ashare-pilot strategy overnight validate-selection \
  --date YYYY-MM-DD
uv run --frozen ashare-pilot mapping intraday build-mapper-base \
  --date YYYY-MM-DD
uv run --frozen ashare-pilot mapping intraday validate-annotations \
  --date YYYY-MM-DD
uv run --frozen ashare-pilot mapping intraday build-mapper \
  --date YYYY-MM-DD
uv run --frozen ashare-pilot mapping intraday validate-mapper \
  --date YYYY-MM-DD
uv run --frozen ashare-pilot strategy overnight build \
  --date YYYY-MM-DD
uv run --frozen ashare-pilot strategy overnight validate \
  --date YYYY-MM-DD
uv run --frozen ashare-pilot strategy overnight render-report \
  --date YYYY-MM-DD
```

## 13. 发布检查

发布前必须逐项确认：

- [x] 当前分支不存在旧 `opportunity_pool.json` 生产读取；
- [x] 当前分支不存在旧 Schema v1 生产读取；
- [x] 当前分支不存在 `theme_continuity` 新输出；
- [x] 当前分支不存在 degraded 空池填充；
- [x] executable pool 中没有 `execution_state.eligible=false`；
- [x] executable pool 中没有 `score_status=unscored`；
- [x] executable pool 中没有低于配置资金门槛的股票；
- [x] executable pool 中没有 technical no_data；
- [x] executable pool 中没有 VWAP missing；
- [x] observation annotations 没有执行字段；
- [x] Theme shadow 不参与 score；
- [x] 空规则项目测试通过；
- [x] 空 executable 项目测试通过；
- [x] 六个冻结日期重放完成；
- [x] 完整 pytest 通过；
- [x] rules check 通过；
- [x] HTML 人工检查通过。

## 14. Definition of Done

只有同时满足以下条件，实施才算完成：

1. ADR-0004 的全部不变量由自动化测试覆盖；
2. `selection_pools.json` 成为唯一双池 Compute 合同；
3. Mapper、annotations、strategy 全部升级 v2；
4. 生产代码不读取或输出旧 Opportunity Schema；
5. 六个冻结日期证明封板不再占执行池；
6. 缺失资金、技术或关键报价的股票没有伪造分数；
7. 所有硬失败和允许降级路径均有测试；
8. Skill、规则治理和现状文档与代码一致；
9. 无学习规则时流水线正常运行；
10. 没有合适股票时正常输出空推荐；
11. 完整测试和规则治理检查通过；
12. 本文状态更新为 Implemented，并记录实际变更与偏差。

## 15. 实施结果与偏差

实施于 2026-07-27 完成。实际交付包括共享 trading scope、召回质量、
必需数据 hard stop、Scoreability/Executability 双门、V1.3 无代理填充评分、
`selection_pools.v1`、Mapper/Annotations/Strategy v2、三视图 HTML、Skill 与规则
治理迁移，以及六个冻结交易日回放。

冻结回放结果见
[`intraday-selection-frozen-replay.v1.json`](intraday-selection-frozen-replay.v1.json)：
720 个 Compute 样本中 213 个可评分、507 个不可评分；149 个旧 Opportunity 中
104 个不可交易候选均未进入新执行池，其中 102 个为封板候选。六日共得到 49 个
执行候选和 180 个 Top-30 观察候选，Mapper、Strategy 和 HTML 均重建成功。

实际偏差只有一项：历史缓存缺少当前 `available`、`main_net_inflow_yuan` 和
technical status 字段，因此六日回放在
`tests/tools/replay_intraday_selection_pools.py` 中使用测试专用、fail-closed
归一化。全零资金分档视为旧接口占位而不可用；该适配器不是生产兼容路径。

最终验收：

- `pytest`: 325 passed、184 skipped、10 subtests passed；
- `automation rules check`: morning 17/20、shared 11/15、intraday 14/15；
- `source_capital_proxy` 与旧名称下的相同 raw 公式完成 720 次相等校验；
- Theme shadow 附加前后分数变化数为 0。
