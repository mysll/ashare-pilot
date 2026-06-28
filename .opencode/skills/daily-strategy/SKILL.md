---
name: daily-strategy
description: Generate daily trading strategy from V5 mapper.md. Used as Step 3 of daily-market-analysis pipeline. Step 3 is the REASONING layer — consumes Step 2 Computed Perception, produces Direction / RiskSeverity / OverrideHint application / Buy/Stop/Target via structured ReasoningTrace.
---

# Daily Strategy Generation (V5)

Loaded by trading-strategist subagent when dispatched for pipeline strategy generation.

## V5 架构角色

```
Compute (Python)
    ↓
Perception (Step 2 — mapper.md)
    ↓
Reasoning (Step 3 — this skill ← 你在这里)
    ↓
Decision (Execution — strategy.md formatting)
```

Step 3 不只是“在 Direction 内交易” — Step 3 **是 Direction 的产生者**。V5 把 Direction / RiskSeverity / OverrideHint 应用从 Step 2 拿回 Step 3。V4-U 越权由 Step 2 算 Direction 的设计在 V5 已废止。

---

## V5 Invariants（Step 3 必须遵守）

| Invariant | Step 3 含义 |
|-----------|------------|
| 1. Minimal Inference 白名单 | Step 3 不越界做 perception — 不重做主题匹配、不重算 tech_score、不重映射 R×P cell |
| 2. Unidirectional Information Flow | **默认不重读 news.md** — 仅在 3 类 Conditional Reread 触发时回查 `NewsLink` 单条 |
| 3. Execution 永不新增信息 | strategy.md 格式化层严格消费 Step 3 Reasoning 输出；不自行加仓 / 改 stop |
| 4. 白名单修改需 Regression Audit | V5+ 修订白名单须 30 日命中回测 — Phase 5 companion 阶段绑定 |
| 5. Python 嵌套 Schema | Step 3 读 `comp.value` / `comp.conf` / `tech.value` / `tech.conf` 等前缀列 |

---

## Workflow

```
Inputs:
  Date:       provided in prompt (YYYY-MM-DD)
  Mapper:     predict/{date}/mapper.md   (Step 2 V5 output, 7 sections)
  Rules:      memory/RULES.md            (OverrideHint token 真实定义)
  News:       predict/{date}/news.md     (仅 for Conditional Reread 单条回查)
```

1. Read `mapper.md` **Market State** — DominantThemes, BoardPolicy, FinancingFlow, RiskFlags
2. Read `mapper.md` **Candidate Pool** — V5 prefix columns（`comp.value/conf`, `tech.value/conf`, `th_heat.value/conf`, `news_imp.value/conf`, `maj_ev.pol`, `risk_type.value`, `pattern.*`, `auc.value`, `anomaly`, `NewsLink`）
3. Read `mapper.md` **Strategy Inputs** — Price, PriceSource, MA20, ATR, ATR%, High20, Low20（**authoritative source**）
4. Fetch market indices via `fetch_stock.py sh000001,sz399001,sh000688 --json` — 评 RegimeHint
5. Read `memory/RULES.md` — 加载 OverrideHint token 真实定义
6. **对每个 Candidate Pool stock 执行 Reasoning Flow**（见 § Reasoning Flow）
7. Generate `predict/{date}/strategy.md` (含 **ReasoningTrace** + **Market Context** + 推荐列表)

---

## Reasoning Flow (per stock)

V5 Step 3 对每个 Candidate Pool stock 按 4 步推理：

### Step 3-A — Conditional Reread 判定（先于此处）

默认**不重读** `news.md`。检查三类触发条件：

| 触发条件 | 判据 | 回读范围 |
|---------|------|---------|
| Anomaly 存在 | row.anomaly != "—" 且非空 | `NewsLink` 指向的单条新闻行 |
| 低 Confidence | 任一 `comp.conf`, `tech.conf`, `th_heat.conf`, `news_imp.conf` < 60 | `NewsLink` 指向的单条新闻行 |
| 硬矛盾 | 下三条之一成立 | `NewsLink` 单条 + cross_rank highlights 复核 |

