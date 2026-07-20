# Step 3 Selection Rubric

只读取当日 `.strategy_llm_input.json`、本 rubric、输出合同、`memory/RULES.md` 与 `memory/SHARED_RULES.md`。不得打开完整 mapper、pool、news 或 Markdown 报告。

## 1. 全候选浅扫描

按输入顺序检查每一行，至少比较：

- composite / tech / theme_heat / news_impact / auction / money_flow；
- primary/source themes、role_tags、Pattern states、risk_type；
- major_event、anomaly、conditional news evidence；
- DirectionBase 与 RiskSeverityBase advisory hints；
- profile base、价格位置和 ATR%。

必须在看完全部候选后才确定选择。不要为未选股生成隐藏的完整推理记录，也不要把低排名候选提前省略。

## 2. 市场 regime

以 `market_inputs.regime_hint` 为 advisory，结合三个指数、dominant themes、融资和风险标记，最终选择 `panic|weak|neutral|strong-sector`。`RULES.md` 的 R85 与 `SHARED_RULES.md` 的 R88 等匹配规则可改变最终判断，原因写入 `market.notes`。

主列表上限：panic 5、weak 7、neutral 10、strong-sector 10。可以少于上限，但不得用中性/看空/暂不参与行凑数。

## 3. 入选决策

先在完整集合中按主题主线、综合质量、可执行性、相关性与组合集中度选择代码及顺序。入选后才对每只执行完整推理：

1. 从 composite advisory 得到 Direction 起点：`>=70 看多`、`55-69 偏多`、`45-54 中性`、`<45 看空`。
2. 检查 confidence exceptions、Pattern、major event 和 anomaly；有条件新闻时只使用顶层 `news_evidence` 对应项。
3. 对每个 risk_type 独立判断 severity，取最大值；非 strong-sector 下 severity 3 将 Direction 上限压到偏多。severity 只写进 `reasoning.risk`，不要新增字段。
4. 阅读完整 RULES/SHARED_RULES，匹配规则并写 `rules_applied`；规则 override 必须有可追溯理由。
5. 确定 rating、entry profile、anchor、trigger/no-buy、position budget、pre-open 与 T+1 plan。
6. 对 Python `profile_base` 只提交必要的白名单 `profile_overrides`；每项必须说明理由。

## 4. 证据边界

`reasoning.source_basis` 必须可读、简短、具体，且只引用候选的 source themes、role_tags、candidate `news_link` 或其主题 evidence。不能添加输入中不存在的 role tag 或 `news#id`。

无 canonical 新闻引用但存在 anomaly/低置信标记时，只根据已投影字段说明不确定性，不得猜测新闻内容。

`composite.confidence=50` 通常来自确定性的 money-flow 默认输入，新闻回读不能修复，因此它单独出现时不是 Conditional Reread trigger；仍应把该 confidence exception 纳入 Direction 不确定性判断。tech/theme/news 的低置信、anomaly、硬矛盾和可用的 `auction_change_pct>3% + news_impact<40` 才触发对应证据回读。

## 5. 排除

不要输出普通未选股。Python 会按输入顺序补齐观察池。仅当默认“regime 名额限制”会明显误导时，才在 `exclusion_overrides[]` 写 `{code,reason}`；soft risk、低分或 setup 信号不得伪装成确定性因果。
