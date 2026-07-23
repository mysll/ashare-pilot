# Mapper V4 Unified — Step 2 SKILL + Schema Revision Plan

Date: 2026-06-27
Status: **Draft for execution** — schema + script alignment + rubric + process

## 设计原则

> *Formulas should not be LLM-computed; judgments should not be LLM-stripped.*
> 公式不应由 LLM 计算；判断不应从 LLM 拿走。

V3 成功地形式化了 Step 2 → Step 3 的数据契约（结构化表、无 prose、Strategy Inputs 作为权威源），副作用是 LLM 判断空间塌缩到几个未规范化的打分字段（News_Impact、theme_heat 子分），而确定性逻辑（Direction、Risk Ceiling）却被文档化为"由 LLM 执行的规则"。同时脚本层与文档层在 MACD / MA Trend / 缺失数据处理等处出现实现错位。

本次修订**不分主从**融合两份来源方案（V4 schema 设计 + 25 项分析补丁包），达成三条主线：

1. **脚本-文档强制对齐**（V4 out-of-scope，本稿接管）
2. **LLM 判断容量回拨**（V4 主体：Direction 分层 / Rubric 化 / Anomaly 窗口）
3. **流程与工程修复**（板排除配置化 / 流程依赖 / 批量化）

## 作用域

| In scope | Out of scope |
|----------|----------------|
| `.agents/skills/daily-stock-mapping/SKILL.md` 全文修订 | Theme Library 重建 |
| `fetch_pool_indicators.py` 公式对齐（6 项） | backtest 自动化 |
| `config/trading-scope.json` 板排除配置 | themes.md / theme_stocks.md 表头改造 |
| Step 3 read contract 同步说明 | mapper.json 二进制 schema（future） |
| `memory/RULES.md` OverrideHint token 映射 | daily-strategy SKILL 实施落地 |

## 修订总览 — V3 → V4 Unified 改动矩阵

| # | 改动 | 作用层级 | 影响文件 | 来源 |
|---|------|---------|---------|------|
| U-1 | Direction 拆 base/final | schema | SKILL | V4 |
| U-2 | RiskType + RiskSeverity 分级（替代一刀切 ceiling） | schema | SKILL | V4 |
| U-3 | NewsImpact 二维矩阵 + cap=60 缓解 News 双重计入 | schema + rubric | SKILL | V4 + 决策② |
| U-4 | Anomaly ≤30 字段 | schema | SKILL | V4 |
| U-5 | BoardPolicy / trading-scope.json 配置化 | process + config | SKILL + config | V4 |
| U-6 | RegimeHint 市场状态 hint | schema | SKILL | V4 |
| U-7 | HeatTrace / Score Trace 审计列 | schema | SKILL | V4 |
| U-8 | OverrideHint token（R37/R61/R39-v3/R35-v3/R73/R74） | schema + process | SKILL + RULES | V4 |
| U-9 | MajorEvent strict rubric（Default None） | rubric | SKILL | V4 |
| U-10 | theme_heat 子分 rubric（P/C/E 三表） | rubric | SKILL | V4 |
| U-11 | ExclusionSource 分类 | schema | SKILL | V4 |
| U-12 | Step 3 read contract 形式化 | process | SKILL + daily-strategy | V4 |
| P0-1 | MACD 实现从 2 级扩到 5 级 | formula | fetch_pool_indicators.py + SKILL | 决策③ |
| P0-2 | MA Trend 补 `P<ma20, ma20>ma50=40` 分支 | formula | fetch_pool_indicators.py + SKILL | 25 项 |
| P0-3 | 删除"流动性 flag 注入"（hard filter 已删） | formula | fetch_pool_indicators.py | 25 项 |
| P0-4 | 缺失数据 NULL 不再静默填 50；子分按权重重归一 | formula | fetch_pool_indicators.py + SKILL | 25 项 |
| P0-5 | Raw fields 计数统一为 13（不含 code） | doc | SKILL | 25 项 |
| P0-6 | Price 字段三态 + PriceSource 列 | schema | SKILL | 25 项 |
| P0-7 | Phase 2 单股失败 → `fetch_failed:true` 占位行 | process | fetch_pool_indicators.py + SKILL | 25 项 |
| P1-1 | Money_Flow 公式 + cookie 失效 fallback | formula | SKILL | 25 项 |
| P1-2 | Auction Turnover 缺失时权重归一公式 | formula | SKILL | 25 项 |
| P1-3 | Auction Change% 边界顺序固化 | formula | SKILL | 25 项 |
| P3-1 | Anchor 单一权威查询，删除 Anch? 临时代号列 | process | SKILL | 25 项 |
| P3-2 | pure stock 循环边界（1 轮、post-filter count） | process | SKILL | 25 项 |
| P3-3 | Strategy Inputs 大表分批（>50 行每 25 行子表） | process | SKILL | 25 项 |
| P3-4 | 删除"边缘扩散→新龙头... most valuable signal"策略语义话术 | doc | SKILL | 25 项 |
| P3-5 | `query_theme.py pure --all-themes` 批量化 | engineering | query_theme.py | 25 项（follow-up） |

