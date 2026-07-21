# Mapper V5 — Architecture & Schema Design

Date: 2026-06-27
Status: **Final design — frozen contracts, ready for implementation planning**
Builds on: `2026-06-27-mapper-v4-unified-revision.md`

## 设计原则

> **Python 负责计算（Compute），Step 2 负责感知（Perception），Step 3 负责推理（Reasoning），Execution 负责格式化。**

V4-U 的核心缺陷：Step 2 用规则伪代码做 reasoning（Direction adjustment、RiskSeverity 分级、OverrideHint 应用），Step 3 反读 Step 2 已固化的结论。V5 用**四层信息处理契约 + 五条不可违反 invariants** 取代字段级边界，使 Pipeline 边界对演化稳定。

## 四层信息处理模型

```
Raw Observation
    │  Python fetch: 新闻 / K线 / 龙虎榜 / 资金流
    ▼
Computed Perception
    │  Step 2: 白名单 Minimal Inference
    │  (per-field Value + Confidence + Trace)
    ▼
Reasoning
    │  Step 3: Direction / Severity / Strategy / Override 应用
    │  默认消费 Computed Perception；例外有条件回查原始新闻
    ▼
Decision (Execution)
    │  格式化输出 strategy.md
    │  Buy/Stop/Target + 风险提示
    │  永不新增信息
```

每层只能消费上层产物，不允许反向跳层。Information Flow is **Unidirectional**。

---

## 五条架构契约（Invariants）

### Invariant 1 — Minimal Inference 白名单

Step 2 只能执行以下六类 minimal inference，**除此之外不得产生任何策略性判断**。

| # | 允许类型 | 例子 | 谁执行 |
|---|---------|------|--------|
| 1 | 数值压缩 | P/C/E 子分 → ThemeHeat 加权 | Python |
| 2 | 矩阵分类 | R×P cell 查表 → NewsImpact | LLM (matrix lookup) |
| 3 | 三元分类 | 新闻 → MajorEvent Polarity (Positive/Negative/Neutral) | LLM |
| 4 | Flag 分类 | risk_flags → RiskType (overbought/trend-weak/...) | LLM (查表) |
| 5 | Pattern 识别 | 多维状态模型每维独立打 state | LLM (per dimension) |
| 6 | 结构模式标签 | Anomaly ≤50 中文字 | LLM (自然语言) |

**Forbidden Reasoning（Step 2 严禁）**：

- ✗ Direction（base / final / 任何形态）
- ✗ RiskSeverity（1/2/3 评分）
- ✗ OverrideHint 应用
- ✗ 因果推断（"A 推动上涨"、"因为资金流入"）
- ✗ 趋势预测（"预计继续上涨"、"可能回调"）
- ✗ 买卖建议（buy/stop/target）
- ✗ 主题级 MajorEvent（行业景气只允许 ThemeHeat/NewsImpact 承载，MajorEvent 必须点名公司）

### Invariant 2 — Unidirectional Information Flow

Step 3 默认**只消费** Computed Perception dataset，不重新读取新闻全文。

**三类 Conditional Reread 触发条件**（每个 stock-per-condition 独立判定）：

| 触发条件 | 量化判据 | 允许回读范围 |
|---------|---------|-------------|
| Anomaly 存在 | `Anomaly != "—"` 且非空 | `NewsLink` 指针指向的**单条**新闻行 |
| 低 Confidence | 任一 `computed_perception.*.confidence < 60` | `NewsLink` 指针指向的单条新闻行 |
| 内部矛盾 | 下三条硬矛盾之一成立 | `NewsLink` 指针指向的单条 + cross-rank highlights 复核 |

**三条硬矛盾（机器可判）**：

```
1. theme_heat >= 80 AND tech_score.value < 40
   （主题高热但个股技术面极弱）

2. major_event.value = "Positive" AND composite.value < 50
   （有公司级正向事件但综合分极低）

3. auction_change_pct > +3% AND news_impact.value < 40
   （竞价强但新闻关联弱）
```

**严禁**：Step 3 扫全文 news.md 重新做主题映射。所有 reread 必须通过 `NewsLink` 指针单条查。

### Invariant 3 — Execution 永不新增信息

