# Parameter Learning System（参数学习系统）设计文档

Version: V1.0
Status: Design Draft

---

# 1. 设计目标

当前 Morning Agent / Intraday Agent 的 Mapper 阶段包含大量经验参数，例如：

* ThemeHeat 权重
* Composite 权重
* Auction Score 权重
* News Impact 分数
* Direction 阈值
* RiskSeverity 阈值
* Entry Strategy 条件

这些参数目前主要来源于人工经验。

随着系统持续运行，经验参数应逐步演化为数据驱动参数。

Parameter Learning System（PLS）的目标不是自动交易，而是持续学习：

> **评估参数 → 验证参数 → 提出参数优化建议**

而不是直接修改策略。

---

# 2. 系统定位

整个交易系统未来建议划分为五个独立 Agent。

```
Morning Agent
        │
        ▼
Intraday Agent
        │
        ▼
Replay Agent
        │
        ▼
Parameter Learning Agent
        │
        ▼
Knowledge Update
```

其中：

Morning / Intraday 负责交易。

Replay 负责评价。

Parameter Learning 专门负责：

**学习参数。**

它不参与任何交易决策。

---

# 3. 设计原则

## 原则一

Parameter Learning 不修改任何参数。

只能：

```
Collect

↓

Evaluate

↓

Recommend
```

最终由人工批准。

---

## 原则二

所有参数必须可追踪。

例如：

```
ThemeHeat

Version:

v1.3

Weights:

Policy 0.40
Capital 0.15
Emotion 0.25
News 0.20

Last Review:

2026-08
```

所有修改必须保留历史版本。

---

## 原则三

任何建议必须有统计依据。

例如：

```
Policy 权重建议降低

Sample:

682

Correlation:

0.18

Win Rate:

44%
```

而不是：

```
感觉 Policy 最近没用了。
```

---

# 4. 参数分类

建议所有参数统一分类。

## A. Weight（权重）

例如：

```
ThemeHeat

Policy

Capital

Emotion

News
```

Composite

```
Theme
News
Auction
Tech
Macro
```

---

## B. Threshold（阈值）

例如：

```
Composite ≥70

Composite ≥55

RiskSeverity ≥3

ThemeHeat ≥80

Auction ≥60
```

---

## C. Mapping（映射）

例如：

```
Composite

↓

Direction
```

```
RiskFlags

↓

RiskType
```

---

## D. Rule（规则）

例如：

```
MA20

↓

Pullback
```

```
Gap >5%

↓

OpeningStrength
```

---

# 5. 参数生命周期

所有参数建议遵循统一生命周期。

```
Manual

↓

Observed

↓

Verified

↓

Recommended

↓

Approved

↓

Production
```

说明：

Manual

人工经验。

Observed

已经积累数据。

Verified

统计验证。

Recommended

Learning Agent 建议修改。

Approved

人工批准。

Production

正式上线。

---

# 6. 数据来源

Parameter Learning 不产生数据。

全部来自已有系统。

包括：

Morning Strategy

Replay

Trade Replay

Daily Replay

Intraday Replay

Historical Market

最终形成统一数据库。

例如：

```
TradeRecord

Date

Stock

ThemeHeat

Composite

Auction

Tech

Direction

EntryStrategy

Result
```

---

# 7. 学习目标

建议 Parameter Learning 分四层。

---

## Layer 1

Weight Learning

目标：

学习各评分权重。

例如：

当前：

```
ThemeHeat

Policy

0.40
```

学习后：

```
建议：

0.31
```

---

## Layer 2

Threshold Learning

目标：

学习最佳阈值。

例如：

当前：

```
Composite ≥70

Bullish
```

统计：

```
65~69

实际胜率：

71%
```

建议：

```
Bullish

Threshold:

65
```

---

## Layer 3

Rule Learning

目标：

统计 Rule 命中率。

例如：

```
Rule

R61

Win

81%
```

```
Rule

R74

Win

36%
```

建议：

```
R74

降权
```

而不是删除。

---

## Layer 4

Pattern Learning

例如：

```
HEAT_RISING
```

统计：

```
Success

78%
```

```
ROTATION_SECONDARY

32%
```