## 文件改动规模预估

- `SKILL.md` 增修订约 250 行
- `fetch_pool_indicators.py` 修订约 80 行
- 新增 `config/trading-scope.json`
- 可选新增 `query_theme.py` 子命令（follow-up issue）

---

## 1. mapper.md 输出 Schema — 7 节布局

仍为 7 节，仍**无 prose 段落**。V3 基础上 +1 节 `Score Trace`（最低形式要求 CompositeTrace 列即可）。

| # | Section | V3 → V4-U 变化 |
|---|---------|----------------|
| 1 | Market State | +2 字段 BoardPolicy / RegimeHint |
| 2 | Theme Ranking | +HeatTrace 列 |
| 3 | Candidate Pool | **核心列大幅修订** |
| 4 | Strategy Inputs | +PriceSource 列，其余不变 |
| 5 | Score Trace | **新增**（最低形式要求 CompositeTrace） |
| 6 | Observation Pool | +Anomaly 列（含 RiskFlags 的行） |
| 7 | Excluded Stocks | +ExclusionSource 列 |

### Section 1：Market State

```markdown
## Market State

| Field | Value |
|-------|-------|
| DominantThemes | 半导体(91), AI算力(80) |
| FinancingFlow | +61.31亿净买入 |
| RiskFlags | RMBWeakness, APACPressure |
| BoardPolicy | sh688=exclude, bj=exclude |
| RegimeHint | strong-sector |
```

| Field | Type | Source | Notes |
|-------|------|--------|-------|
| DominantThemes | string | themes.md top 2-3 | 不变 |
| FinancingFlow | string | news / fetch_special | 不变 |
| RiskFlags | string | news.md 宏观扫描 | 逗号分隔 token |
| **BoardPolicy** | string | config/trading-scope.json | 反映当前实际排除策略，非硬编码 |
| **RegimeHint** | enum | LLM + 指数预读 | `strong-sector` \| `neutral` \| `weak` \| `panic` — **hint only**，Step 3 用实时指数确认 |

**RegimeHint 阈值**（参考，Step 2 不硬编码进 Direction）：

| Value | Condition（上证竞价/昨收） |
|-------|---------------------------|
| panic | < -1.5% |
| weak | -1.5% ~ -0.5% |
| neutral | ±0.5% |
| strong-sector | neutral index BUT dominant theme heat ≥ 85 OR 科创50 > +2% |

### Section 2：Theme Ranking

新增 `HeatTrace` 列 — theme_heat 子分审计。

```markdown
| Theme | Heat | Rank | HeatTrace |
|-------|------|------|-----------|
| 半导体 | 91 | 1 | P85/C70/E95/N8 |
```

| Token | 含义 |
|-------|------|
| P | policy 0-100 |
| C | capital 0-100 |
| E | emotion 0-100 |
| N | news_count（整数） |

公式保留：`heat = P×0.40 + C×0.15 + E×0.25 + N×0.20`（news_count 先归一化到 0-100 再加权）。

> **News 双重计入处理决策**：保留 theme_heat 公式不动，依赖 V4 §NewsImpact 中 `MajorEvent=Negative → NewsImpact cap=60` 缓解双重加权叠加爆炸。日常主题新闻有效权重约 26%，作为设计接受。

**Theme heat 子分 rubric（LLM MUST follow）**

| Policy (P) Score | Condition |
|-------|-----------|
| 90-100 | 国家/行业政策明确点名主题；监管文件、国务院、部委 |
| 75-89 | 强政策代理（标准、补贴、试点区）无头条政策 |
| 60-74 | 间接政策受益（供应链、本地化） |
| <60 | 无政策角度 — discard theme |