Execution（strategy.md 的格式化层）只能：
- 引用 Step 3 输出的 Direction / Strategy / Risk 评估
- 用固定模板排版 Buy/Stop/Target
- 列出风险提示

**严禁**： Execution 层独立判断、推理、补信息、覆盖 Step 3 结论。

### Invariant 4 — 白名单修改需 Regression Audit

Invariant 1 的白名单不是不可改，但**任何添加 / 删除白名单条目的改动必须通过 Regression Audit**：
- 回测此前 30 个交易日的 strategy 命中率
- 命中率不得显著下降（>2 个百分点视为下降）
- Audit 通过才合并到主线

防止 V6 演化时再次滑回 V4-U 的"Step 2 做 Reasoning"状态。

### Invariant 5 — Python 嵌套 Schema

Python 输出从 V4-U flat 25 字段升级为嵌套 JSON：`raw_observation` 与 `computed_perception` 两节，每字段带 `{value, confidence, trace}`。`mapper.md` 保持 markdown 表格但使用**前缀列名**承载嵌套（见 § Output Schemas）。

---

## Step 2 Perception Layer — 详细规范

### Theme Heat — 加权下沉 Python

LLM 给 P/C/E 子分（rubric 见 V4-U § Theme Heat sub-score rubric），Python 算 aggregation：

```
theme_heat = P × 0.40 + C × 0.15 + E × 0.25 + N_norm × 0.20
where N_norm = min(news_count / 20, 1) × 100
```

每字段独立 confidence：
- `theme_heat.P.confidence` — LLM 给（按 rubric 命中等级：90-100 满档、60-74 中等、<60 discard）
- `theme_heat.C.confidence` — 同上
- `theme_heat.E.confidence` — 同上
- `theme_heat.N.confidence` — Python 算：`min(news_count / 5, 1) × 100`（≥5 条 = 95+）
- `theme_heat.value.confidence` — `min(P, C, E, N confidences)`（最弱子分决定整体）

**PerceptionTrace 公式形式（机器可解析，必填）**：
```
ThemeHeat = P85×0.40 + C70×0.15 + E95×0.25 + N40×0.20 = 82.0
```

### NewsImpact — R×P 矩阵 + Confidence

LLM 选 R0-R4 × P0-P3 矩阵一格（V4-U § NewsImpact rubric 保留），并独立标 confidence：

| R/P | P3 | P2 | P1 | confidence（cell-level） |
|-----|----|----|----|------------------------|
| R4 | 95 | 85 | 70 | R4×P3=95；R4×P2=85；R4×P1=70 |
| R3 | 80 | 70 | 55 | 中档 |
| R2 | 65 | 55 | 40 | 中低档 |
| R1 | 45 | 35 | 25 | 边缘（confidence 默认偏低） |

**confidence 计算规则**：
```
confidence = base.cell_weight × 100
  R4×P3 = 95+, confidence = 95
  R3×P2 = 70,  confidence = 75
  R2×P1 = 40,  confidence = 55  (低于阈值，触发 reread)
  R1×P0 = 不允许（不应在 pool）
```

调整项（V4-U § NewsImpact adjustments 保留：多源+5、负向-20、MajorEvent=Negative cap=60）后 confidence 同步重算。

`PerceptionTrace`：`R4×P3=95; +5 multi-source; cap@60 Negative = 60`

### MajorEvent — Polarity 留 Step 2，Weight 留 Step 3

V5 撤回上轮"Detection + Impact 拆分"提议。Polarity 是分类（perception），Weight 是判断（reasoning）。

| 字段 | 谁给 | 取值 |
|------|------|------|
| `major_event.polarity` | Step 2 LLM | `Positive` / `Negative` / `Neutral` |
| `major_event.confidence` | Step 2 LLM | 0-100（默认 Neutral=90，P/N 由 evidence 强度决定） |
| `major_event.NewsLink` | Step 2 | 最短指针 `flash#3` |
| `major_event.evidence` | Step 2 LLM | ≤30 字公司级事件描述（"财政部降印花税"、"董事长被立案"） |
| **MajorEvent 权重 + 1 级 Direction 调整** | Step 3 | Step 2 不给 |

**Rubric 严格度**（继承 V4-U）：行业景气 / TSMC 涨价 / 论坛开幕 → `Neutral`。Default `Neutral`。

### RiskType 分类留 Step 2，RiskSeverity 评定移 Step 3

