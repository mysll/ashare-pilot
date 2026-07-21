# Overnight Alpha System（日内隔夜选股系统）

Version: V1.1

---

# 一、系统目标

## 目标

本系统不是寻找今天涨得最好的股票。

而是寻找：

> 收盘后仍具有资金持续性，预计第二个交易日具有正溢价机会的股票。

即：

```
Today Market
        ↓
资金行为
        ↓
预期延续
        ↓
Tomorrow Premium
```

系统输出的是：

> Tomorrow Opportunity Pool

而不是：

> Today's Strongest Stocks

---

## 交易时刻

本系统的交易规则已经确定：

```
14:30    开始选股（触发 pipeline）
14:30~14:50  市场扫描 + 股票发现 + 数据增强 + 隔夜评分
14:50~14:57  执行买入
次交易日   持有至第二天
```

这意味着：**15:00 收盘数据对选股没有价值。** 系统必须在 14:50 前完成全部计算。

所有数据获取必须基于 14:30 这个时间点之前/当前的价格和资金数据。尾盘指标（Tail Strength）观察的是 14:00~14:30 的尾盘前半段行为，而非 14:30~15:00。

---

# 二、设计原则

## Principle 1：Market First

市场决定股票。

不是先有股票。

流程：

```
市场
    ↓
热点
    ↓
股票
```

而不是：

```
股票
    ↓
主题
```

---

## Principle 2：Data First

所有数字必须来自实时数据。

LLM禁止生成任何数字。

例如：

允许：

```
涨停：61
炸板：19
成交额：13652亿
```

禁止：

```
约60家
大约1.3万亿
```

---

## Principle 3：Expected Premium

评分目标不是：

```
Momentum
```

而是：

```
Tomorrow Expected Premium
```

核心问题：

> 明天是否还有资金愿意继续买？

---

## Principle 4：Progressive Computation（渐进式计算）

**这是整个系统最重要的架构原则。**

不要对全市场做全量计算。

不要对 500 只股票都算 MACD / RSI / ATR / BOLL。

而是分阶段逐级收缩：

```
全市场 5500
    ↓  行情过滤（涨幅/成交额/换手/资金流）
Scan Pool 300~500     ← 耗时 < 3s，只取基本行情，不算任何指标
    ↓  主题归属 + 快速打分
Compute Pool 80~150   ← 这里才算 MACD/RSI/ATR/Bollinger
    ↓  深度评分（5维度 + 风险）
Opportunity Pool 20~40 ← 最终输出
```

每一阶段都有明确目的，计算量逐级下降一个数量级。

---

# 三、整体架构

```
14:30 Trade Time
        │
        ▼
Market Scan       → MarketState
        │
        ▼
Scan Pool Build   → 300~500 stocks (basic market data only)
        │
        ▼
Fast Filter       → Theme归属 + 快速评分
        │
        ▼
Compute Pool      → 80~150 stocks
        │
        ▼
Data Enrichment   → MACD/RSI/ATR/Bollinger/VWAP/Capital detail
        │
        ▼
Theme Detection   → Theme Heat (statistical, bottom-up)
        │
        ▼
Overnight Scoring → 5-dimension score
        │
        ▼
Opportunity Pool  → 20~40 stocks (A/B/C tiers)
```

关键约束：全流程在 14:30~14:50 之间完成（20 分钟窗口）。

---

# 四、Market Scan（市场扫描）

目的：

确定今天市场真正炒什么。

## 获取数据

### 指数

实时：

- 上证
- 深成
- 创业板
- 科创50
- 中证1000

字段：

- Price
- Change%
- Turnover
- Intraday Trend

---

### 市场宽度

获取：

- 上涨家数
- 下跌家数
- 涨停数量
- 跌停数量
- 炸板数量
- 封板率
- 连板数量
- 最高板
- 晋级率

---

### 市场资金

获取：

- 北向资金
- 主力资金
- 行业资金
- 概念资金

---

### 行业排行

字段：

- 行业涨幅
- 成交额
- 资金流
- 上涨家数

---

### 概念排行

字段：

- 概念涨幅
- 龙头
- 成交额
- 资金流

---

输出：

```
Market State
```

包括：

- Market Strength
- Market Breadth
- Capital Direction
- Active Themes

---

# 五、Scan Pool Build（扫描池构建）

## 三层股票池架构

```
Scan Pool     (300~500)   ← 当前阶段：仅基本行情过滤
    ↓
Compute Pool  (80~150)    ← 下一阶段：技术增强
    ↓
Opportunity Pool (20~40)  ← 最终输出
```

## Scan Pool 过滤条件

Scan Pool 只用最轻量的数据：

| 维度 | 条件 | 备注 |
|------|------|------|
| 涨跌幅 | > 0% | 今日上涨 |
| 成交额 | > N 亿 | 排除僵尸股 |
| 换手率 | > 0.5% | 有活跃度 |
| ST | 排除 | 非 ST |
| 新股 | 排除 | 上市 < 30 天 |