| Capital (C) Score | Condition |
|-------|-----------|
| 85-100 | 融资流入/北向/龙虎榜净买入与主题对齐（今日或昨日） |
| 65-84 | 板块成交放大、融资扩张 |
| 45-64 | 中性 |
| <45 | 流出或无资金信号 — 用 45 default |

| Emotion (E) Score | Condition |
|-------|-----------|
| 90-100 | ≥3 flash 项 + 热股榜 + 主题内涨停簇 |
| 75-89 | 2 条新闻 或 1 条重大头条 |
| 60-74 | 仅语义匹配，媒体密度低 |
| <60 | discard |

News count (N) — 映射到该主题的不同新闻条数原始计数（整数，显示截断至 20）。

### Section 3：Candidate Pool — 核心修订

**V3 列（保留）**：`Code`, `Name`, `Composite`, `Theme`, `RoleTags`, `Emotion`, `Turnover%`, `Risk`

**V3 列（改变）**：

| V3 | V4-U | 变更 |
|----|-----|------|
| `Direction` | `DirectionBase` + `DirectionFinal` | 拆 base / post-override |
| `MajorEventFlag` | `MajorEvent` | 同 enum，配更严格 rubric |
| `Risk` (自由文本) | `RiskFlags` + `RiskType` + `RiskSeverity` | 结构化 |

**V4 新列**：

| Column | Type | Description |
|--------|------|-------------|
| **NewsImpact** | int 0-100 | per-stock，rubric 见下 |
| **NewsLink** | string | news 项 id 或 ≤15 char 锚点（`flash#3`, `finance#12`） |
| **CompositeTrace** | string | 紧凑形式 `T91/N82/A75/Tech78/MF65` |
| **DirectionBase** | enum | 仅 composite 映射结果（脚本可算） |
| **DirectionFinal** | enum | RiskSeverity + MajorEvent + RegimeHint 调整后 |
| **RiskType** | enum | 主风险类别（Step 3 路由用） |
| **RiskSeverity** | int 1-3 | 1=informational, 2=caution, 3=hard caution |
| **OverrideHint** | string | 逗号分隔 RULE token，Step 3 应考虑 |
| **Anomaly** | string ≤30 字符 | 可选；规则之外的提取模式 |

**示例行**：

```markdown
| Code | Name | Composite | DirectionBase | DirectionFinal | Theme | RoleTags | NewsImpact | NewsLink | Emotion | Turnover% | RiskFlags | RiskType | RiskSeverity | OverrideHint | Anomaly | MajorEvent |
|------|------|-----------|---------------|----------------|-------|----------|------------|----------|---------|-----------|-----------|----------|--------------|--------------|---------|------------|
| sh603986 | 兆易创新 | 76.72 | bullish | neutral-bull | 半导体 | IndustryLeader,Candidate | 88 | flash#2 | 92.5 | 7.61% | RSI>75 | overbought | 2 | R37 | — | None |
| sh600048 | 保利发展 | 42.1 | bearish | bearish | 房地产 | — | 35 | — | 10 | 1.2% | RSI<30,MA双熊 | oversold-opportunity | 1 | R61 | 利空出尽缩量 | None |
```

### Section 4：Strategy Inputs

V3 不变，**仅补 PriceSource 列**（解决 P0-6 三态漂移）：

```markdown
| Code | Price | PriceSource | MA20 | ATR | ATR% | High20 | Low20 |
|------|-------|-------------|------|-----|------|--------|-------|
| sh603986 | 94.70 | Auction | 79.42 | 6.14 | 6.50 | 94.70 | 65.72 |
```

| PriceSource | 含义 | 何时使用 |
|-------------|------|----------|
| `PrevClose` | 昨日收盘 | pre-market < 9:15 |
| `Auction` | 集合竞价价 | 9:15-9:25 |
| `Live` | 盘中实时 | intraday 运行 |

数据源：Technical Enrichment Phase 2 K 线记录。无额外 API 调用。Step 3 **必须直接使用 Strategy Inputs**，不可重新 fetch，除非字段缺失/无效/陈旧。

### Section 5：Score Trace（新增）

每行一个 Candidate Pool 股。无 prose 也能审计。