V5 RiskSeverity 不再 Step 2 给 1/2/3 干值。Step 2 只输出 RiskType 分类（机器可判表，per flag）：

| risk_flag | RiskType |
|-----------|----------|
| RSI>75 | `overbought` |
| RSI<30 | `oversold_opportunity` |
| MA双熊 | `trend_weak` |
| 炸板 | `broken_board` |
| Auc<-5% | `auction_anomaly` |

多 flag 取**所有触发 flag 的 set**（不是 V4-U 的"最高 severity 单一映射"），Step 3 看全集后综合评 RiskSeverity。

`risk_type` 字段 value 为逗号分隔 list，confidence=100（机器查表，固定）。

### Pattern — 多维状态模型（非正交，每维独立）

每只股在以下 5 个维度各自独立打 state + confidence：

| Dimension | Possible States | 判据（rubric 简版） |
|-----------|----------------|---------------------|
| `heat` | `RISING` / `FALLING` / `STABLE` | theme_heat 今日 vs 昨日（需要历史数据；首日默认 STABLE） |
| `leader` | `STABLE` / `DIVERGENCE` / `ABSENT` | RoleTags 含 Anchor 且 board_streak ≥ 1 → STABLE；Anchor 但断板 → DIVERGENCE；无 Anchor → ABSENT |
| `auction` | `LEADING` / `LAGGING` / `MATCH` / `NEUTRAL` | abs(auc_chg) > 1% AND 同向 theme_heat → LEADING；反向 > 1% → LAGGING；< 0.5% → NEUTRAL；其余 MATCH |
| `rotation` | `PRIMARY` / `SECONDARY` / `TERTIARY` / `NONE` | MultiTheme + 板块涨停簇中 → PRIMARY；纯度 ≥ 0.7 → SECONDARY；其他可入池 → TERTIARY；不达主题纯度 → NONE |
| `volume` | `SURGE` / `NORMAL` / `DRY` | amount/10000 ≥ 8 亿 → SURGE；3-8 亿 → NORMAL；< 3 亿 → DRY（注意 hard filter 边界） |

**非正交允许**：同一只股可同时 `heat=RISING + leader=DIVERGENCE` — 这正是"主升中龙头退潮"信号。

`pattern.*.confidence`：LLM 按 rubric 命中清晰度标 0-100。无历史的 `heat=STABLE` confidence 默认 50（触发 reread 但不强制）。

**Pattern 字段不出现在 V5 mapper.md 表中**（避免行宽爆炸），作为 `anomaly` 字段的 evidence 基础，放在 `theme_stocks.md` enrichment 表中。

### Anomaly — 自然语言 ≤50 字

V4-U 30 字 → V5 50 字。允许：
- 模式标签：`三日缩量首板 + 板块龙头启动`
- 跨主题：`跨半导体+AI算力，板块内涨停簇形成`
- 事件形态：`涨停开板二次封，封单递减`

禁止：
- 买卖建议 / 价格目标 / 因果解释
- `> 50` 字

**必需情形**：
- `cross_rank_highlights` 入池
- LHB 注入且净买入 > 0
- `board_streak ≥ 2 但 composite < 70`
- 任一 Pattern 维度 state 为 non-default（如 `leader=DIVERGENCE`、`volume=DRY`）
- LLM 判定 RiskType 单独不足以描述 setup

否则 `—`。

### Computed Perception 字段全清单

```
computed_perception:
  theme_heat                { value, confidence, trace, sub: P/C/E/N {value,confidence} }
  news_impact               { value, confidence, trace, R, P, NewsLink }
  major_event               { polarity, confidence, evidence, NewsLink }
  risk_type                 { value (list), confidence }
  pattern.heat              { state, confidence }
  pattern.leader            { state, confidence }
  pattern.auction           { state, confidence }
  pattern.rotation          { state, confidence }
  pattern.volume            { state, confidence }
  auction_score             { value, confidence, trace }
  tech_score                { value, confidence } （置信 = present_factor_count/6）
  composite                 { value, confidence, trace }   ← V5 新下沉 Python
  anomaly                   { text, confidence }           ← 自然语言 ≤50 字
```

注：`composite` 从 V4-U 的 Step 2 LLM 加权**下沉 Python**。Python 接收 Step 2 LLM 输出的各 computed_perception value + confidence，按固定权重聚合：

