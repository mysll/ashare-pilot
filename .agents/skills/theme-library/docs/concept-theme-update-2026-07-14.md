# Theme Library Concept 映射修订文档

- **日期**: 2026-07-14
- **范围**: `scripts/theme_config.json`（主题↔概念映射与权重）
- **数据基线**:
  - `cache/concepts.json` 更新于 2026-07-14 18:10（495 concepts）
  - `cache/stocks/*.json` 当日成分缓存（**实际成分数以此为准**）
  - `metadata/update_log.json` build 于 2026-07-14 18:44（61 themes / 328 mapped / 167 unthemed）
  - `theme_config.json` 上次修改约 2026-06-17（映射配置滞后于 concept 缓存）
- **修订依据**: `docs/concept-theme-update-review-2026-07-14.md`（评审 + 本地复算确认）
- **修改状态**: Batch 1 已实施（2026-07-14）：已改 `theme_config.json` 并 rebuild；基线在 `.cache/theme-library/baseline-2026-07-14/`

## 1. 结论摘要

| 项 | 结论 |
|----|------|
| 本批是否新增/删除主题 | **否**（是否另建主题由后续专项评估决定，不作「覆盖已够」断言） |
| 映射失效（config 有、cache 无） | **0** |
| 是否必须改映射 | **是**（明确投资向 concept 漏挂） |
| 本批是否改 `concept_aliases` | **否**（见 §3.2） |
| 风格/指数/交易状态类 unthemed | **保持不挂**（约 100+ 项，属设计预期） |

**原则**:

1. 只把「产业语义清晰、成分纯度可接受、排名冲击可控」的 concept 挂到现有主题。
2. 过宽（如「人工智能」）或政策大筐（如「反内卷」）继续 unthemed。
3. **静态主题归属** 由语义/纯度/排名影响决定；**盘面强弱** 只进动态 `market` view，不决定是否映射。
4. 新增 concept 权重会进入 V5 `total_theme_weight` **分母**，可能使旧股 coverage 下降、qualified 减少——权重必须先模拟再落库。

---

## 2. 现状快照

```
concept 总数:     495
已映射 themed:    328
未映射 unthemed:  167
  ├─ 风格/指数/财报/交易状态等: ~101
  └─ 投资向但未挂:               ~66
      └─ 其中 BK≥1100 较新且值得评估: ~10
```

### 2.1 成分数字段说明（重要）

| 来源 | 字段 | 实际含义 |
|------|------|----------|
| `cache/concepts.json` → `stock_count` | 东财 `f104` | **上涨家数**（与 `up_count` 同源，见 `datasource.py`） |
| `cache/stocks/BKxxxx.json` → `len(stocks)` | 成分列表长度 | **真实成分数**（主题构建使用此数据） |

**文档与模拟一律使用真实成分数。** `concepts.json.stock_count` 字段修复见 Batch 3，不阻塞本批映射。

### 2.2 `concept_aliases` 与 keyword 的关系

`concept_aliases` 仅在 `build_library` 写入各 concept JSON 的 `aliases` 字段。

`keyword_to_theme.json` **只**包含：主题正式名、主题 aliases、主题 keywords。

`query_keyword()` 顺序：keyword_to_theme → 主题 alias → concept **正式名** 包含匹配。  
**全程不读取 concept_aliases。**

因此：「有 concept alias 但 unthemed」**不会**造成 keyword→theme 假阳性；unthemed concept 本就可独立查询。  
本批 **不删除、不强制映射** 植物照明 / 无线充电 / 电子烟 / 电子车牌 / 超清视频 的 aliases。  
若需 `4K`/`8K` 等 alias 可查询，另立代码任务（Batch 3），返回类型为 `concept` 而非强制 theme。

---

## 3. 变更清单（按优先级）

### 3.1 Batch 1 / P0 — 低风险映射（建议本次实施）

| # | Code | Concept | 实际上涨家数* | **实际成分数** | 目标主题 | 权重 | 模拟影响（pool / qualified / Top20 换手） | 结论 |
|---|------|---------|-------------:|---------------:|----------|------|------------------------------------------|------|
| 1 | BK1172 | AI语料 | 20 | **34** | `AI应用` | **0.45** | 412→426(+14) / 167→170(+3) / 0进0出 | **实施** |
| 2 | BK1170 | AI制药（医疗） | 52 | **61** | `创新药` | **0.4** | 465→482(+17) / 236→244(+8) / 1进1出 | **实施**（单挂，不双挂 AI应用） |
| 3 | BK1176 | 财税数字化 | 17 | **41** | `数字经济` | **0.4** | 563→569(+6) / 235→252(+17) / 1进1出 | **实施** |
| 4 | BK1179 | 房屋检测 | 34 | **40** | `房地产基建` | **0.3** | 332→342(+10) / 171→179(+8) / 1进1出 | **实施** |

