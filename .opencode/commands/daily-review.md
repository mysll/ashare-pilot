---
description: 每日复盘 (盘后验证早盘策略, 生成 verification.json/md, 更新规则和记忆)
agent: general
---

Load skill `daily-trading-review` and execute the full review workflow.

Date: $ARGUMENTS (要复盘的策略日期 YYYY-MM-DD, default to today)

This runs Step 1 (load strategy) → Step 2 (generate verification.json) → Step 3 (write human review to memory/daily/{date}/verification.md) → Step 4 (update rules and performance).