```
composite_value = theme_heat.value × 0.30
              + news_impact.value × 0.20
              + auction_score.value × 0.20
              + tech_score.value × 0.20
              + money_flow.value × 0.10

composite_confidence = weighted_avg of sub-confidences (same weights)
composite_trace = "T{th}×0.3+N{ni}×0.2+A{au}×0.2+Tech{ts}×0.2+MF{mf}×0.1={comp}"
```

---

## Step 3 Reasoning Layer — 详细规范

### Step 3 默认输入

- `mapper.md`（Step 2 dataset，含所有 computed_perception 字段）
- `memory/RULES.md`
- `news.md`（**仅做 NewsLink 单条回查用，不做主题映射**）

### Step 3 必须输出（strategy.md）

| 字段 | 类型 | 来源 |
|------|------|------|
| `Direction` | enum | Step 3 推理（参考 Composite + RiskType + MajorEvent + Regime） |
| `RiskSeverity` | int 1/2/3 | Step 3 评定（依赖 RegimeHint + RiskType set） |
| `RegimeHint` | enum | Step 3 综合（上证竞价 + 科创50 + 主题 heat） |
| `OverrideHintApplied` | list of tokens | Step 3 从 RULES.md 调用并应用 |
| `Strategy` | struct | Buy/Stop/Target + 仓位建议 |
| `ReasoningTrace` | structured | 强制 audit 痕迹 |
| `PerceptionOverride` | list | Step 3 异议 Step 2 perception 时记录 |
| `ConditionalRereadTriggered` | list | 哪条触发条件被满足及其回查结果 |

### Conditional Reread 触发流程

```
FOR each stock in Candidate Pool:
  IF anomaly != "—":
    reread news_link → single news row
    append to ConditionalRereadTriggered
  ELIF ANY computed_perception.*.confidence < 60:
    reread news_link → single news row
    append
  ELIF ANY hard_contradiction(3 rules above) = true:
    reread news_link + cross_rank_highlights
    append
  ELSE:
    no reread; consume perception directly
```

每次 reread 必须在 `ConditionalRereadTriggered` 列写明触发条件 + 回查结果（≤30 字），便于审计。

### Perception Override 机制

Step 3 可对 Step 2 的 `computed_perception` 字段提出 override，但：

**可 override 字段清单**（白名单）：
- `news_impact.value`
- `major_event.polarity`
- `pattern.heat.state` / `pattern.leader.state` / `pattern.auction.state` / `pattern.rotation.state` / `pattern.volume.state`
- `anomaly.text`

**不可 override 字段**：
- `theme_heat`（Python 算，无异议空间）
- `composite`（Python 算）
- `tech_score`（Python 算）
- `risk_type`（机器查表）
- `raw_observation.*`（Python 取值）

**Override 输出格式**（structured）：

```markdown
| Field | Old | New | Reason | NewConfidence |
|-------|-----|-----|--------|---------------|
| news_impact.value | 70 | 95 | reread flash#3 发现公司直接被点名于标题，原 R2 误判应 R4 | 90 |
```

**Override 率统计**：
- 每日累计：`override_count / candidate_pool_size`
- 滚动 30 日均值 ≤ 5% → Step 2 perception 健康
- 滚动 30 日均值 > 15% → 触发 V6 perception rubric 重审
- 单字段 override 率 > 30% → 该字段 rubric 失效，强制 V6 修订

**T+1 Verification**：
- T+1 收盘后，验证当日 T 时 override 字段对应的实际市场表现
- 若 override 方向与实际市场表现一致 → override 正确
- 若不一致 → Step 3 越权，记入 30 日 override 命中率
- 命中率 < 50% → 抑制 Override 权限（Step 3 该字段不可再 override，需人工介入）

### ReasoningTrace 强制结构化输出

```
ReasoningTrace:
  DirectionPath:
    composite: 76.5
    composite_confidence: 78
    risk_type_set: [overbought]
    risk_severity: 2
    regime_hint: strong-sector
    major_event: Neutral
    Direction inference: bullish-with-caution (≠ V4-U DirectionFinal 自动算法)
    Direction final: bullish
    
  RuleApplications:
    - token: R37
      rule: "strong-market RSI overbought exemption"
      applied: True
      effect: "do not exclude for RSI; retain 4★"
    - token: R35-v3
      rule: "continuation probe eligible"
      applied: True
      effect: "widen stop for streak"
```