\* `concepts.json.stock_count`，仅供对照，不作决策依据。

**默认决策（已确认口径）**:

- AI制药：仅挂 `创新药`，权重 **0.4**（评审区间 0.35–0.45 的中间值）；不双挂 `AI应用`。
- 财税数字化：挂 `数字经济`（非 `信创`）。
- 本批 **不改** `concept_aliases`、`anchors`、`min_coverage`、`min_concepts`。
- themed 概念数预期：328 → **332**。

### 3.2 暂缓（原 P0 移出，进入专项）

| Code | Concept | 实际成分数 | 原建议 | 暂缓原因 | 后续动作 |
|------|---------|-----------:|--------|----------|----------|
| BK1155 | 小米汽车 | **100** | 新能源车 @0.55 | pool +65；qualified **128→72(-56)**；Top20 **12进12出**；分母冲击过大 | 测 0.3/0.4/0.5 + 必要时联调 `min_coverage`；或独立主题 / 仅 concept 查询 |
| BK1655 | 零售概念 | **62** | 新消费 @0.45 | 口径宽（含港口/航空/地产等）；与已有 `新零售`(w=0.8) 重叠；Top20 **9进9出** | 先 diff `零售概念` vs `新零售` 成分；补消费可优先评估 `化妆品概念` |

### 3.3 Batch 2 / P1 — 专项评估后再映射

启用条件：**产业语义 + 成分纯度 + 与现有主题重合度 + 排名影响模拟**；**不**因短期盘面强弱决定。

每项至少输出：实际成分数、与目标主题已有重合、pool/qualified/Top20 三档权重模拟。

| Concept | 建议主题方向 | 备注 |
|---------|--------------|------|
| 小米汽车 | `新能源车` 或独立主题 | 见 §3.2 |
| 零售概念 | 暂 unthemed | 见 §3.2 |
| 特斯拉概念 | `新能源车` | 需同小米一样做分母冲击模拟 |
| 化妆品概念 | `新消费` | 优先于零售概念评估 |
| 铁路基建 / 水利建设 | `房地产基建` | |
| 煤化工概念 | `化工` | |
| 元宇宙概念 | `VR/AR/MR` | 主题 aliases 已含「元宇宙」 |
| 无线充电 / 超清视频 | `消费电子` 等 | 映射与否独立于 alias 是否保留 |
| 工程机械概念 | `工业母机` 或 `房地产基建` | |
| 智能家居 / 物联网 | 视纯度 | 偏宽，权重宜低或继续 unthemed |
| 资源开采 / 氦气 / 超超临界发电 | 材料/能源相关主题 | 样本或口径需复核 |
| 跨境支付 / 移动支付 / 安防概念 | 金融/数字相关 | |
| 磁悬浮 / 海洋经济 | — | 无完美主题时可保持 unthemed |

### 3.4 P2 — 明确保持 unthemed

| 类别 | 示例 | 原因 |
|------|------|------|
| 交易状态 | 昨日涨停/连板/炸板/首板/高换手/高振幅 | 非投资主题 |
| 风格指数 | 大盘成长/小盘价值/科技风格/消费风格 等 | 非产业主题 |
| 财报事件 | 2026中报预增/扭亏/首亏 等 | 事件标签 |
| 通道/持股 | 沪股通/深股通/融资融券/机构重仓/QFII 等 | 资金标签 |
| 过宽概念 | **人工智能**、**一带一路** | 污染纯度 |
| 政策大筐 | **反内卷概念** | 纯度差，易误映射 |
| 过窄/样本小 | 供销社、同步磁阻电机、PLC概念 | 可查 concept，不入 theme |
| 做市/交易结构 | 科创板做市商/做市股 | 非产业 |

---

## 4. V5 影响机制（实施前必读）

```text
coverage_pct = stock_matched_weight / total_theme_weight × 100
```

