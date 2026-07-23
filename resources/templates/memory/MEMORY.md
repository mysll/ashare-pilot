# Memory System

本目录保存 Agent 从真实分析和复盘中逐步形成的项目记忆。初始化只提供导航、记录结构和
空规则模板，不预置任何交易策略、经验规则、胜率或历史结论。

## 结构总览

```text
memory/
├── MEMORY.md               导航入口（本文件）
├── RULE_GOVERNANCE.md      未来规则的生命周期和证据约束
├── PERFORMANCE.md          从实际复盘累计的表现统计
├── RULES.md                早盘规则；初始化为空模板
├── INTRADAY_RULES.md       尾盘/T+1 规则；初始化为空模板
├── SHARED_RULES.md         跨时段规则；初始化为空模板
├── daily/
│   ├── INDEX.md            早盘复盘索引
│   └── YYYY-MM-DD/
│       ├── verification.json
│       └── verification.md
└── intraday/
    ├── INDEX.md            尾盘复盘索引
    └── YYYY-MM-DD/
        └── intraday_verification.md
```

## 零历史语义

- 三个规则文件只有模板结构、没有规则行，表示对应作用域尚无已学习规则。
- 不得创建占位规则、复制示例策略或声称存在历史验证。
- 第一份记忆来自真实交易日的 verification，而不是初始化过程。
- 单日发现只能记录为候选，不能直接成为可执行规则。

## 盘后复盘

1. Morning 复盘写入 `memory/daily/YYYY-MM-DD/verification.json` 和 `verification.md`。
2. Intraday 复盘写入 `memory/intraday/YYYY-MM-DD/intraday_verification.md`。
3. 将日期和产物链接追加到对应 `INDEX.md`。
4. 用实际结果更新 `PERFORMANCE.md`，没有样本时保持空状态。
5. 发现可复用模式时先读 `RULE_GOVERNANCE.md`，再决定是否向对应模板写入候选规则。

## 查询路径

- 按日期：`daily/YYYY-MM-DD/` 或 `intraday/YYYY-MM-DD/`
- 按表现：`PERFORMANCE.md`
- 按规则：`RULES.md`、`INTRADAY_RULES.md`、`SHARED_RULES.md`
- 按生命周期：`RULE_GOVERNANCE.md`

## 维护原则

- 事实记录、推断和可执行规则必须分开。
- 缺少样本不能算正向验证。
- 不覆盖旧 verification；修订应保留审计说明。
- 已有 memory 属于用户运行状态，初始化命令只能补缺失文件，不能覆盖。