**ReasoningTrace 永远输出**，即使是 default 推理路径也要记。这是 V5 audit 必需。

### RegimeHint 评定（Step 3 独占）

V4-U 把 RegimeHint 放 Step 2，V5 移到 Step 3：

| RegimeHint | 条件 |
|-----------|------|
| `panic` | 上证竞价 < -1.5% |
| `weak` | -1.5% ~ -0.5% |
| `neutral` | ±0.5% |
| `strong-sector` | neutral index BUT dominant theme heat ≥ 85 OR 科创50 > +2% |

Step 3 读 mapper.md 的 dominant_themes + 自查实时指数 → 评定。

---

## Python 嵌套 Schema（V5 Invariant 5）

### `fetch_pool_indicators.py` 输出结构

```json
{
  "code": "sh603986",
  "fetch_failed": false,
  "raw_observation": {
    "price":             {"value": 94.70, "source": "auction"},
    "close":             {"value": 94.70},
    "turnover":          {"value": 7.61},
    "change_pct":        {"value": 3.21},
    "amount":            {"value": 85000, "unit": "万元"},
    "rsi":               {"value": 72.0, "confidence": 100},
    "macd":              {"value": 1.5},
    "macdh":             {"value": 1.5, "prev": 1.2, "accelerating": true},
    "ma20":              {"value": 79.42},
    "ma50":              {"value": 62.50},
    "boll_ub":           {"value": 94.70},
    "boll_lb":           {"value": 64.14},
    "atr":               {"value": 6.14},
    "high20":            {"value": 94.70},
    "low20":             {"value": 65.72},
    "atr_pct":           {"value": 6.50},
    "percent_b":         {"value": 0.82},
    "board_streak":      {"value": 2},
    "seal_quality":      {"value": "封死"},
    "limit_up_freq":     {"value": 3},
    "auction_change_pct":{"value": 3.5},
    "auction_amount":    {"value": 8500, "unit": "万元"},
    "auction_turnover":  {"value": 0.42, "unit": "%"}
  },
  "computed_perception": {
    "theme_heat": {
      "value": 91.0, "confidence": 88,
      "trace": "P85×0.40+C70×0.15+E95×0.25+N40×0.20=82.0",
      "subscores": {
        "P": {"value": 85, "confidence": 85},
        "C": {"value": 70, "confidence": 70},
        "E": {"value": 95, "confidence": 95},
        "N": {"value": 40, "confidence": 80}
      }
    },
    "news_impact": {
      "value": 88, "confidence": 90,
      "R": "R4", "P": "P3", "NewsLink": "flash#2",
      "trace": "R4×P3=95; +5 multi-source; cap@60 N/A = 95"
    },
    "major_event": {
      "polarity": "Neutral", "confidence": 90,
      "evidence": "—", "NewsLink": "—"
    },
    "risk_type": {
      "value": ["overbought"], "confidence": 100
    },
    "pattern": {
      "heat":      {"state": "RISING",   "confidence": 80},
      "leader":    {"state": "STABLE",   "confidence": 85},
      "auction":   {"state": "LEADING",  "confidence": 90},
      "rotation":  {"state": "PRIMARY",  "confidence": 75},
      "volume":    {"state": "SURGE",    "confidence": 95}
    },
    "auction_score": {
      "value": 92.5, "confidence": 88,
      "trace": "AucChg100×0.40+AucAmt75×0.35+AucTO100×0.25=92.5"
    },
    "tech_score": {
      "value": 78.5, "confidence": 100,
      "trace": "MA100×0.22+MACD100×0.19+RSI40×0.13+Liq100×0.22+BB80×0.16+ATR60×0.09=78.5"
    },
    "composite": {
      "value": 86.7, "confidence": 87,
      "trace": "T91×0.30+N88×0.20+A92.5×0.20+Tech78.5×0.20+MF50×0.10=86.7"
    },
    "money_flow": {
      "value": 50, "confidence": 30,
      "stale": true,
      "trace": "MoneyFlowStale (cookie 失效) → 50 neutral"
    },
    "anomaly": {
      "text": "缩量首板，板块龙头启动", "confidence": 75
    }
  }
}
```

