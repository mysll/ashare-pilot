---
description: 尾盘分析 (14:30隔夜Alpha流水线: 计算→感知→推理→发布)
agent: general
---

Load skill `intraday-market-analysis` and execute the full overnight-alpha workflow.

Date: $ARGUMENTS (use YYYY-MM-DD, default to today if empty)

Pipeline: Compute → Perception → Reasoning → Validate & Publish.
Outputs: intraday/{date}/intraday_mapper.json, overnight_strategy.json, overnight_strategy.html.
