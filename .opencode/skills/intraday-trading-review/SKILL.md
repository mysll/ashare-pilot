---
name: intraday-trading-review
description: Review yesterday's intraday tail-position predictions against T+1 morning actual results. Compare Entry Plan recommendations with real next-day morning price movements (9:30-10:00), verify overnight holding payoff, extract lessons, update INTRADAY_RULES.md, and write structured verification to memory. Trigger at T+1 9:45-10:00 or when user asks for 尾盘复盘/intraday verification/review.
---

# Intraday Trading Review (尾盘复盘 Workflow)

Verify yesterday's intraday tail-position strategy against T+1 **morning** (9:30-10:00) actual market data. 
The goal of tail positioning is overnight hold → next morning exit. Verification at 9:45-10:00 answers: 
did the overnight hold pay off at the morning exit window?

## Workflow Overview

```
Step 1: Read Tail Strategy
        predict/{date}/tail_strategy.md
            │
            ▼
Step 2: Fetch T+1 Morning Prices
        stock-analysis skill (fetch_stock.py + --intraday 1-min)
            │
            ▼
Step 3: Compare & Analyze
        trading-strategist
        (验证 T+1 9:30-10:00 开盘兑现)
            │
            ▼
Step 4: Write to Memory
        memory/daily/{date}/intraday_verification.md
        memory/daily/INDEX.md
        memory/INTRADAY_RULES.md
        memory/SHARED_RULES.md
```

## Execution Steps

### Step 1: Read Today's Tail Strategy

**Action:** Read `predict/{YYYY}-{MM}-{DD}/tail_strategy.md`

**What to extract:**
- Date and market context (RegimeHint, DominantThemes)
- Tail Position Table: all Recommend/Light/Wait recommendations
  - Code / Name / Theme / Tradeability / OvernightScore / TailFlow
  - ProfileMatch (Aligned/Degraded/Invalidated/New)
  - Tail Action / Entry Plan (Buy Zone / Stop / Position / EntryMode)
  - Tomorrow Expectation (High/Moderate/Weak/Risk)
- ReasoningTrace: per-stock DirectionPath / RuleApplications / ProfileTrace
- Prediction Review: Morning vs Intraday comparison (if available)

**Key question to answer:** Did the overnight hold produce a profitable T+1 morning exit?

---

### Step 2: Fetch T+1 Morning Market Data

**Agent:** `stock-analysis` skill

**Target stocks:** All stocks from yesterday's Tail Position Table.

**Timing:** Run at T+1 9:45-10:00. Data is from the current session (9:30 open → now).

**For each stock, fetch:**
- T+1 real-time quote: current price, open, high, low, change_pct (`fetch_stock.py`)
- T+1 intraday 1-min K-line: analyze open gap, first 30-min price action pattern (`--intraday --scale 1`)
- Verify: did overnight hold produce a profitable morning exit?
- Check: was the Entry Plan buy zone entered yesterday at 14:30?

**Scripts:**
```bash
# Real-time (T+1 morning, ~9:45)
python .opencode/skills/stock-analysis/scripts/fetch_stock.py CODE1,CODE2,... --json

# Intraday 1-min K-line (first 45 min of T+1)
python .opencode/skills/stock-analysis/scripts/fetch_stock.py CODE --intraday --scale 1 --json
```

---

### Step 3: Compare & Analyze (使用 trading-strategist 复盘)

**Agent:** `trading-strategist`

**Task:** Detailed comparison between yesterday's intraday tail predictions and T+1 morning (9:30-10:00) actual results.

**Required analysis sections:**

#### 3a. Entry Plan Accuracy Table

| 代码 | 名称 | 尾盘操作 | 画像匹配 | 买入区间 | T+1 开盘 | T+1 现价(~10:00) | 早盘高 | 早盘低 | 是否入区 | 是否止损 | 开盘兑现 | 结果 |
|------|------|:---:|:---:|----------|:---:|:---:|:---:|:---:|:---:|------|