- 新增 concept 的权重计入 **所有股票共享的** `total_theme_weight`。
- 未命中新 concept 的旧股：分子不变、分母变大 → coverage 下降 → 可能跌破 `min_coverage` → **qualified 减少**。
- 因此「权重不高」≠「影响不大」；小米汽车 @0.55 是典型反例。
- 低风险批次验收：单主题 qualified 变化建议 **不超过约 15%**，且无未解释的显著下降；Top20 leaders 换手建议 **≤3 进 / 3 出**。

---

## 5. `theme_config.json` 具体改法（Batch 1）

文件: `config/themes/theme-config.json`

concept 名称必须以 `cache/concepts.json` / `cache/stocks` 为准（注意全角括号：`AI制药（医疗）`）。

### 5.1 `AI应用`

`concepts` 追加: `"AI语料"`

`concept_weights_override` 追加:

```json
"AI语料": 0.45
```

### 5.2 `创新药`

`concepts` 追加: `"AI制药（医疗）"`

`concept_weights_override` 追加:

```json
"AI制药（医疗）": 0.4
```

### 5.3 `数字经济`

`concepts` 追加: `"财税数字化"`

`concept_weights_override` 追加:

```json
"财税数字化": 0.4
```

### 5.4 `房地产基建`

`concepts` 追加: `"房屋检测"`

`concept_weights_override` 追加:

```json
"房屋检测": 0.3
```

### 5.5 明确不改

| 项 | 说明 |
|----|------|
| 小米汽车 / 零售概念 | 不进本批 |
| `concept_aliases` | 整表不动 |
| `aliases/theme_aliases.json` | 不动 |
| `theme_library_config.json` | 排名阈值不动 |
| 各 theme `anchors` / `min_coverage` / `min_concepts` | 本批不动（Batch 2 专项时再评） |

---

## 6. 执行步骤（Batch 1）

```bash
# 0. 改配置前：将四个主题基线 JSON 复制到生成目录之外，仅用于 diff
mkdir -p .cache/theme-library/baseline-2026-07-14
cp -n data/theme-library/themes/{AI应用,创新药,数字经济,房地产基建}.json \
  .cache/theme-library/baseline-2026-07-14/

# 1. 按 §5 编辑 theme_config.json

# 2. 仅当需要刷新本批相关成分时（默认跳过已有缓存）:
# uv run --frozen ashare-pilot themes concepts fetch-stocks --concept BK1172
# uv run --frozen ashare-pilot themes concepts fetch-stocks --concept BK1170
# uv run --frozen ashare-pilot themes concepts fetch-stocks --concept BK1176
# uv run --frozen ashare-pilot themes concepts fetch-stocks --concept BK1179
# 全量重拉才用 --reset（本批通常不需要）

# 3. 重建库
uv run --frozen ashare-pilot themes library build

# 4. 查询校验
uv run --frozen ashare-pilot themes query concept AI语料
uv run --frozen ashare-pilot themes query concept "AI制药（医疗）"
uv run --frozen ashare-pilot themes query concept 财税数字化
uv run --frozen ashare-pilot themes query concept 房屋检测
uv run --frozen ashare-pilot themes query theme AI应用 --json
uv run --frozen ashare-pilot themes query theme 创新药 --json
uv run --frozen ashare-pilot themes query theme 数字经济 --json
uv run --frozen ashare-pilot themes query theme 房地产基建 --json
uv run --frozen ashare-pilot themes query stats

# 5. 静态校验：所有已映射 concept 必须存在于实际成分缓存
python - <<'PY'
import json
from pathlib import Path

skill_dir = Path(".agents/skills/theme-library")
config = json.loads(
    (skill_dir / "scripts/theme_config.json").read_text(encoding="utf-8")
)
mapped = {
    concept
    for theme in config["themes"].values()
    for concept in theme.get("concepts", [])
}
cached = set()
for path in (skill_dir / "cache/stocks").glob("BK*.json"):
    data = json.loads(path.read_text(encoding="utf-8"))
    cached.add(data["concept_name"])

missing = sorted(mapped - cached)
print(f"mapped_missing: {len(missing)}")
if missing:
    print("\n".join(missing))
    raise SystemExit(1)
PY
```

说明：`uv run --frozen ashare-pilot themes query concept <name>` 只验证 concept 文件存在及成分数据正常，当前不会显示所属主题。主题归属应通过对应 `theme <name> --json` 输出中的 `concepts` 字段，或 `index/theme_to_concept.json` 验证。基线复制使用 `cp -n`，避免重复执行时用 build 后文件覆盖 build 前快照。