**Scan Pool 不使用任何技术指标（MACD/RSI/ATR/Bollinger）。**

只依赖一条实时行情即可，速度极快。

## 多源合并

Pool 来自多个 Source，合并去重后进入 Scan Pool：

### Source A：主线板块

当前市场活跃主线板块的主题库股票。

获取：Theme Library → 过滤成交活跃 + 今日上涨 + 非 ST。

### Source B：涨停池

实时涨停池，含首封时间 + 炸板次数 + 连板高度。

仅作为观察参考，不直接推荐。

### Source C：成交额排行

成交额 Top N。

过滤：放量 + 趋势良好 + 非异常波动。

### Source D：资金流排行

主力净流入排行。

保留：持续净流入。

### Source E：涨幅排行

过滤区间：**2%~7%**。

排除：9%+ 涨幅（避免追高）。

### Source F：尾盘资金（14:00~14:30）

重点观察尾盘前半段：

- 尾盘成交变化
- 尾盘净流入
- 尾盘价格方向

---

## 快速评分（Scan Pool → Compute Pool 过渡）

这是从 400 缩到 120 的关键步骤。

使用轻量评分（不需要计算指标，只用 Scan Pool 已有数据）：

```
QuickScore =
    Market Alignment   × 0.30   (是否属于活跃主题)
  + Capital Attraction × 0.30   (资金流方向)
  + Price Momentum    × 0.25   (涨幅区间 + 分时形态)
  + Tail Activity     × 0.15   (尾盘异动)
```

Score Top 80~150 → Compute Pool。

**QuickScore 也是数据驱动的，LLM 不输出数字。**

---

# 六、Compute Pool（计算池）— 数据增强

对 Compute Pool（80~150 只）执行完整数据增强。

## 行情

- 最新价
- 涨跌幅
- 成交额
- 换手率
- 振幅
- Volume Ratio

---

## 技术指标

- MA5
- MA10
- MA20
- MA60
- MACD
- RSI
- ATR
- Bollinger

---

## 分时数据

- VWAP
- 均价线
- High / Low / Close

重点：尾盘前半段（14:00~14:30）

- 成交变化
- 价格变化
- 承接强度

---

## 资金

- 主力净流入
- 超大单
- 大单
- 连续资金变化

---

# 七、Theme Detection（主题识别）

## 核心差异：Bottom-Up，不是 Top-Down

**Daily Pipeline（预测型）：**

```
News → Theme → Stocks
```

**Intraday Pipeline（确认型）：**

```
Stocks → Theme → Ranking
```

原理：

新闻不会告诉你 "PCB 今天突然爆发"，但股票会。

如果今天 PCB 概念 15 只涨停，新闻可能一条都没有。

所以：

主题由 Compute Pool 中的股票统计出，不依赖任何新闻。

---

## Theme Heat 公式

```
Theme Heat = Breadth + Leader + Capital + Momentum + Continuation
```

| 子维度 | 权重 | 含义 |
|--------|:----:|------|
| Breadth | 20% | 板块内上涨股票数量 / 涨停数量 |
| Leader | 30% | 龙头股涨幅 + 封板质量 |
| Capital | 25% | 板块主力资金净流入 |
| Momentum | 15% | 板块平均涨幅 + 加速度 |
| Continuation | 10% | 连续活跃天数 + 热度趋势 |

最终得到：

```
Theme Ranking（纯统计，非新闻驱动）
```

---

# 八、Overnight Scoring（隔夜评分）

目标：Tomorrow Expected Premium。

不是：Today Momentum。

---

## 评分组成（V1: Rule Based — Initial Weight）

> **重要**：以下权重为 V1 经验初始值（Initial Weight），非固定参数。
> V2 将通过历史回测校准，V3 将支持自动优化。

| 维度 | Initial Weight | 子项 |
|------|:----:|------|
| Theme Continuity | 30% | 主题是否仍在加强（热度趋势↑ / 龙头扩散 / 板块宽度） |
| Capital Continuity | 25% | 全天资金方向 + 尾盘资金方向 |
| Tail Strength | 20% | 14:00~14:30 尾盘承接（放量/不跳水/收盘位置） |
| Position Advantage | 15% | 涨幅适中 (2%~5%) 高分；连续涨停扣分 |
| Risk Deduction | -10% | 连续涨停 / 连续放量 / 获利盘过大 / 龙虎榜兑现 / 高换手 |

---

## 权重演进路线

```
V1: Rule Based
    Initial Weight (经验)
    → 保证系统可运行

V2: Historical Calibration
    历史回测 (e.g. 300天 × 30样本 ≈ 9000个样本)
    → 统计最优权重

V3: Auto Optimization
    滚动窗口 + 自适应权重
    → 市场风格变化自动调整
```