```markdown
## Score Trace

| Code | CompositeTrace | DirectionPath | NewsImpactCalc |
|------|----------------|---------------|----------------|
| sh603986 | T91×0.3+N88×0.2+A60×0.2+Tech78×0.2+MF70×0.1=76.7 | bullish→(RSI>75,sev2)→nb +R37 | R4×P3=95→88(多源+5) |
```

| Column | Content |
|--------|--------|
| CompositeTrace | 加权项 → 四舍五入结果 |
| DirectionPath | base → risk adjustment → final + hints |
| NewsImpactCalc | matrix cell + adjustments |

**最低形式要求**：Candidate Pool 必须含 `CompositeTrace` 列。Score Trace 表对 Composite ≥ 70 的股票强制（其余可选）。

### Section 6：Observation Pool

阈值不变（Composite < 55）。补 **Anomaly** 列（对仍值得次日观察的低 composite 标记）。

### Section 7：Excluded Stocks

```markdown
| Code | Name | ExclusionReason | ExclusionSource |
|------|------|-----------------|-----------------|
| sh688256 | 寒武纪 | 科创板不可交易 | board-policy |
| sz300975 | 商络电子 | atr_pct=9.0% > 8% | hard-filter |
```

| ExclusionSource | Meaning |
|-----------------|---------|
| `board-policy` | 配置驱动（sh688/bj via trading-scope.json） |
| `hard-filter` | liquidity / atr_pct |
| `soft-filter` | tech_score < 50 |
| `indicators-fetch-failed` | Phase 2 fetch 失败（P0-7 新分类） |
| `manual` | LLM 显式排除并附 reason |

---

## 2. Direction 模型（替代 V3 一刀切 Risk Ceiling）

### Step A — DirectionBase（确定性，脚本可算）

| Composite | DirectionBase |
|-----------|---------------|
| ≥ 70 | bullish |
| 55-69 | neutral-bull |
| 45-54 | neutral |
| < 45 | bearish |

### Step B — RiskType + RiskSeverity（暂不调 Direction）

每个 `RiskFlags` 条目映射**一个 primary** RiskType（最高 severity 胜出）：

| RiskFlag | RiskType | RiskSeverity | 理由 |
|----------|----------|:------------:|------|
| RSI>75 | `overbought` | 2 | caution，不等同 trend break |
| RSI<30 | `oversold-opportunity` | **1** | 机会 hint — **不**与 MA双熊 同档 |
| MA双熊 | `trend-weak` | 3 | 结构性弱势 |
| 炸板 | `broken-board` | 2 | 事件复盘 (R39/R35) |
| Auc<-5% | `auction-anomaly` | 2 | 操纵 / 恐慌竞价 |
| ATR>8% | (hard exclude) | — | 留 Excluded，不进 pool |

**V3 → 关键变化**：RSI<30 severity **1**（informational）；MA双熊 severity **3**。V3 对所有 flag 一律压制 `neutral-bull`，V4-U 分级。

### Step C — DirectionFinal（软约束 + hints）

按顺序应用，记入 `OverrideHint`：

```
DirectionFinal = DirectionBase
FOR each adjustment:
  IF MajorEvent = Positive      → shift +1 level (cap bullish)
  IF MajorEvent = Negative      → shift -1 level (cap bearish)
  IF RiskSeverity = 3 AND RegimeHint != strong-sector
                                → cap at neutral-bull (was: all flags)
  IF RiskSeverity = 2           → no automatic cap; set OverrideHint only
  IF RiskSeverity = 1           → no cap; set OverrideHint only
CLAMP to [bearish … bullish]
```

**OverrideHint tokens**（Step 3 应用 RULES.md 前必须读）：

| Token | When set | Step 3 meaning |
|-------|----------|----------------|
| `R37` | RiskType=overbought AND theme heat ≥ 85 | 强市场：不因 RSI auto-exclude |
| `R61` | RiskType=oversold-opportunity | 分级 entry；不当日建仓 |
| `R39-v3` | RiskType=broken-board AND theme heat ≥ 80 | 涨停炸板 watch 模式 |
| `R35-v3` | Emotion ≥ 85 AND board_streak ≥ 1 | 连续探测 eligible |
| `R73` | RiskType=trend-weak AND RegimeHint=weak | MA20 buffer / 更宽止损 |
| `R74` | RiskType=trend-weak AND RegimeHint=strong-sector | 不因 MA 单维度降级 |

