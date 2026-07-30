# 14:30 隔夜流水线

## 1. 目标

`intraday-market-analysis` 在约 14:30 基于当日真实盘面寻找可执行的隔夜候选，
执行窗口为 14:50–14:57。主题从股票表现自底向上聚合，不使用早盘新闻主题替代
盘中事实。

## 2. 总流程

```text
Compute once
  market breadth / indices / concepts / scan pool
  → enriched compute pool / theme ranking
  → scoreability / scoring / executability
  → selection_pools.json
        │
        ├─ Market perception check
        └─ Stock/theme perception check
                ↓
  intraday_mapper.base.json
                ↓
  portfolio-manager annotations
                ↓
  intraday_mapper.v3
                ↓
  intraday_overnight_strategy.v3 + HTML
```

## 3. Compute once

```bash
uv run --frozen ashare-pilot automation intraday run \
  --date YYYY-MM-DD \
  --compute-pool-size 120 \
  --executable-size 30 \
  --observation-size 30
```

一次运行写入 `.cache/intraday/{date}/`：

- `market_breadth.json`；
- `indices.json` 和 `indices_quality.json`；
- `concept_dashboard.json`；
- `scan_pool.json`；
- `compute_pool_enriched.json`；
- `theme_ranking.json`；
- `selection_pools.json`。

子步骤不得重复抓取或覆盖同日缓存。必须数据缺失时由顶层重新运行完整 Compute。

## 4. 三路召回与 Compute Pool

Scan Pool 将市场活跃股、换手/涨停等市场来源和主题来源合并，统一应用交易范围，
形成较大基础池。Compute Pool 截取指定数量后补充：

- 实时报价和执行状态；
- 股票资金流及覆盖状态；
- 日 K 技术指标；
- VWAP 和盘面特征；
- 静态主题成员关系；
- 数据质量与排除原因。

资金流最低值来自 `config/setting.json`。全市场、资金流、技术或关键指数整体不可用
时 fail closed。

## 5. 双池合同

流程明确分离 Scoreability 与 Executability：

```text
Compute Pool
  ├─ 不可评分 → unscored observation
  └─ 可评分 → Scored Pool → rank/rank_tier
                  ├─ 执行资格通过 → executable_pool
                  └─ 不通过 → scored observation
```

`intraday_selection_pools.v1` 只有：

- `executable_pool`：可评分且通过交易范围、资金、趋势、VWAP、封板等资格；
- `observation_pool`：有观察价值但至少一项确定性执行资格失败。

两池互斥，各最多 30 只且不要求填满。执行池为空是合法结果。A/B/C/D rank tier
只是 Scored Pool 相对排名，不是 Tradeability，也不能把不可执行股票升级入池。

## 6. 感知检查

### 6.1 市场感知

`market-microstructure-analyst` 加载 `intraday-market-scan`，只读 breadth、
indices、concept dashboard 和 scan pool，检查市场强度、宽度、资本方向和概念
Dashboard 一致性。

### 6.2 股票与主题感知

`equity-analyst` 加载 `intraday-stock-discovery`，只读 enriched pool、
theme ranking 和 selection pools，检查数据覆盖、双池互斥和自底向上主题证据。

两类感知都不能生成 Direction、RiskSeverity、Expected Premium 或推荐。

## 7. Mapper 与推理

```bash
uv run --frozen ashare-pilot mapping intraday build-mapper-base \
  --date YYYY-MM-DD
```

Python 把权威市场、主题、池、分数、execution state 和排除信息复制到
`intraday_mapper.base.json`。

`portfolio-manager` 加载 `intraday-strategy`，读取 base、cache、`INTRADAY_RULES.md`
和 `SHARED_RULES.md`，写 `intraday_mapper.annotations.json`：

- executable annotations 精确覆盖执行池，并分为 `primary|alternative|watch`；
- observation annotations 精确覆盖观察池，只含观察摘要、条件和风险说明；
- primary 才能具有可执行 Direction；
- alternative/watch 必须是 `观望`；
- observation 不能被规则或推理升级为 executable。

## 8. 发布

```bash
uv run --frozen ashare-pilot mapping intraday validate-annotations --date YYYY-MM-DD
uv run --frozen ashare-pilot mapping intraday build-mapper --date YYYY-MM-DD
uv run --frozen ashare-pilot mapping intraday validate-mapper --date YYYY-MM-DD
uv run --frozen ashare-pilot strategy overnight build --date YYYY-MM-DD
uv run --frozen ashare-pilot strategy overnight validate --date YYYY-MM-DD
uv run --frozen ashare-pilot strategy overnight render-report --date YYYY-MM-DD
```

正式视图分为：

- `recommendations`：仅 primary，可同时执行的收敛集合；
- `eligible_watchlist`：alternative/watch，不是同时执行指令；
- `observations`：确定性观察池。

策略不输出账户无关的百分比或金额。空执行池发布 `risk_posture=zero` 和观察视图，
不伪造推荐。
