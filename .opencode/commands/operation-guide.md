---
description: 盘中操作指南 (基于早盘策略+实时数据, 生成A/B/C/D操作指令HTML)
agent: general
---

Load skill `intraday-operation-guide` and execute the full operation guide workflow.

Date: $ARGUMENTS (use YYYY-MM-DD, default to today if empty)

Pipeline: Step 1 (run snapshot at 09:35 + 09:40) → Step 2 (read rules) → Step 3 (generate guide) → Step 4 (render HTML board).

Reads predict/{date}/strategy.json + mapper.json. Fetches real-time quotes and 5-min K-lines. Outputs operation_guide.html with A/B/C/D operation classes. Does NOT place orders.
