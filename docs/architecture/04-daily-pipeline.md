# 日线盘前流水线

## 1. 目标与时序

`daily-market-analysis` 在交易日 09:20 启动，目标是在 09:35 前发布条件式盘前
计划。架构为 V5 Compute → Perception → Reasoning，分三步串行执行：

```text
Step 1 新闻 + Theme 感知
    ↓ daily_news.v1 + daily_themes.v2
Step 2 股票池 + Mapper 感知
    ↓ daily_mapper.v2 + daily_strategy_input.v2
Step 3 Portfolio Reasoning
    ↓ daily_strategy.v3 + daily_report.html
```

## 2. Step 1：新闻与主题

Owner：`sector-analyst` + `daily-theme-extraction`。

### 2.1 Prepare

```bash
uv run --frozen ashare-pilot themes daily prepare \
  --date YYYY-MM-DD --fetch-news
```

Python 抓取并规范化新闻，写 `news.json` 和 `news.md`，再结合主题 taxonomy 生成
紧凑 `.theme_evidence_input.json`。`news.json` 中的全局递增 `news#id` 是后续
唯一新闻证据引用；Markdown 行号不是证据。

### 2.2 语义 annotations

Agent 只读证据输入和主题语义 rubric，写 `.theme_annotations.json`。LLM 只拥有
accepted refs、confidence、attention direction、政策语义、catalyst 和 reason。
rank、status、heat、公式和 matched concepts 由 Python 所有。

### 2.3 Publish

```bash
uv run --frozen ashare-pilot themes daily publish --date YYYY-MM-DD
```

命令验证 annotation 覆盖和证据归属，在内存组装完整 `daily_themes.v2`，确认三项
正式输出后原子发布 `themes.json`。`step1_timing.json` 只用于观测，不替代合同。

## 3. Step 2：股票映射

Owner：`equity-analyst` + `daily-stock-mapping`。

### 3.1 确定性 Prepare

```bash
uv run --frozen ashare-pilot mapping daily prepare --date YYYY-MM-DD
```

Prepare 完成：

1. 将已验证主题解析到离线主题库；
2. 生成受控股票 universe，不抓全市场约 5500 只股票；
3. 应用 `trading-scope.json`；
4. 为池内股票抓指标和资金/市场数据；
5. 应用硬过滤、软过滤和角色标签；
6. 发布 `theme_stocks.json`，在内存构建 mapper base，并写紧凑 annotation 输入。

### 3.2 股票语义

Agent 为 compact input 中每个候选写且只写一行 annotation：

- 新闻相关度 `R0..R4`；
- 新闻显著性 `P0..P3`；
- 公司级重大事件；
- 稀疏 Pattern override；
- anomaly。

Python 拥有 R×P 分数矩阵、技术值、来源、角色、成员和最终 mapper 组装。Step 2
严格禁止 Direction、RiskSeverity、价格计划和推荐。

### 3.3 Finalize

```bash
uv run --frozen ashare-pilot mapping daily validate-annotations \
  predict/YYYY-MM-DD/mapper.annotations.json --date YYYY-MM-DD
uv run --frozen ashare-pilot mapping daily finalize --date YYYY-MM-DD
```

Finalize 重建并写出 `daily_mapper_base.v2`，再发布 `daily_mapper.v2` 和紧凑
`daily_strategy_input.v2`。Step 3 只消费 `mapper.strategy_view.json`，不重新
读取完整新闻、指标和 mapper。

## 4. Step 3：日策略

Owner：`portfolio-manager` + `daily-strategy`。

### 4.1 Prepare

```bash
uv run --frozen ashare-pilot strategy daily prepare --date YYYY-MM-DD
```

Python 校验 Step 2 输入，为全部候选计算 advisory Trade Profile，构造
`.strategy_llm_input.json` 和 SHA-256 指纹。所有候选必须完整、同序进入紧凑输入，
禁止 top-N 预筛。

### 4.2 Draft

Portfolio Manager 读取紧凑输入、策略 rubric、`RULES.md` 和
`SHARED_RULES.md`，只为最终入选股写 `strategy.draft.json`。它拥有最终 regime、
代码和顺序、Direction、评级、RiskSeverity 应用与 reasoning。

主列表上限随市场状态收缩：

| Regime | 最大入选数 |
|---|---:|
| `strong-sector` / `neutral` | 10 |
| `weak` | 7 |
| `panic` | 5 |

### 4.3 Finalize

```bash
uv run --frozen ashare-pilot strategy daily finalize --date YYYY-MM-DD
```

Finalize 校验输入指纹、草稿时序、候选和证据归属；按最终 regime 重算确定性执行
计划；补齐所有未选候选的观察行；验证并发布：

- `strategy.json`：`daily_strategy.v3`；
- `daily_report.html`：从正式 JSON 渲染的人类看板；
- `step3_timing.json`：非合同性能数据。

## 5. 策略安全约束

- 新仓计划是 T+1 条件计划，最早不早于 09:35:05；
- 仓位仅 `WATCH_ONLY|LIGHT|STANDARD`；
- 不输出账户无关百分比、金额、股数或手数；
- 每个入选股必须有来自输入的主题、role tag 或 `news#id`；
- Python baseline 是 advisory，不能替代最终 LLM 判断；
- Step 3 不写 memory，memory 更新属于盘后复盘。

## 6. 失败语义

- Step 1/2 输入或确定性合同错误：停止，不让 LLM 修补；
- annotation/draft 字段错误：按 Skill 最多进行一次完整修复；
- 指纹不匹配或草稿早于 prepare：重新 prepare/读取并重写 draft；
- 第二次 LLM 输出仍失败：不发布策略；
- timing 写入失败可告警，但不能使已经有效的策略合同失效。