---

最终评分：

```
Overnight Score: 0~100
```

---

# 九、Opportunity Pool（机会池）

最终输出，分三级：

## A：Leader Watch

真正龙头。

作用：观察，不一定买。

---

## B：Premium Candidates

最值得隔夜持有。

**系统主要推荐。**

---

## C：Early Breakout

刚启动，位置低，有补涨机会。

---

每只股票输出：

| 字段 | 说明 |
|------|------|
| Theme | 所属主题 |
| Overnight Score | 综合隔夜评分 |
| Theme Heat | 主题热度 |
| Capital Score | 资金连续性分 |
| Tail Score | 尾盘承接分 |
| Position Score | 位置优势分 |
| Risk Penalty | 风险扣分 |
| Expected Premium | 预期溢价（方向+幅度） |
| Key Reasons | 核心理由（3条以内） |

---

# 十、系统输出

最终生成：

```
intraday_mapper.md
```

包含：

1. Market State
2. Theme Ranking
3. Tomorrow Opportunity Pool（A/B/C 三级）
4. Stock Details（每只股票完整评分追溯）
5. Overnight Score Trace（评分计算路径）
6. Observation Pool（接近阈值但未入选的股票）
7. Excluded Stocks（入选 Compute Pool 但未通过最终筛选的股票 + 原因）

最终交由 **Strategy Layer** 生成 **Tomorrow Trading Strategy**。

---

# 十一、Skill 拆分

系统拆成三个独立 Skill，职责清晰，可独立优化：

## Skill 1: `intraday-market-scan`

**职责**：市场扫描 + 扫描池构建

**输入**：实时行情 API

**输出**：
- `MarketState`（指数 / 宽度 / 资金方向 / 活跃主题）
- `ScanPool`（300~500 只，仅基本行情）

**不涉及**：任何技术指标计算、主题深度分析、评分。

---

## Skill 2: `intraday-stock-discovery`

**职责**：Compute Pool 构建 + 数据增强 + Theme Detection（统计反推）

**输入**：`MarketState` + `ScanPool`

**输出**：
- `ComputePool`（80~150 只，含完整技术指标 + 资金 + 分时）
- `ThemeHeat`（统计自 Compute Pool，非新闻驱动）
- `ThemeRanking`

**不涉及**：策略评分、买卖建议、Direction / RiskSeverity。

---

## Skill 3: `overnight-strategy`

**职责**：隔夜评分 + 机会池分级 + 策略生成

**输入**：`ComputePool` + `ThemeRanking` + `memory/RULES.md`

**输出**：
- `OvernightScore`（5 维度 + 风险扣分）
- `OpportunityPool`（A/B/C 三级，20~40 只）
- `intraday_mapper.md`（7-section）
- （可选）`tomorrow_strategy.md`

**这是唯一的 Reasoning 层**：输出 Direction / RiskSeverity / Expected Premium / ReasoningTrace。

---

## 数据流向

```
[14:30 触发]

Skill 1: intraday-market-scan
  │   MarketState + ScanPool (300~500)
  │   耗时目标：< 5s
  ▼
Skill 2: intraday-stock-discovery
  │   ComputePool (80~150) + ThemeRanking
  │   耗时目标：< 10s（含 80~150 只的技术指标计算）
  ▼
Skill 3: overnight-strategy
  │   OpportunitiyPool (20~40) + intraday_mapper.md
  │   耗时目标：< 5s（纯 LLM reasoning over structured data）
  ▼
[14:50 前完成，执行买入]
```

总耗时目标：**< 20 秒**（不含 LLM 推理时间）。

---

# 十二、设计决策记录

以下 4 项为 V1.1 架构级决策，后续开发以此为基准，不再推翻：

| # | 决策 | 内容 | 理由 |
|---|------|------|------|
| 1 | 三层股票池 | Scan Pool (300~500) → Compute Pool (80~150) → Opportunity Pool (20~40) | "发现"与"计算"解耦，性能与效果兼顾 |
| 2 | Theme 来源 | 由股票统计反推主题（Bottom-Up），不依赖新闻 | 日内热点是市场行为，不是新闻事件 |
| 3 | 权重设计 | V1 为 Rule Based Initial Weight，V2 历史回测校准，V3 自动优化 | 先保证可运行，用数据迭代，不求一步最优 |
| 4 | Progressive Computation | 全市场 5500 → 行情过滤 → 400 → 主题归属 → 150 → 技术增强 → 40 → 策略评分 → 20 | 计算量逐级下降一个数量级，每步有明确目的 |

---

# 十三、核心理念

整个系统始终围绕一个目标：

> 不是寻找今天涨得最多的股票。

而是寻找：

> 今天已经获得资金认可，但上涨空间尚未完全兑现，预计第二个交易日仍具有正溢价机会的股票。