Results:
- **成功** (entered buy zone, T+1 morning exit profitable — 开盘跳涨或早盘拉升)
- **部分成功** (entered zone, morning exit break-even or small profit)
- **踏空** (correct direction but never entered zone; morning rally missed)
- **止损** (entered zone, T+1 open gap-down triggered stop at open)
- **失败** (wrong direction, T+1 open lower, morning continued down)
- **不追高正确** (No Chase was correct — stock opened lower or went sideways)

#### 3b. ProfileMatch Verification

Verify whether Morning Trade Profile playbooks aligned with T+1 morning reality:

| 代码 | 早盘剧本 | 尾盘匹配 | T+1 开盘表现 | Profile判定 | 说明 |
|------|----------|:---:|------|:---:|------|

Profile判定: 
- **一致成立** (Aligned: playbook matched T+1 morning outcome)
- **降级正确** (Degraded: decision to reduce was correct)
- **降级踏空** (Degraded but morning rally confirmed opportunity)
- **失效确认** (Invalidated: Morning hypothesis genuinely failed at T+1 open)
- **新发现成立** (New: Intraday discovery paid off at T+1 morning)

#### 3c. Tomorrow Expectation Verification (T+1 开盘兑现)

| 预期档位 | 总数 | T+1 开盘兑现 | 准确率 |
|:---:|:---:|:---:|:---:|
| High Continuation | x | x | xx% |
| Moderate | x | x | xx% |
| Weak | x | x | xx% |
| Risk | x | x | xx% |

**兑现标准 (T+1 morning)**:
- High: 开盘 ≥ +1% 且 10:00 前触及 +2%
- Moderate: 开盘 -1%~+1% 或早盘小幅盈利
- Weak: 开盘 < -1% 或早盘持续走弱
- Risk: 开盘即大幅低开 > -3%

For each mismatch, analyze why. Per I06 rubric validation (morning exit context).

#### 3d. OvernightScore Calibration

Analyze correlation between OvernightScore and T+1 morning exit returns (~9:30-10:00):

| OvernightScore Range | Count | Avg T+1 Open Gap | Avg Morning Exit Return | 命中率 |
|:---:|:---:|:---:|:---:|:---:|
| 90-100 | x | +x.x% | +x.x% | xx% |
| 75-89 | x | +x.x% | +x.x% | xx% |
| 60-74 | x | +x.x% | +x.x% | xx% |
| <60 (Avoid) | x | +x.x% | +x.x% | xx% |

**Morning exit return** = (T+1 price at ~10:00 or morning high near exit) / 昨日尾盘买入价 - 1.

Flag if OvernightScore thresholds need recalibration.

#### 3e. Tradeability Classification Accuracy

| Tradeability | Count | Correct | Accuracy | Note |
|-------------|:---:|:---:|:---:|------|
| Suitable | x | x | xx% | |
| Watch | x | x | xx% | |
| Extended | x | x | xx% | |
| Avoid | x | x | xx% | |

#### 3f. Intraday Rule Effectiveness Assessment

Evaluate each intraday rule (I01-I08) and relevant shared rules:

| 规则 | 触发标的 | T+1结果 | 判定 | 累计 |
|------|----------|------|:---:|:---:|
| I01 Tradeability | xxx | xxx | ✅/⚠️/❌ | 第x次 |
| I02 OvernightScore | xxx | xxx | ✅/⚠️/❌ | 第x次 |
| I03 TailFlow | xxx | xxx | ✅/⚠️/❌ | 第x次 |
| I04 Extension | xxx | xxx | ✅/⚠️/❌ | 第x次 |
| I05 隔夜边界 | xxx | xxx | ✅/⚠️/❌ | 第x次 |
| I06 T+1兑现 | xxx | xxx | ✅/⚠️/❌ | 第x次 |
| I07-v2 Entry Plan | xxx | xxx | ✅/⚠️/❌ | 第x次 |
| I08 轮动 | xxx | xxx | ✅/⚠️/❌ | 第x次 |