### `fetch_failed` 占位行（V5 扩展）

```json
{
  "code": "sh688XXX",
  "fetch_failed": true,
  "raw_observation": {},
  "computed_perception": {
    "tech_score":        {"value": null, "confidence": 0, "trace": "fetch_failed"},
    "risk_type":         {"value": [], "confidence": 0},
    "composite":         {"value": null, "confidence": 0},
    "anomaly":           {"text": "indicators_fetch_failed", "confidence": 0}
  }
}
```

V5 规定：**fetch_failed 股不进 Candidate Pool，进 Observation Pool**，标 `ExclusionSource=indicators-fetch-failed`。Step 3 不得包含进 Strategy Inputs；可在 Watchlist 单独列出，不参与 Direction 决策。

### Confidence 计算规则汇总

| 字段 | Confidence 公式 | 谁算 |
|------|----------------|------|
| `theme_heat.subscores.P/C/E` | LLM 按 rubric 命中等级：90/75/55 | LLM |
| `theme_heat.subscores.N` | `min(news_count/5, 1) × 100` | Python |
| `theme_heat.value` | `min(P, C, E, N confidences)` | Python |
| `news_impact.value` | matrix cell weight × 100 ± adjustments | LLM (matrix-driven) |
| `major_event.polarity` | Default Neutral=90；P/N by evidence strength (headline=90, body=70) | LLM |
| `risk_type` | 100（机器查表，固定） | Python |
| `pattern.*.state` | LLM 按 rubric 命中清晰度 0-100 | LLM |
| `auction_score.value` | `min(aucChg, aucAmt, aucTO confidences)` | Python |
| `tech_score.value` | `present_factor_count / 6 × 100` | Python |
| `composite.value` | `weighted_avg(sub-confidences, same 0.30/0.20/0.20/0.20/0.10 weights)` | Python |
| `money_flow.value` | 100 if fresh, 30 if stale + MoneyFlowStale flag | Python |

### Confidence 校准机制（V5 上线后 1-2 周必做）

- 第一周：统计所有 `computed_perception` 字段 confidence 分布
- 若某字段 confidence 长期 > 85（全员自信），强制阈值上调 +10
- 若某字段 confidence 与 T+1 实际市场表现命中率不匹配，Phase 5 companion 阶段校准 rubric
- T+1 命中率 = (Composite 高分股实际涨幅均值) / (预期上涨比例)，置信度 → 实际表现的散点图分析

---

## Output Schemas

### `theme_stocks.md`（Step 2 中间产物，V5 加 Pattern 列）

```markdown
## Stock Pool (After Technical Enrichment)

| # | Code | Name | Best Score | Source Themes | Auc% | AucAmt | 情绪 | 连板 | 封板 | Tech | RSI | %B | MA50 | 换手% | Risk? | P.Heat | P.Leader | P.Auct | P.Rot | P.Vol | Anomaly |
|---|------|------|-----------|---------------|------|--------|------|------|------|------|-----|----|----------|-------|-------|--------|----------|--------|-------|-------|---------|
| 1 | sh603986 | 兆易创新 | 92.0 | 半导体 | +3.5 | 8500万 | 85 | 2连板 | 封死 | 78.5 | 72.0 | 0.85 | >ma50 | 7.61% | RSI>75 | RISING | STABLE | LEADING | PRIMARY | SURGE | 缩量首板板块龙头启动 |
```

### `mapper.md`（单层前缀列名方案）

单层 markdown 表，避免嵌套子表导致行宽爆炸。前缀列名承载嵌套：

```markdown
## Candidate Pool

| Code | Name | comp.value | comp.conf | th_heat.value | th_heat.conf | news_imp.value | news_imp.conf | maj_ev.pol | maj_ev.conf | risk_type.value | pattern.heat | pattern.leader | pattern.auct | pattern.rot | pattern.vol | auc.value | tech.value | tech.conf | anomaly | NewsLink |
|------|------|-----------|-----------|---------------|--------------|---------------|---------------|------------|-------------|-----------------|--------------|----------------|--------------|-------------|------------|-----------|-----------|-----------|---------|----------|
| sh603986 | 兆易创新 | 86.7 | 87 | 91.0 | 88 | 88 | 90 | Neutral | 90 | overbought | RISING | STABLE | LEADING | PRIMARY | SURGE | 92.5 | 78.5 | 100 | 缩量首板板块龙头启动 | flash#2 |
```

