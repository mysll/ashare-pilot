---
description: 盘中操作指南 (基于早盘策略+实时数据, 生成A/B/C/D操作指令HTML)
agent: general
---

Load skill `intraday-operation-guide` and execute the full operation guide workflow.

Date: $ARGUMENTS (use YYYY-MM-DD, default to today if empty)

Run the state-aware lifecycle entrypoint. It discovers today's valid snapshot chain automatically. Before 09:35 it remains active and executes both confirmations at 09:35:10 and 09:40:10; later invocations perform a current-data recheck without requiring the user to say "再次确认".

```bash
uv run --frozen ashare-pilot operations guide run --date {YYYY-MM-DD}
```

Never rebuild the guide from an old `_0940` decision after a newer snapshot was fetched. Use `operation_run.latest.json` as the atomic authority for the matching immutable snapshot, decision, and HTML; unversioned latest files are convenience projections only.

Reads predict/{date}/strategy.json + mapper.json. Fetches real-time quotes and 5-min K-lines. Outputs operation_guide.html with A/B/C/D operation classes. Does NOT place orders.