Also evaluate applicable SHARED_RULES (R36, R37, R62, etc.) that were triggered.

#### 3g. New Lessons & Rule Updates

Extract **actionable intarday-specific rules** from T+1 results. Each new rule:
- **规则**: One-sentence rule statement
- **场景**: When does this apply (market condition, time, stock type)
- **证据**: Specific example from today's data (stock code, prices, timeline)
- **操作**: Concrete operational guidance for Intraday Agent

---

### Step 4: Write to Memory

#### 4a. Write Intraday Verification File

**Output file:** `memory/daily/{YYYY}-{MM}-{DD}/intraday_verification.md`

**File format:**

```markdown
# 尾盘验证复盘 {YYYY}-{MM}-{DD}

Date: {YYYY-MM-DD}
Verified: {T+1 date} 9:45-10:00 (T+1 morning session)

## 市场环境回顾

- RegimeHint: {panic/weak/neutral/strong-sector}
- DominantThemes: {theme list}
- 14:30 上证: xxxx (+x.xx%)

## Entry Plan 执行结果

**可执行-EntryPlan 成功率**: X/Y = XX%
**ProfileMatch 一致率**: Aligned X / Degraded X / Invalidated X / New X
**T+1 高预期兑现率**: High Continuation X/Y = XX%
**OvernightScore 相关性**: r = x.xx (or directional summary)

### 成功案例

| 代码 | 名称 | 剧本 | 买入区 | 昨日尾盘入场 | T+1 开盘 | ~10:00 价 | 收益 | ProfileMatch |
|------|------|------|--------|:---:|:---:|:---:|:---:|:---:|
| xxx | xxx | MOMENTUM | xx~xx | xx | xx | xx | +x.x% | Aligned |

### 失败/踏空案例

| 代码 | 名称 | 失败原因 | 类别 | 教训 |
|------|------|----------|------|------|
| xxx | xxx | 价格超出锚点未入区→踏空 | 踏空 | MA5锚点太快，强趋势应VWAP |
| xxx | xxx | 入场后尾盘跳水→止损 | 止损 | TailFlow=Neutral不应Light |

...

## Tradeability 分类验证

| Tradeability | 判定 | 实际 | 正确/错误 |
|-------------|:---:|------|:---:|
| Suitable (x只) | x正确 | | |
| Watch (x只) | x正确 | | |
| Extended (x只) | x正确 | | |
| Avoid (x只) | x正确 | | |

## Tomorrow Expectation 验证

| 预期 | 预测数 | 兑现数 | 准确率 |
|:---:|:---:|:---:|:---:|
| High | x | x | xx% |
| Moderate | x | x | xx% |
| Weak | x | x | xx% |
| Risk | x | x | xx% |

## 关键教训

### 1. <Lesson Title>

**Why**: ...

**How to apply**: ...

...

## 规则触发记录

| 规则编号 | 规则名称 | 触发标的 | 结果 | 累计验证次数 |
|----------|----------|----------|------|:---:|
| I01 | Tradeability | xxx | ✅ 正确 | 第1次 |
| I02 | OvernightScore | xxx | ⚠️ 部分有效 | 第1次 |
| I03 | TailFlow | xxx | ✅ 正确 | 第1次 |
| I06 | T+1兑现 | xxx | ✅ 正确 | 第1次 |
| I07-v2 | Entry Plan | xxx | ⚠️ 部分有效 | 第1次 |
| R37 | 强市超买豁免 | xxx | ✅ 正确 | 第7次 |

## 规则更新建议

(列出需要新增/修改/退役的规则, 以及目标文件: INTRADAY_RULES.md 或 SHARED_RULES.md)

## 次日尾盘策略调整

(基于本次复盘的实时改进建议)
```

#### 4b. Update daily/INDEX.md

Append new entry at the top of `memory/daily/INDEX.md`:

```markdown
| {MM-DD} | 尾盘验证 | <Entry Plan success rate>, <key lessons> | [`intraday_verification`]({YYYY-MM-DD}/intraday_verification.md) |
```

