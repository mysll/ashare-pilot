---
description: 每日市场分析 (早盘3步流水线: 新闻→映射→策略)
agent: general
---

Load skill `daily-market-analysis` and execute the full 3-step pipeline.

Date: $ARGUMENTS (use YYYY-MM-DD, default to today if empty)

This runs Step 1 (news brief) → Step 2 (stock mapping) → Step 3 (trading strategy).
Outputs go to predict/{date}/ including strategy.json and daily_report.html.