**三条 Hard Contradictions（机器可判）**：
1. `th_heat.value ≥ 80 AND tech.value < 40`（主题高热但个股技术面极弱）
2. `maj_ev.pol = "Positive" AND comp.value < 50`（公司利好但综合分极低）
3. `auc_change_pct > +3% AND news_imp.value < 40`（竞价强但新闻关联弱）

**严禁**：扫全文 news.md 重新做主题映射（违反 Invariant 2）。

若任一触发：回读 `NewsLink` 指向的单条新闻行（仅此一条），并在 `ReasoningTrace.RereadTriggered` 写明：触发条件 / 回读结果（≤30 字）。

### Step 3-B — RegimeHint 评定（per market 一次）

读 fetch_stock.py 返回的上证 / 科创 50：

| RegimeHint | 条件 |
|-----------|------|
| `panic` | 上证竞价 < -1.5% |
| `weak` | -1.5% ~ -0.5% |
| `neutral` | ±0.5% |
| `strong-sector` | neutral index BUT dominant theme heat ≥ 85 OR 科创50 > +2% |

RegimeHint 是 Step 3 独有的 reasoning 输出（不在 mapper.md 中）。

### Step 3-C — Direction 推理（per stock）

V5 Step 3 **必须自算 Direction**（V4-U 的 DirectionBase/Final 已删除）：

```
1. 读 comp.value (Python 已给)
   └─ 使用 DirectionBase 阈值表：
      >= 70 → bullish 倾向
      55-69 → neutral-bull 倾向
      45-54 → neutral 倾向
      < 45 → bearish 倾向

2. 读 comp.conf
   └─ 若 < 60: Direction ConfidenceFlag=True (Consider warnings)
   └─ 若 < 30: Direction 维持倾向 但加 "low_confidence" tag

3. 读 risk_type.value (list, e.g., ["overbought"])
   └─ Step 3 评 RiskSeverity (见 Step 3-D)

4. 读 maj_ev.pol
   └─ Positive: Direction +1 level (cap bullish)
   └─ Negative: Direction -1 level (cap bearish)
   └─ Neutral: no shift

5. 评 RiskSeverity (Step 3-D)
   └─ RiskSeverity = 3 AND RegimeHint not strong-sector → cap at neutral-bull
   └─ RiskSeverity = 2 → no auto cap; 记 OverrideHint
   └─ RiskSeverity = 1 → no cap; 记 OverrideHint

6. 应用 OverrideHint tokens (Step 3-E)
   └─ token 应用后调整 Direction 或仅在 ReasoningTrace 记录 effect

7. Clamp to [bearish .. bullish]
   └─ 最终 Direction ∈ {bullish, neutral-bull, neutral, bearish}

8. DirectionPivot 检查（见下）
```

**DirectionBase 阈值表**（V5 Step 3 参考，非硬约束）：

| comp.value | 倾向 (DirectionBase) |
|-----------|---------------------|
| >= 70 | bullish |
| 55-69 | neutral-bull |
| 45-54 | neutral |
| < 45 | bearish |

阈值是参考框架；Step 3 据完整 Context（confidence + pattern + risk_type + Regime + MajorEvent）综合判定 Direction final。允许偏离 DirectionBase 但必须写理由（ReasoningTrace）。

**DirectionPivot**（V5 新增）：如果 `anomaly` 非空且 LLM 判定 anomaly 暗示 Base 阈值不够（如"龙头断板但板块未退潮" → 即使 comp 在 50-55 中性区，仍可升 Direction 一档 bullish）— 必须在 ReasoningTrace 写 "DirectionPivot: anomaly-driven +1 level; reason=..."。

### Step 3-D — RiskSeverity 评定

读 `risk_type.value` (list) + RegimeHint 评 severity：

| RiskType + Regime | Severity | 理由 |
|-------------------|:--------:|------|
| `trend_weak` + (weak/panic/neutral) | **3** | 结构性弱势，硬压 |
| `trend_weak` + strong-sector | **2** | 大盘强势下 trend_weak 降级 |
| `overbought` + strong-sector | **1** | R37: 强市场 RSI 超买豁免 — 仅 informational |
| `overbought` + (weak/neutral) | **2** | caution |
| `oversold_opportunity` + any | **1** | R61: 深超卖是机会 hint, 非 risk |
| `broken_board` + strong-sector | **2** | caution; R39/R35 watch |
| `broken_board` + weak | **3** | 弱市场炸板危险 |
| `auction_anomaly` + any | **2** | caution |
| 多 flag 并存 | 取 max(severity) | 但 ReasoningTrace 必须逐 flag 记录 |

