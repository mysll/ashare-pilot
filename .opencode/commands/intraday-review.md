---
description: 尾盘复盘 (T+1验证隔夜策略, 对比预测与实际, 更新尾盘规则)
---

Load skill `intraday-trading-review` and execute the full verification workflow.

Date: $ARGUMENTS (要复盘的策略日期 YYYY-MM-DD, 即昨天 T 日)

This verifies yesterday's overnight strategy against actual T+1 market data.
Runs Step 1 (read strategy) → Step 2 (fetch actuals) → Step 3 (compare & analyze) → Step 4 (write to memory/intraday/{date}/intraday_verification.md).