DirectionFinal 是**默认 stance**，非 hard veto。Step 3 log 必须引用 OverrideHint 当偏离时。

---

## 3. NewsImpact Rubric（per-stock, 0-100）

二维查表。LLM 选 **一格**，可插值 ±5 并在 Score Trace 给一行 reason。

### Dimension 1: Relevance (rows)

| Tier | Code | Condition |
|------|------|-----------|
| R4 | Direct | 公司名或代码在头条 |
| R3 | Supply-chain | 客户/供应商/合同方被点名 |
| R2 | Sector | 主题级新闻，无公司名 |
| R1 | Proxy | 仅指数/同行/行业数据 |
| R0 | None | 无关联 — 不应在 pool |

### Dimension 2: Prominence (columns)

| Tier | Code | Condition |
|------|------|-----------|
| P3 | Headline | 标题主体或首段 lead |
| P2 | Body | 正文提及，material detail |
| P1 | List | 仅表/列表/chain 提及 |
| P0 | Absent | — |

### Score matrix

|  | P3 Headline | P2 Body | P1 List |
|--|:-----------:|:-------:|:-------:|
| **R4 Direct** | 95 | 85 | 70 |
| **R3 Supply-chain** | 80 | 70 | 55 |
| **R2 Sector** | 65 | 55 | 40 |
| **R1 Proxy** | 45 | 35 | 25 |

**Adjustments（叠加，cap 0-100）**：

| Condition | Δ |
|-----------|---|
| 同股同日出现在 ≥2 个新闻源 | +5 |
| Negative sentiment（penalty / investigation） | -20 |
| MajorEvent = Positive / Negative | 用 MajorEvent 替代；NewsImpact 上限 60 for Negative（缓解 News 双重计入叠加爆炸） |

`NewsLink` = 指向 `news.md` 源行的最短指针（如 `flash#3`）。

---

## 4. MajorEvent Rubric（比 V3 更严格）

| Value | Required evidence |
|-------|-------------------|
| **Positive** | 点名公司 + 离散事件：订单中标、重组、业绩 >20% 超、产品获批 |
| **Negative** | 点名公司 + 离散事件：处罚、立案、造假、停牌、大幅减持 |
| **None** | 其他一切 — **包括**行业景气、TSMC 涨价、论坛开幕 |

默认 **None**。Step 2 不得用 MajorEvent 承载主题级催化。

---

## 5. Anomaly 字段（≤30 中文字）

**目的**：透传rubric 会扁平化的结构性模式，不重开 prose mapper。

| Allowed | Example |
|---------|---------|
| 模式标签 | `三日缩量首板`, `板块龙头猝死`, `边缘扩散新龙头` |
| 跨主题 | `跨半导体+AI算力` |
| 事件形态 | `涨停开板二次封` |

| Forbidden | 原因 |
|-----------|------|
| 买卖建议 | Step 3 领地 |
| 价格目标 | Step 3 领地 |
| >30 char | 保持表可扫描 |

**必需情形** — 任一即写：

- 股票经由 `market_active` cross_rank_highlights 入池
- LHB 注入且净买入 > 0
- board_streak ≥ 2 但 Composite < 70
- LLM 判定 RiskType 单独不足以描述 setup

否则 `—`。

---

## 6. P0 脚本对齐包（V4 out-of-scope，本稿接管）

> 决策③：MACD 改脚本实现 5 级，而非降低文档规格。

### P0-1 MACD 5 级评分实现

`fetch_pool_indicators.py:193-196` 当前：
```python
mac_s = 75 if mh > 0 else 25
```

改为实现 SKILL line 370 五级：

```python
prev_mh = _to_float(records[last_idx-1].get("macdh")) if last_idx > 0 else None
if mh is not None:
    if mh > 0 and prev_mh is not None and mh > prev_mh:
        mac_s = 100          # 加速
    elif mh > 0:
        mac_s = 75           # macdh > 0
    elif abs(mh) < 0.05:     # crossing 0（阈值 0.05 量级，Open Question）
        mac_s = 50
    elif mh < 0:
        mac_s = 25
    else:  # mh < 0 且 |mh| 递增
        mac_s = 0
else:
    mac_s = None  # 缺失交给 P0-4 重归一逻辑
```

### P0-2 MA Trend 补分支