**Severity 应用到 Direction（Step 3-C 第 5 步）**：
- Severity 3: cap Direction at `neutral-bull`（若 RegimeHint != strong-sector）
- Severity 2: no cap; OverrideHint 记录
- Severity 1: no cap; OverrideHint 记录

### Step 3-E — OverrideHint Token 真实应用

V5 Step 3 不再仅作 "占位"。每个 token 在 `memory/RULES.md` 必须有真实定义。Step 3 决定是否 apply 以及 apply 后 effect：

| Token | Trigger Condition | Step 3 Action |
|-------|------------------|----------------|
| `R37` | RiskType=overbought AND th_heat.value ≥ 85 | 不因 RSI 排除；保留 4★；MA20 buy zone 不变 |
| `R61` | RiskType=oversold_opportunity | 分级 entry；不当日建仓；可分 2-3 笔 |
| `R39-v3` | RiskType=broken_board AND th_heat.value ≥ 80 | watch 模式；缩仓 1-2 星；放宽止损 |
| `R35-v3` | sentiment ≥ 85 AND board_streak ≥ 1 | 连续探测 eligible；tauten stop is allowed |
| `R73` | RiskType=trend_weak AND RegimeHint=weak | MA20 buffer / 更宽止损；仓位 ×0.6 |
| `R74` | RiskType=trend_weak AND RegimeHint=strong-sector | MA 单维度不降级；保留评级 |

**Token 未在 RULES.md 定义时**：ReasoningTrace 记 `OverrideHint xxx_pending_RULES_md_definition`，沿用 V5 默认 severity rule。

---

## PerceptionOverride Mechanism (V5 新增)

Step 3 在严格条件下可异议 Step 2 perception 字段。**非默认行为，必须有 audit**。

### 可 override 字段白名单

- `news_imp.value`, `news_imp.conf`
- `maj_ev.pol`
- `pattern.heat.state`, `pattern.leader.state`, `pattern.auction.state`, `pattern.rotation.state`, `pattern.volume.state`
- `anomaly`

**不可 override 字段**：

- `th_heat`, `comp`（Python 算）
- `tech_score`（Python 算）
- `risk_type`（机器查表）
- 任何 `raw_observation.*`（Python 取值）

### Override 触发条件

仅允许在 Perception 不一致 + Conditional Reread 触发了之后：
- Anomaly reread 后发现新闻与 step 2 Perception 不一致
- 硬矛盾 reread 后 Step 3 认定 Step 2 perception 误判

**严重 White-list 违规**：不可因 "Step 3 自己觉得" 没 reread 触发就 override。

### Override 输出格式（在 ReasoningTrace 中）

```markdown
| Field | Old | New | Reason | NewConfidence |
|-------|-----|-----|--------|---------------|
| news_imp.value | 70 | 95 | reread flash#3 发现公司直接被点名于标题，原 R2 误判应 R4 | 90 |
```

### Override 率监控

- 单日 override / candidate_pool_size ≥ 15% → trigger V6 perception rubric 复审
- 单字段 override 率滚动 30 日 > 30% → 该字段 rubric 失效（Phase 5 companion 阶段绑定）
- T+1 验证：T+1 收盘后验 override 方向 vs 实际市场表现；命中率 < 50% 则抑制该字段 override 权限

---

## Market Context Fetch

Fetch 3 index quotes in a single batch call (fast, ~3s):

```bash
python .opencode/skills/stock-analysis/scripts/fetch_stock.py sh000001,sz399001,sh000688 --json
```

| Index | Code | Purpose |
|-------|------|---------|
| 上证指数 | sh000001 | 大盘方向（全市场情绪）/ RegimeHint 主输入 |
| 深证成指 | sz399001 | 深圳市场水位 |
| 科创50 | sh000688 | 科技权重指标（结构性强度 / strong-sector 判定关键） |