**保留 V4-U 的 7 sections**，但 Section 3 Candidate Pool 列改为上述前缀列。其余 section 大致保持 V4-U 结构（HeatTrace 在 Section 2、PriceSource 在 Section 4、CompositeTrace/PerceptionTrace 在 Section 5、Anomaly 在 Section 6、ExclusionSource 在 Section 7）。

### `mapper.md` — 完整 7 Sections（V5）

1. **Market State**（V4-U 不变，仍含 BoardPolicy）
2. **Theme Ranking** — V4-U HeatTrace + 子分 confidence
3. **Candidate Pool** — V5 前缀列名表，无 Direction（移 Step 3）
4. **Strategy Inputs** — V4-U 不变 + PriceSource
5. **Score Trace**（V5 增强）— `CompositeTrace + PerceptionTrace`，机器可解析格式
6. **Observation Pool** — V4-U + `fetch_failed` 单独分类
7. **Excluded Stocks** — V4-U ExclusionSource（含 `indicators-fetch-failed`）

### `strategy.md`（Step 3 输出，V5 新结构）

```markdown
## Strategy

| Code | Name | Direction | RiskSeverity | RegimeHint | OverrideHintApplied | Buy | Stop | Target | Position |
|------|------|-----------|--------------|------------|---------------------|-----|------|--------|----------|
| sh603986 | 兆易创新 | bullish | 2 | strong-sector | R37,R35-v3 | 94.70 | 88.50 | 104.20 | 4★ |
```

```markdown
## Reasoning Trace

| Code | DirectionPath | RuleApplications | PerceptionOverride | RereadTriggered |
|------|----------------|------------------|---------------------|-----------------|
| sh603986 | comp86.7→bullish; risk_type=overbought sev2; regime=strong; maj_ev=Neutral; final=bullish | R37:apply,retain 4★; R35-v3:apply,widen stop | — | — |
```

```markdown
## Watchlist (Optional — 不参与 Direction 决策)

| Code | Name | Reason |
|------|------|--------|
| sh688XXX | 某股 | indicators_fetch_failed — 次日复核 |
```

---

## Migration: V4-U → V5

### Step 2 SKILL.md 改动

| V4-U 字段 / 章节 | V5 处置 |
|-----------------|---------|
| § Direction（Step A/B/C 全章节） | **删除整章** |
| `DirectionBase` / `DirectionFinal` 列 | 移除（Section 3 表） |
| `RiskSeverity` 列 | 移除（归 Step 3） |
| `OverrideHint` 占位 token 表 | 移除（归 Step 3 真实应用） |
| `RegimeHint`（Section 1） | 移除（归 Step 3，仍在 Market State 显示但由 Step 3 生成） |
| `Composite` 计算位置 | 从 Step 2 LLM 加权 → Python 加权（fetch_pool_indicators 扩展） |
| `ThemeHeat` 加权 | 从 Step 2 LLM 公式 → Python 实现（fetch_pool_indicators 扩展） |
| `Pattern.*` 5 维度 | **新增**，theme_stocks.md enrichment |
| `Anomaly` 30 字 → 50 字 | 放宽 |
| `PerceptionTrace` 公式 trail | **新增**，Section 5 Score Trace 扩 |
| `Confidence` 字段 | **每个 computed_perception 字段必带** |
| Invariant 1 Forbidden Reasoning 清单 | **新增章节**写进 SKILL 头部 |
| Invariant 2 Conditional Reread 触发条件 + 3 硬矛盾 | **新增章节** |

### Step 3 SKILL.md 改动

- 新增 § Direction 评定（Composite + RiskType 综合）
- 新增 § RiskSeverity 评定（依赖 RegimeHint + RiskType set）
- 新增 § OverrideHint 应用（真正读 RULES.md，V4-U 是占位）
- 新增 § RegimeHint 评定
- 新增 § ReasoningTrace 强制结构化输出
- 新增 § PerceptionOverride 机制（白名单字段 + T+1 验证）
- 新增 § Conditional Reread（3 触发条件 + 3 硬矛盾）