建议：

降低权重。

---

# 8. 推荐学习方法

建议按复杂度逐步升级。

---

## 第一阶段

描述统计

例如：

```
平均收益

胜率

标准差

最大回撤
```

无需机器学习。

---

## 第二阶段

相关性分析

例如：

```
ThemeHeat

vs

NextDay Return
```

输出：

```
Correlation

0.42
```

用于判断：

ThemeHeat 是否有效。

---

## 第三阶段

单变量回归

例如：

```
Return

=

a

+

b

×

ThemeHeat
```

学习：

最佳系数。

---

## 第四阶段

多变量回归

例如：

```
Return

=

Policy

+

Capital

+

Emotion

+

News
```

得到：

```
Weight
```

用于建议新的 ThemeHeat 权重。

---

## 第五阶段

AutoML（未来）

未来可升级：

XGBoost

LightGBM

CatBoost

SHAP Explainability

学习：

Feature Importance。

仅作为参考。

---

# 9. 参数更新流程

建议采用：

```
Replay

↓

Statistics

↓

Parameter Report

↓

Human Review

↓

weights.yaml

↓

Production
```

而不是：

Replay

↓

自动修改。

---

# 10. 参数配置管理

建议所有参数移出 Skill。

建立统一配置。

例如：

```
config/

weights.yaml

thresholds.yaml

mapping.yaml

rules.yaml
```

Skill：

禁止写死参数。

全部读取配置。

---

# 11. 输出报告

Learning Agent 每周生成：

```
parameter_review.md
```

内容：

## ThemeHeat

当前：

```
Policy

0.40
```

建议：

```
0.32
```

原因：

```
Correlation

下降

Win Rate

下降

Sample

683
```

---

## Composite

当前：

```
Auction

0.20
```

建议：

```
0.27
```

原因：

Auction 与次日收益相关性提高。

---

## Threshold

当前：

```
Bullish

70
```

建议：

```
67
```

原因：

过去 90 天：

67~69 区间胜率显著提高。

---

# 12. 审批机制

Learning Agent 永远没有权限：

```
Update

weights.yaml
```

只能生成：

```
parameter_review.md
```

真正更新流程：

```
Learning Agent

↓

Human Review

↓

Approve

↓

Version Update

↓

Production
```

---

# 13. 参数版本管理

建议所有参数版本化。

例如：

```
ThemeHeat

v1.0

↓

v1.1

↓

v1.2
```

记录：

```
更新时间

修改人

修改原因

统计依据

样本数
```

确保任何版本均可回滚。

---

# 14. 长期演化路线

## Phase 1

人工经验参数。

---

## Phase 2

Replay 自动统计。

---

## Phase 3

Learning Agent 提出建议。

---

## Phase 4

人工批准更新参数。

---

## Phase 5

建立 Parameter Knowledge Base。

记录：

* 每次参数调整
* 调整原因
* 调整后的收益变化
* 是否成功

形成完整参数演化历史。

---

# 15. 最终架构

```
Morning Agent
        │
        ▼
Intraday Agent
        │
        ▼
Replay Agent
        │
        ▼
Parameter Learning Agent
        │
        ├── Weight Learning
        ├── Threshold Learning
        ├── Rule Learning
        ├── Pattern Learning
        │
        ▼
parameter_review.md
        │
        ▼
Human Approval
        │
        ▼
weights.yaml / thresholds.yaml / rules.yaml
        │
        ▼
下一版本策略系统
```

---

# 16. 核心设计原则

Parameter Learning 的职责不是寻找"最优参数"，而是建立一个**持续、可解释、可审计的参数演化机制**。

系统永远遵循以下闭环：

```
交易

↓

Replay

↓

统计

↓

学习

↓

建议

↓

人工审核

↓

参数更新

↓

下一版本交易
```

参数的每一次调整，都必须能够回答三个问题：

1. **为什么调整？**（统计依据）
2. **调整了什么？**（版本差异）
3. **调整后效果如何？**（后续验证）

只有满足这三个条件，参数学习系统才能真正从"经验驱动"逐步演化为"数据驱动"，同时保持策略的稳定性、可解释性和可回滚性。