### 6.1 验收标准

| 检查项 | 通过条件 |
|--------|----------|
| mapped missing | config 中 concept 名均能在成分缓存中找到 |
| themed 数量 | 328 → **332** |
| theme membership | 对应 theme JSON 的 `concepts`（或 `index/theme_to_concept.json`）包含新增 concept：AI语料→AI应用；AI制药→创新药；财税数字化→数字经济；房屋检测→房地产基建 |
| 总池增量 | 与模拟一致量级：约 +14 / +17 / +6 / +10（允许成分缓存微调） |
| qualified 变化 | 无未解释显著下降；单主题建议 ≤15%；数字经济 +17 需人工看 leaders/pure |
| leaders 换手 | Top20 建议 ≤3 进/3 出；本批模拟最大 1 进 1 出 |
| pure/candidates | 无明显跨行业无关新增 |
| 知识库 vs 交易池 | 主题库可保留 `sh688*`/`bj*`/ST；**下游交易候选**须排除 `bj*`、`sh688*`、ST/`*ST` |
| aliases | 本批不删除；确认 concept_aliases 未错误进入 keyword_to_theme |
| 回归 | 原主题数 61、索引与查询命令正常 |
| 基线 diff | 四个主题 JSON 对 build 前后做自动/半自动 diff，不只靠肉眼 query |

---

## 7. 风险与回滚

| 风险 | 缓解 |
|------|------|
| concept 名称字符不一致（括号/空格） | 以 cache 的 `name`/`concept_name` 为准 |
| 新权重抬高分母 → qualified 下降 | Batch 1 已模拟；禁止未模拟的高权重追加 |
| 双挂抬高 stock 权重 | AI制药 单挂创新药 |
| 过宽 concept 稀释纯度 | 人工智能/一带一路/反内卷/零售/小米本批不进 |
| 知识库含交易范围外股票 | 下游过滤；不在主题库层强删成分 |
| rebuild 耗时 | 仅 `uv run --frozen ashare-pilot themes library build`；按需 `--concept` 刷新成分 |

**回滚**: 还原 `theme_config.json`，然后完整执行 `uv run --frozen ashare-pilot themes library build`。基线 theme JSON 只用于 diff，不能单独恢复；否则会与 `stocks/*.json`、索引和 metadata 等派生文件不一致。

---

## 8. 实施批次总览

| 批次 | 内容 | 产出 |
|------|------|------|
| **Batch 1** | AI语料、AI制药、财税数字化、房屋检测 | 改 `theme_config.json` + rebuild + §6.1 验收 |
| **Batch 2** | 小米汽车、零售概念、特斯拉、化妆品、铁路/水利、煤化工、元宇宙等 | 逐项影响模拟报告后再改配置 |
| **Batch 3** | 数据/代码质量 | 修 `concepts.json.stock_count`；可选 concept-alias 查询索引；映射静态校验脚本；知识库 vs 交易范围边界文档化 |

---

## 9. 待确认项

- [x] 反内卷：保持 unthemed
- [x] 本批不改 concept_aliases
- [x] AI制药：单挂创新药，默认权重 0.4
- [x] 财税数字化：数字经济
- [x] 小米汽车 / 零售概念：移出 P0
- [x] **是否立即执行 Batch 1 改配置 + rebuild**（已于 2026-07-14 执行并通过 §6.1 验收）

---

## 10. 变更记录

| 日期 | 作者 | 说明 |
|------|------|------|
| 2026-07-14 | analysis | 初版：P0 六概念 + orphan aliases 方案；尚未改配置 |
| 2026-07-14 | analysis | **v2（评审修订）**：修正成分数来源；删除 aliases 假阳性结论与本批 aliases 变更；P0 收敛为四项；小米/零售改专项；补充 V5 分母机制、量化验收、交易范围分层；P1 启用原则改为语义/纯度/排名而非盘面 |
| 2026-07-14 | implement | **Batch 1 落地**：`theme_config` 挂 AI语料→AI应用@0.45、AI制药（医疗）→创新药@0.4、财税数字化→数字经济@0.4、房屋检测→房地产基建@0.3；rebuild；themed 332；pool/qualified/Top20 与模拟一致 |