`fetch_pool_indicators.py:188-191` 当前对 `P<ma20, ma20>ma50` 落 `else 0` (回到中期多头却记 0，错位)。补：

```python
if m20 is not None and m50 is not None and p is not None:
    if p > m20 > m50:
        ma_s = 100
    elif m20 > m50 and p <= m20:
        ma_s = 40         # 回踩中期多头，弱多头
    elif p > m20:
        ma_s = 60
    else:                 # p < ma20 且 ma20 < ma50 (双熊)
        ma_s = 0
else:
    ma_s = None
```

### P0-3 删除流动性 flag 注入

`fetch_pool_indicators.py:256-257` 删除：
```python
if amt is not None and amt < 30000:
    flags.append("流动性<3亿")
```

理由：流动性 < 3亿已属 hard filter，被删除的股票不应再带 flag。SKILL 同步加说明"hard filter 不重复标 flag"。

### P0-4 缺失数据 NULL 不静默填 50

当前 `_sc(v, default=50)` 把任何 None 默认中位，系统性拔高缺数据股票。改为：

- `row[field] = None`（保留显式缺失）
- 子分计算：缺失因子**跳过**，剩余因子按原权重比例**重归一化**

示例：traditional 6 因子，amount 缺失时：
```
remap_weights = original_weights[not_none_factors] / sum(original_weights[not_none_factors])
traditional = sum(score[f] × remap_weight[f])
```

当传统层所有因子都缺失 → `traditional = None` → `tech_score = None` → 该股降入 Observation Pool 并标 `IndicatorsMissing`。

SKILL 新增 "Missing Data Handling" 段说明此策略。

### P0-5 Raw fields 计数统一

文档表格 line 331 改 "Raw indicators (13)"（不含 code），脚本文档注释改 "13 raw indicators + code = 14"。

### P0-6 PriceSource 列

见 Section 4。Strategy Inputs 表新增 `PriceSource` 列，枚举 `PrevClose / Auction / Live`，按运行时间的 fetch_stock.py 数据状态决定。

### P0-7 Phase 2 fetch_failed 占位行

`fetch_pool_indicators.py` 单股 except 分支当前 `continue`，导致 pool 内有股但 Phase 2 缺记录。改为：

```python
results.append({"code": code, "fetch_failed": True})
```

SKILL 规定：fetch_failed 股降入 Observation Pool，RiskFlags 标 `Indicators_Fetch_Failed`，不进 Candidate Pool。

---

## 7. P1 缺失打分公式包（V4 未覆盖）

### P1-1 Money_Flow 打分公式

```
Money_Flow = 0.6 × IndustryFlowScore + 0.4 × StockFlowScore

  IndustryFlowScore = clamp(50 + 100 × 行业净流入 / 行业流通市值, 0, 100)
  StockFlowScore    = 50 + sign(主力净流入) × min(|净流入| / amount, 1) × 50
```

- cookie 失效 / fetch 失败 → `Money_Flow = 50`（中性），Risk 加 `MoneyFlowStale` flag
- intraday 实时 money flow 可用时用上述公式；pre-market 走昨日数据

### P1-2 Auction Turnover Rate 缺失时归一

```
若 float_shares None：
  auction_score = AucChg% × (0.40/0.75) + AucAmt × (0.35/0.75)
                 = AucChg% × 0.533 + AucAmt × 0.467
```

按 0.40:0.35 比例重归一，**不**简单加到 AucAmt 上。

### P1-3 Auction Change% 边界顺序

固化顺序：先按绝对值分级 → 再按正负方向调整 → clip [0,100]：

```
abs(percent):
  ±2~5%   → 100
  ±1~2%   → 85
  ±0.5~1% → 70
  ±0~0.5% → 50
  >±5%    → 40（异常竞价，watch 操纵）

if percent < 0: score /= 2   （halved）
```

明确：`-3%` = 100/2 = 50；`-0.3%` = 50/2 = 25；`-6%` = 40/2 = 20。

---

## 8. P3 流程与工程修复

### P3-1 Anchor 单一权威查询

删除 `theme_stocks.md` Stock Pool 表中的 `Anch?` 临时代号列。统一在 Structured Dataset 阶段一次性 `query_theme.py stock <code> --roles` 取 RoleTags，避免两阶段 anchor 判定不一致。

### P3-2 pure stock 循环边界

- 触发条件：post-filter count < 8（hard filter 后计数）
- 最多 1 轮 `--top 20` 重跑
- 不可无限循环