Compute signals:

| Signal | Calculation | Interpretation |
|--------|-------------|----------------|
| **大盘方向** | sh000001.percent | >+0.5%=强, ±0.5%=震荡, <-0.5%=弱, <-1.5%=恐慌 |
| **结构性强度** | sh000688.percent - sh000001.percent | >2%=科技主线虹吸 |
| **成交水位** | from news.md market overview | ≥2万亿=活跃, 1-2万亿=正常, <1万亿=冷清 |

**Timing note**：MUST NOT run fetch before 09:25:10. Must sleep until 09:25:10 if entered earlier (`time.sleep(seconds_until)`).

---

## Market State → Parameter Adjustment

Use signals computed above + mapper Market State (DominantThemes, RiskFlags, FinancingFlow) + Step 3 评定的 RegimeHint：

| 市场状态 | 仓位系数 | 止损倍数 | 推荐标的数 | 非主线处理 |
|---------|:---:|:---:|:---:|------|
| 强市 + 放量 | ×1.0 | 1.5×ATR | 10只 | 可轻度参与(≤2只) |
| 震荡 | ×1.0 | 1.5×ATR | 10只 | 降权(≤1只) |
| 弱市(-0.5~-1.5%) | ×0.7 | 2×ATR | 7只 | 全部剔除 |
| 恐慌(<-1.5%) | ×0.5 | 2×ATR（放宽防洗） | 5只 | 全部剔除 |
| 极端分化(科创-上证>3%) | 主线×1.0 非主线×0.5 | 主线1.5× 非主线2× | 8只 | 只在主线板块选 |

Stop-loss widens in weak markets (2×ATR) to avoid noise stops, tightens in strong markets (1.5×ATR) to protect gains. **Systematic — no LLM ad-hoc judgment**.

---

## Buy / Stop / Target Formulas

For each stock, derive quantitative levels from **Strategy Inputs** table in `mapper.md`：

| 参数 | 公式 | 数据来源 |
|------|------|---------|
| **买入区间** | `[MA20, MA20 + 0.5×ATR]` | Strategy Inputs.MA20, .ATR |
| **止损价** | `买入价 - 1.5×ATR` (or 2×ATR 弱市场) | Strategy Inputs.ATR |
| **止盈目标一** | `High20` | Strategy Inputs.High20 |
| **止盈目标二** | `High20 + ATR` | Strategy Inputs.High20, .ATR |

Strategy Inputs table is **authoritative source** — use its values directly, do not re-derive or re-fetch.

### MA20 vs Low20 支撑选择

- If MA20 > Low20 → use MA20 as primary support
- If MA20 < Low20 (bearish) → use Low20 as last-resort support, flag stock as high-risk

### Data Source Rule

Strategy Inputs is **authoritative** for: Price, PriceSource, MA20, ATR, ATR%, High20, Low20.

Re-fetch only if：missing / invalid / stale。**Default: no re-fetch。**

---

## Coverage & Scope

- **Scope**：A-shares only (sh/sz prefix)
- **Coverage**：ALL stocks in `mapper.md` Strategy Inputs table (i.e., all Candidate Pool stocks with `comp.value ≥ 55`)
- **Size**：Minimum 10, maximum 25

---

## Output: strategy.md (V5 结构)

**Quantitative foundation**：Buy zones, stops, targets are formula-driven — validate and adjust based on context, do not invent numbers。

### Structure

1. **Market Context** (inline section)
   - 上证/深证/科创50 levels
   - 大盘方向 / 结构性强度 / 成交水位
   - Step 3 评定的 RegimeHint
   - 市场状态 classification + 仓位系数 / 止损倍数 from Parameter Adjustment table

2. **Strategy (10 stocks)** — table with formula-derived levels + Step 3 Reasoning 调整
   ```markdown
   | Code | Name | Sector | Direction | RiskSeverity | Rating | Buy Zone | Stop | Target1 | Target2 | Position |
   ```

3. **Reasoning Trace** (V5 强制结构化)
   ```markdown
   | Code | DirectionPath | RuleApplications | PerceptionOverride | RereadTriggered |
   ```