### Python `fetch_pool_indicators.py` 改动

- 输出从 flat 25 字段 → 嵌套 `raw_observation / computed_perception` 两节
- 接收 LLM 输入子分（P/C/E、NewsImpact cell、Pattern states），Python 算加权与 confidence 聚合
- 新增 `composite` Python 计算
- 字段级 `confidence` 计算下沉
- `PerceptionTrace` 公式生成

### `memory/RULES.md` 改动

- OverrideHint token 实体定义（R37 / R61 / R39-v3 / R35-v3 / R73 / R74）
- 每个 token 明确：trigger condition、Step 3 action、regime gating

### Execution 层（strategy.md 格式化）

- 保留 V4-U 的结构化输出契约
- 不新增 reasoning；纯格式化 Step 3 的 Direction/Strategy/Risk 评估结果
- 风险提示和仓位建议由 Step 3 给，Execution 仅排版

---

## Backward Compatibility

V5 比 V4-U 改动大，不向后兼容。建议：

- V4-U mapper.md 仍能被 Step 3 V5 兼容模式接受：
  - 缺 `Direction` 列 → Step 3 自行推理（这正是 V5 默认行为）
  - 缺 `RiskSeverity` → Step 3 自行评定
  - 缺 `Confidence` → 视为 confidence=80（默认信任）
- V5 mapper.md 不含 Step 2 给的 Direction → Step 3 V4-U 模式可能找不到字段而报错

**实施路径**：Day 1 上线 V5 Step 2（含新 mapper.md 结构），同步上线 V5 Step 3；不接受 V4-U mapper 输入。

---

## Open Questions（V5 收尾，Phase 6 companion 阶段定）

1. **Pattern 5 维度初始 rubric 是否够覆盖日常情形**？后续 1-2 周运营后评估是否需要 `breakout` 维度（NEW / FOLLOW_THROUGH / FAILED）。
2. **Confidence 校准起点**：上线第一周所有 `computed_perception` 字段 confidence 长期 > 85 是否立即触发阈值上调 +10？建议每日跑一次 calibration 脚本统计。
3. **Override T+1 验证机制落地形式**：人工 vs 自动？建议人工审核 30 日试点，再自动化。
4. **Regression Audit 30 日窗口**：交易命中率口径（T+1 涨幅 ≥ 3% 算命中？还是 ≥ 综合分均值？）。
5. **Multi-stock 协同 Reasoning**：V5 Step 3 是否允许跨股 reasoning（如"主题内 3 只龙头同时炸板 → 该主题降级"）？建议 V5 单股 reasoning 为主，跨股 reasoning 进 V6 issue。

---

## Summary

V5 通过四层信息处理模型 + 五条 invariants，将 V4-U 静态字段级边界升级为**信息生命周期契约**：

1. **白名单边界**（Invariant 1）—— Step 2 永不越界
2. **单向信息流**（Invariant 2）—— Step 3 不绕过 Step 2
3. **Execution 无新增**（Invariant 3）—— 输出层不补信息
4. **白名单修改受 Regression 约束**（Invariant 4）—— 防 V6 滑回 V4-U
5. **Python 嵌套 Schema**（Invariant 5）—— 数据载体承载 Value+Confidence+Trace

V5 Step 2 = Perception（perception 内含白名单 minimal inference + per-field confidence + perception trace）
V5 Step 3 = Reasoning（Direction/Severity/Strategy/Override + ReasoningTrace + Conditional Reread + Override Audit）
V5 Execution = Formatting（永不新增信息）

**关键新增机制**：
- Pattern 多维状态模型（非正交、5 维度、每维独立 confidence）
- PerceptionOverride + Override 率统计 + T+1 验证（形成 Step 2 rubric 持续改进闭环）
- Conditional Reread + 3 硬矛盾（防 Step 3 自重感知）
- Confidence 双向作用：Step 3 区分可信 perception vs 需谨慎 perception；Step 2 rubric 失效时通过低 confidence 自动触发 Step 3 回查

V5 把 LLM 真正的推理能力集中在 Step 3，Step 2 只承担 Pattern Recognition / Classification / Detection 这类 LLM 强项但非推理任务。Pipeline 通过 Confidence + Override 反馈循环**可自我校准演化**，不再依赖每轮 V 升级手工划边界。