### P3-3 Strategy Inputs 大表分批

Candidate Pool > 50 行时按 Composite 降序分批，每 25 行子表，避免 markdown 单表过宽难以读取。

### P3-4 删除策略语义话术

SKILL line 159 "classic 边缘扩散 → 新龙头 pattern — the most valuable trading signal the market view provides" 改为纯数据描述：
```
cross_rank_highlights 表示该股出现在 ≥2 个 top-N 列表中，attention_score + industry_score 值已给出。
```

### P3-5 `query_theme.py pure --all-themes` 批量化

follow-up issue。新增 `pure --all-themes --top N` 一次拉所有主题的 pure_stocks，替代 SKILL 中 20 次独立 subprocess，预计节省 30-40s。

### P3-6 RULES.md 引用规范化

SKILL 中 risk flag 表 line 405-410 的明文 R37/R61/R73/R74 引用全部替换为 OverrideHint token 引用形式（第 2 节已给 token 表），避免读者把 Step 2 当作"读 RULES.md"的责任边界混淆。

### P3-7 Board policy 配置文件

新增 `config/trading-scope.json`：

```json
{
  "boards": {
    "sh688": { "exclude": true, "reason": "STAR board — account scope" },
    "bj":    { "exclude": true, "reason": "BSE — account scope" },
    "sh":    { "exclude": false },
    "sz":    { "exclude": false }
  },
  "overrides": []
}
```

Step 2 读 config → 写 `BoardPolicy` 到 Market State。overrides 允许单代码例外，无需改 SKILL。

**影响**：toggled 时半导体/AI 主题的 688 龙头以 `ExclusionSource=board-policy` 出现在 Excluded Stocks，非沉默丢弃。

---

## 9. Migration（V3 → V4-U）

| V3 field | V4-U mapping |
|----------|-------------|
| Direction | → DirectionBase + DirectionFinal |
| MajorEventFlag | → MajorEvent |
| Risk | → RiskFlags + RiskType + RiskSeverity |
| (none) | + NewsImpact, NewsLink, OverrideHint, Anomaly, CompositeTrace |
| (none) | + PriceSource (Strategy Inputs) |
| (none) | + ExclusionSource (Excluded Stocks) |

**Backward compatibility**：Step 3 skill 在 V4-U mapper 缺 `DirectionFinal` 时退化为 V3 处理（`Direction` 兼作 base+final，`OverrideHint=—`）。

---

## 10. Step 3 Read Contract

Step 3 **MUST** read in order:

1. `Market State`：`RegimeHint`、`BoardPolicy`
2. `Candidate Pool`：`DirectionFinal`、`RiskType`、`RiskSeverity`、`OverrideHint`、`Anomaly`
3. `Strategy Inputs`：`Price`、`PriceSource`、`MA20`、`ATR`、`ATR%`、`High20`、`Low20`
4. `memory/RULES.md`

Step 3 **MUST NOT**:

- 重新派生 Composite 或 NewsImpact
- 当 `OverrideHint` 适用时忽略该 token
- `OverrideHint` 存在时把 `DirectionFinal` 视为 hard veto
- 重新 fetch Strategy Inputs 已给字段（除非缺失/无效/陈旧）

**示例 decision log 行（目标格式）**：

```
sh603986: DirectionFinal=neutral-bull, OverrideHint=R37, RegimeHint=strong-sector → apply R37, retain 4★, MA20 buy zone unchanged
```

---

## 11. Success Criteria

| Metric | Target |
|--------|--------|
| Step 2 输出 | 仍零 prose 段落 |
| NewsImpact | 每个 pool 股在 Score Trace 引用矩阵 cell |
| Risk differentiation | RSI<30 与 MA双熊 不共享 RiskType |
| OverrideHint 引用 | 强市场日 RSI>75 决策 ≥80% 引用 OverrideHint |
| Anomaly 使用 | 活跃市场日 ≥1 行，无买卖建议 |
| **审计可复算** | 第三方可从 Score Trace 重算 DirectionBase + Composite |
| **脚本-文档对齐** | fetch_pool_indicators.py 各字段逐项与 SKILL 文档公式一致 |
| **缺数据不静默拔分** | 缺失因子不落 default=50，重归一权重后子分仍可解释 |

---

## 12. Open Questions