4. **Watchlist (Optional)** — indicators_fetch_failed stocks from Observation Pool, **不参与 Direction 决策**

### ReasoningTrace 字段说明

- **DirectionPath**：`comp_value → DirectionBase倾向 → (overrides applied) → final Direction`
  - 例：`86.7→bullish; risk_type=overbought sev2; regime=strong; maj_ev=Neutral; final=bullish`
- **RuleApplications**：tokens 实际应用情况
  - 例：`R37:apply,retain 4★; R35-v3:apply,widen stop`
- **PerceptionOverride**：异常情形下 Step 3 异议 Step 2 字段；无则 `—`
- **RereadTriggered**：触发条件 + 回读结果；无则 `—`

### 3 "super predictions"

从 Strategy 10 中选 3 个：
- 每个 from a **different sector**
- 有 formula-derived entry/stop/target + LLM context adjustment
- 至少有 1 个 Rating ≥ 4⭐

### Rating 评级

V5 Rating 是 Step 3 综合以下信号给的 1-5 ⭐：
- `comp.value` 高分加成
- `comp.conf` 高置信加成
- RiskSeverity 反向扣分
- Pattern 多维组合（如 `heat=RISING + leader=STABLE + volume=SURGE` = 满档）
- MajorEvent Polarity 加减
- OverrideHint 是否 apply（apply R37 / R35-v3 加分）
- Anomaly 中暗含的 setup（如"龙头启动 + 板块未退潮" 加 1⭐）

### Memory Integration

**BEFORE** generating → READ `memory/RULES.md` for active rules + OverrideHint token 定义

**AFTER** generating → append strategy entry to `memory/daily/INDEX.md`：
```markdown
| {MM-DD} | 策略 | <top 3 picks with ratings> | [`strategy`](../../predict/{YYYY-MM-DD}/strategy.md) |
```

---

## Migration: V4-U → V5 Step3

| V4-U Step3 行为 | V5 Step3 行为 |
|----------------|---------------|
| "Do NOT recompute Direction" — 接受 mapper Direction | **RECOMPUTE Direction** via Reasoning Flow |
| "Consume MajorEventFlag as-is" | Consume `maj_ev.pol` as input；may shift Direction per rule |
| 不评 RiskSeverity（沿用 Step 2） | **评 RiskSeverity** per § Step 3-D |
| OverrideHint 仅占位（V4-U） | **真 apply** per RULES.md token definitions |
| 不重读 news.md | Conditional Reread via 3 triggers + 3 hard contradictions |
| 无 PerceptionOverride | Override allowed for whitelisted fields with audit |
| 无 ReasoningTrace 输出 | **ReasoningTrace 强制结构化输出** |

**Backward compat**：V5 Step3 接受 V4-U mapper.md（缺 `comp.conf` / `pattern.*` / `risk_type.value`）— 退化为不消费 confidence、pattern 仅看 anomaly、按 risk_flags 自行映射 risk_type。Direction 仍自算。

---

## Open Questions（Phase 5 companion 阶段定）

1. R73 / R74 / R39-v3 / R35-v3 等在 `memory/RULES.md` 的实际定义（V5 启用前必须绑）
2. Confidence 校准起点 +85 阈值是否强制
3. Override T+1 验证机制落地形式（人工 vs 自动）
4. Regression Audit 30 日窗口命中口径
5. 跨股协同 Reasoning（如"主题内 3 只龙头同时炸板 → 该主题降级"）— V5 单股为主，跨股进 V6

---

## Summary

V5 Step 3 是 Reasoning Layer：
- **输入**：V5 mapper.md computed perception + Confidence + Pattern + Anomaly + Market Context + RULES.md
- **输出**：Direction + RiskSeverity + OverrideHint 应用 + Buy/Stop/Target + ReasoningTrace + (可选) PerceptionOverride
- **核心规则**：Unidirectional Flow（不重读新闻）+ Override Audit（写 trace）+ RuleBind（apply 同时记 effect）
- **永远不做**：Execution 层补信息；扫全文 news.md 重新映射主题；override 不可 override 字段（如 comp, tech_score）；ad-hoc 创造参数表外的 stop 倍数