#### 4c. Update Rule Files

New rules or status changes based on scope:

| 发现来源 | 目标文件 | 示例 |
|----------|----------|------|
| Intraday 专属规律 | `memory/INTRADAY_RULES.md` | I01-I08 验证/修订; 新尾盘规则 |
| 通用规律 (早盘+尾盘都适用) | `memory/SHARED_RULES.md` | 新发现的通用市场规律 |
| 早盘规律 (从尾盘复盘发现) | `memory/RULES.md` | 尾盘复盘发现的竞价/开盘规律 |

Actions per file:
- **New rule discovered**: Add to "观察中" section with `⚠️ 首验`
- **Rule status change**: Update emoji + verification count
- **Rule retirement**: Move to deprecated with reason
- **OvernightScore threshold adjustment**: Update I02/I05 boundaries if needed

#### 4d. Update PERFORMANCE.md (periodically)

- Update Intraday monthly stats after each verification
- Track: EntryPlan hit rate, ProfileMatch distribution, Tomorrow Expectation accuracy
- Add notable dates for significant findings (e.g., "首个I06全垒打日", "MA5锚点连续踏空触发I07-v2修订")

## Output Files

| File | Content | Generated By |
|------|---------|--------------|
| `memory/daily/{date}/intraday_verification.md` | Detailed intraday verification report | Step 3+4 |
| `memory/daily/INDEX.md` (updated) | Index entry for intraday verification | Step 4b |
| `memory/INTRADAY_RULES.md` (updated) | New/modified intraday rules | Step 4c |
| `memory/SHARED_RULES.md` (updated) | New/modified shared rules | Step 4c |
| `memory/RULES.md` (updated) | Morning rules discovered via intraday review | Step 4c |
| `memory/PERFORMANCE.md` (updated) | Cumulative intraday stats | Step 4d |

## Quick Reference

| Step | Action | Input | Output |
|------|--------|-------|--------|
| 1 | Read Tail Strategy | `predict/{date}/tail_strategy.md` | Extracted Entry Plans + Profiles |
| 2 | Fetch T+1 Actuals | Stock codes from tail_strategy | T+1 daily/intraday prices |
| 3 | trading-strategist analysis | Entry Plan predictions + T+1 actuals | Full comparison report |
| 4 | Write Memory | Analysis report | `memory/daily/{date}/intraday_verification.md` + INDEX/INTRADAY_RULES/SHARED_RULES updates |

## Common Usage

- "复盘尾盘策略"
- "Run intraday review / 尾盘复盘"
- "Verify today's tail strategy on T+1"
- "尾盘预测怎么样了？验证一下"
- "Update intraday rules from today's results"

## Important Notes

- Run **at T+1 9:45-10:00** for morning exit verification (tail positioning = overnight → morning exit)
- **BEFORE** generating analysis → READ `memory/INTRADAY_RULES.md` (尾盘规则) AND `memory/SHARED_RULES.md` (通用规则) to understand existing rules and cumulative counts
- **AFTER** generating review:
  - Write verification to `memory/daily/{YYYY-MM-DD}/intraday_verification.md`
  - Append entry to `memory/daily/INDEX.md` (尾盘验证 row)
  - Update `memory/INTRADAY_RULES.md` (I01-I08 规则状态更新)
  - Update `memory/SHARED_RULES.md` if universal patterns discovered
  - Update `memory/RULES.md` if morning patterns discovered via intraday review
- Cumulative rule counts tracked per-rule (e.g., "I01 第3次验证")
- Output in Chinese (中文输出)
- If today's `tail_strategy.md` does not exist yet, report error and suggest running intraday-market-analysis first
- **ProfileMatch 复盘口径**: Verify whether Morning Trade Profile playbook was validated or invalidated by T+1 reality
- **EntryPlan 复盘口径**: Main KPI = 可执行-EntryPlan 成功率 (not old 严格-MA20)