1. **Score Trace 强制范围**：V4 推荐 Composite ≥ 70 强制，其余可选。确认？
2. **RegimeHint vs Step 3 index fetch 重叠**：intraday 时 Step 3 实时 fetch 仍 authoritative，RegimeHint 仅 pre-market prior。确认？
3. **R73 / R74 在 RULES.md 是否已定义**：启用 OverrideHint token 前必须落定，否则 token 引用悬空。
4. **JSON sidecar**：未来 option `mapper.json` 同 schema 用于 backtest — Out of scope this phase。
5. **MACD 加速判定阈值**：`mh > prev_mh` 用 0 量级还是 0.1 量级？影响 crossing 分档稳定性。
6. **`query_theme.py pure --all-themes` 批量化**：是否随本稿落地，还是开 follow-up issue？

---

## 13. Implementation Sequence

```
Phase 1: 脚本对齐（P0 包 #P0-1~P0-7）
   ├─ fetch_pool_indicators.py 改 ~80 行
   └─ 不依赖文档；先行可验证

Phase 2: Schema 落稿 SKILL.md（Sections 1-5 + Direction 模型 + rubrics）
   ├─ 依赖 Phase 1 公式正确性
   └─ 同步 HeatTrace / CompositeTrace / NewsImpact 表 / RiskSeverity / OverrideHint token

Phase 3: P1 公式补齐（Money_Flow / Auction）
   ├─ SKILL.md 新增 3 段
   └─ 与 Phase 2 可并行

Phase 4: P3 流程优化 + config/trading-scope.json
   ├─ SKILL 中 Anch? 列删除、pure 循环边界、Strategy Inputs 分批
   └─ 依赖 Phase 2 完成

Phase 5: Companion 更新
   ├─ daily-strategy SKILL.md：读新列、OverrideHint token 路由
   ├─ memory/RULES.md：R37/R61/R39-v3/R35-v3/R73/R74 token 定义
   └─ 可与 Phase 4 并行
```

---

## 14. 附：来源映射

| 章节 | V4 设计 | 25 项分析补丁 | 合并决策 |
|------|---------|--------------|----------|--|
| §1 Market state + RegimeHint | √ | | 接受 V4 |
| §2 Theme Ranking + HeatTrace + 子分 rubric | √ | | 接受 V4 |
| §3 Candidate Pool 列设计 | √ | | 接受 V4 |
| §4 Strategy Inputs + PriceSource | 部分 | √ (P0-6) | 合并 |
| §5 Score Trace | √ | | 接受 V4 |
| §6 Observation Pool + Anomaly | √ | | 接受 V4 |
| §7 Excluded + ExclusionSource | √ | √ (P0-7) | 合并 |
| Direction 模型 DirectionBase/Final | √ | √ (P2-1 分级) | 完全一致，融合 |
| RiskSeverity 分级表 | √ | √ | 完全同向 |
| NewsImpact 矩阵 | √ | √ 类似 | 接受 V4 精化 |
| News 双重计入缓解 | √ cap=60 | √ 决策② | 接受 V4 cap=60（决策②） |
| MajorEvent strict rubric | √ | | 接受 V4 |
| OverrideHint token | √ | √ (P3-6 剥离_TRNS) | 合并升级 |
| Board policy 配置化 | √ | √ (P2-3) | 接受 V4 schema |
| MACD 5 级修正 | 未涉及 | √ (P0-1) | 决策③ 改脚本 |
| MA Trend 补分支 | 未涉及 | √ (P0-2) | 接受 |
| 缺失数据重归一 | 未涉及 | √ (P0-4) | 接受 |
| PriceSource 列 | 未涉及 | √ (P0-6) | 接受 |
| fetch_failed 占位行 | 未涉及 | √ (P0-7) | 接受 |
| Money_Flow 公式 | 未涉及 | √ (P1-1) | 接受 |
| Auction 边界顺序 | 未涉及 | √ (P1-3) | 接受 |
| Anch? 单一权威 | 未涉及 | √ (P3-1) | 接受 |
| pure 循环边界 | 未涉及 | √ (P3-2) | 接受 |
| Strategy Inputs 分批 | 未涉及 | √ (P3-3) | 接受 |
| 删除策略话术 | 未涉及 | √ (P3-4) | 接受 |
| `pure --all-themes` 批量化 | 未涉及 | √ (P3-5) | follow-up issue |