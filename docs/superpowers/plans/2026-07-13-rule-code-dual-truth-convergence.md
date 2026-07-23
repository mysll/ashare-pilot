# Rule–Code Dual-Truth Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make OvernightScore filters and related INTRADAY rules (I02, I10, I11/I11-v2, VWAP/I14) a single source of truth — code behavior and rule docs describe the same machine — before any weight/threshold tuning.

**Architecture:** Compute owns numeric score and hard/soft eligibility (`score_overnight.py`). Rules docs become either (a) the human-readable spec of that code, or (b) explicit Reasoning-only overlays that never claim to change scores. Reasoning (`intraday-strategy` annotations) reads compute outputs and applies only Direction / position / T+1 rules. No weight calibration in this plan.

**Tech Stack:** Python 3, existing `score_overnight.py`, pytest, `memory/INTRADAY_RULES.md`, skill SKILL.md files. No new dependencies.

**Non-goals (explicit):**
- Do **not** retune `WEIGHTS_V1_2` percentages
- Do **not** change Suitable≥75 via backtest (only document real tier assignment)
- Do **not** implement full I03 30-minute TailFlow rewrite (optional follow-up)
- Do **not** change daily morning pipeline

> **批注（2026-07-13 review）：原方案方向成立，但不可按原稿直接执行。**
> 本次修订保留原阶段结构，纠正四个实现风险：
> 1. `rank_tier` 与 `tradeability` 必须是两个概念，不能把 A 直接翻译成 Suitable；
> 2. I10 不能在百分位前对全池 raw 做统一缩放（排序不变，分数基本不变），必须缩放百分位贡献；
> 3. I11 只能修复明确的缺失/矛盾数据，合法零值不能自动用中位数覆盖；
> 4. `regime_snapshot` 必须进入 mapper base 和 validator，历史回放至少覆盖 7/7、7/9、7/10、7/13。
>
> **术语锁定：**
> - `absolute_score`：0–100 的 OvernightScore 数值；
> - `rank_tier`：池内相对排名 A/B/C/D，只表达排序，不表达是否可买；
> - `tradeability`：Suitable/Watch/Extended/Avoid，由 Reasoning 根据计算层字段与规则确定；
> - 兼容期可保留输出字段 `tier`，但其语义固定等于 `rank_tier`，不得再与 Suitable/Watch 互换。

---

## Ownership Matrix (lock this first)

| Rule ID | Decision | Owner after convergence | Effect on numbers |
|---------|----------|-------------------------|-------------------|
| I02 | Rewrite doc to match V1.2 code | Code + doc | None (doc only) |
| Tier A/B/C | Single definition: **rank percentile** as currently applied in `main()`；仅表示相对排名 | Code + doc | Remove duplicate assignment; do not map to Tradeability |
| I10-v2 | **Implement in code** (capital-related percentile contributions scaled by regime) | Code | Yes — weak-market capital contribution discount |
| I11 / I11-v2 | **Implement in code** (confirmed missing/contradictory dimension → valid-peer median before percentile) | Code | Yes — rescue bad data without rewriting legitimate zeros |
| VWAP hard filter | Keep as default gate | Code | Unchanged default |
| I14 | **Implement in code** inside `apply_quality_filter` | Code | Yes — weak-market micro-deviation pass |
| I13 zero position | Reasoning-only (no score change) | Reasoning + doc | No score change; clear label |
| I05 Suitable≥75 | Keep as a separate Reasoning rule over `absolute_score`; **do not map it to rank tier A** | Reasoning + doc | No score change; outputs `tradeability` |

**Policy:** If a rule says it changes Score and is not in `score_overnight.py`, it is a bug until implemented or reclassified as Reasoning-only. If docs and code disagree, CI/acceptance must fail; “code wins” is only an emergency runtime interpretation, not a normal maintenance policy.

---

## File Structure Map

### Create
- `.agents/skills/intraday-strategy/tests/test_score_overnight_convergence.py` — unit tests for I10/I11/I14 + tier consistency
- `.agents/skills/intraday-strategy/scripts/score_overnight_lib.py` *(optional extract)* — only if `score_overnight.py` grows unwieldy; prefer keeping functions in `score_overnight.py` unless file exceeds maintainability

### Modify
- `.agents/skills/intraday-strategy/scripts/score_overnight.py` — I10, I11-v2, I14; expose regime inputs; fix dual tier path; emit provenance fields
- `.agents/skills/intraday-strategy/scripts/build_intraday_mapper_base.py` — carry `regime_snapshot` and scoring provenance into base contract
- `.agents/skills/intraday-strategy/scripts/validate_intraday_mapper_annotations.py` — reject compute-owned fields in annotations; validate tradeability behavior
- `.agents/skills/intraday-strategy/scripts/intraday_mapper_json_lib.py` — only if contract propagation helpers need adjustment
- `.agents/skills/intraday-strategy/SKILL.md` — scoring table, filters, ownership
- `.agents/skills/intraday-market-analysis/SKILL.md` — one-line pointer to code-owned score rules
- `memory/INTRADAY_RULES.md` — I02 rewrite; I10/I11/I14 mark code-owned; I13 mark reasoning-only
- `AGENTS.md` / `CLAUDE.md` — optional one line under Memory: score rules must match `score_overnight.py`

### Read-only references
- `memory/intraday/2026-07-07/intraday_verification.md` — VWAP false exclude (星网)
- `memory/intraday/2026-07-09/intraday_verification.md` — Conviction=0 紫光踏空; I14 context
- `.cache/intraday/{date}/market_breadth.json`, `indices.json` — regime inputs for I10/I14

---

## Regime snapshot contract (shared by I10 + I14)

Pass market context into scoring (CLI + library):

```python
# Conceptual shape written into opportunity_pool.json
{
  "regime_snapshot": {
    "available": true,
    "up_ratio_pct": 33.0,       # market_breadth.up_ratio; fallback includes flat_count
    "sz_change_pct": -0.5,      # 深成指 from indices.json (sz399001)
    "i10_active": true,
    "i14_active": true,
    "i10_capital_scale": 0.5,
    "warnings": []
  },
  ...
}
```

**CLI additions to `score_overnight.py`:**

```bash
python score_overnight.py compute_pool_enriched.json --json \
  -o opportunity_pool.json \
  --breadth .cache/intraday/{date}/market_breadth.json \
  --indices .cache/intraday/{date}/indices.json
```

If `--breadth` / `--indices` omitted or invalid: `available=false`,
`i10_active=false`, `i14_active=false`, `capital_scale=1.0` (backward compatible;
log warning on stderr). Missing data must never default to numeric zero because that
would falsely activate weak-market rules.

**Orchestrator:** `run_intraday_pipeline.py` Phase 4 must pass the two cache paths for the same `--date`.

### Exact regime parsing contract

The current production shapes are fixed for this plan:

```json
// market_breadth.json (object)
{
  "up_count": 595,
  "down_count": 4647,
  "flat_count": 30,
  "total": 5272,
  "up_ratio": 11.29,
  "partial": false
}

// indices.json (array; target row)
{
  "code": "sz399001",
  "name": "深证成指",
  "percent": "-1.43%"
}
```

Parsing rules:

1. `up_ratio_pct` first reads numeric `market_breadth.up_ratio`.
2. If `up_ratio` is absent but counts are valid, fallback is
   `up_count / (up_count + down_count + flat_count) * 100`. Do not use
   `up_count / (up_count + down_count)` because production includes flat stocks.
3. `sz_change_pct` matches only `indices[].code == "sz399001"`; `name` may appear
   in diagnostics but is not a normal matching key.
4. Parse `indices[].percent` by removing `%`, `+`, and commas, then converting to float.
5. Any missing/non-numeric field, `market_breadth.partial == true`, missing index row,
   or unreadable file returns an unavailable snapshot with both rules inactive and
   `i10_capital_scale=1.0`; record a machine-readable warning.
6. Unit tests must cover direct `up_ratio`, count fallback including flat stocks,
   malformed percent, missing `sz399001`, and `partial=true`.

> **批注：合同不能停在 `opportunity_pool.json`。**
> `build_intraday_mapper_base.py` 当前只挑选有限的 `pool_summary` 字段；本计划必须显式把
> `regime_snapshot`、I14 skip counters、评分/异常版本写入 base，并增加 validator 测试。
> Reasoning 不能依赖“原始 opportunity_pool 里可能有”这种旁路读取。

Canonical propagation:

```text
market_breadth.json + indices.json
  -> score_overnight.py
  -> opportunity_pool.json.regime_snapshot
  -> intraday_mapper.base.json.pool_summary.regime_snapshot
  -> intraday_mapper.json.pool_summary.regime_snapshot
```

---

## Phase 0: Inventory commit (docs only)

### Task 0: Write ownership matrix into INTRADAY_RULES header

**Files:**
- Modify: `memory/INTRADAY_RULES.md` (top section after lifecycle table)

- [ ] **Step 1: Insert “Code vs Reasoning ownership” block**

Add after the lifecycle table:

```markdown
## Code vs Reasoning ownership (2026-07-13)

| Rule | Owner | Changes OvernightScore? |
|------|-------|-------------------------|
| I02 (formula) | `score_overnight.py` V1.2 | Yes (definition of score) |
| I10-v2 | `score_overnight.py` + regime_snapshot | Yes (capital percentile contributions scaled) |
| I11 / I11-v2 | `score_overnight.py` | Yes (confirmed bad data replaced with valid-peer median) |
| VWAP filter + I14 | `score_overnight.py` `apply_quality_filter` | Yes (eligibility) |
| I13 | Reasoning only | No — forces 观望 / zero size |
| I16 / I17 / I18 | Reasoning only (T+1) | No |

If this table disagrees with code, acceptance fails. Runtime diagnosis may temporarily
treat code behavior as observed truth, but the same PR must restore agreement.
```

- [ ] **Step 2: Commit**

```bash
git add memory/INTRADAY_RULES.md
git commit -m "docs: declare code vs reasoning ownership for overnight rules"
```

---

## Phase 1: I02 + Tier single truth (doc + dead code path)

### Task 1: Align rank-tier assignment to one function, keep Tradeability separate

**Problem:** `compute_scores()` assigns tier by absolute score (75/60/45), then `main()` overwrites with `classify_tier()` rank percentile. SKILL.md still documents absolute thresholds. At the same time, A/B/C and Suitable/Watch are used as if they were aliases even though A currently means Leader Watch and B is the main buy pool.

> **批注：本任务只统一“排名字段”，不决定是否买入。**
> `classify_tier()` 应更名或明确为 `classify_rank_tier()`；兼容字段 `tier` 可以暂留，
> 但最终 JSON 还应提供 `rank_tier`。`tradeability` 继续由 Reasoning 输出。

**Files:**
- Modify: `.agents/skills/intraday-strategy/scripts/score_overnight.py`
- Test: `.agents/skills/intraday-strategy/tests/test_score_overnight_convergence.py`

- [ ] **Step 1: Create test file with failing tier test**

Create `.agents/skills/intraday-strategy/tests/test_score_overnight_convergence.py`:

```python
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "score_overnight.py"


def load_score_mod():
    spec = importlib.util.spec_from_file_location("score_overnight", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_classify_rank_tier_percentiles():
    mod = load_score_mod()
    # rank 1 of 100 -> A (top 10%)
    assert mod.classify_rank_tier(rank=1, pool_size=100) == "A"
    assert mod.classify_rank_tier(rank=10, pool_size=100) == "A"
    assert mod.classify_rank_tier(rank=11, pool_size=100) == "B"
    assert mod.classify_rank_tier(rank=40, pool_size=100) == "B"
    assert mod.classify_rank_tier(rank=41, pool_size=100) == "C"
    assert mod.classify_rank_tier(rank=70, pool_size=100) == "C"
    assert mod.classify_rank_tier(rank=71, pool_size=100) == "D"


def test_compute_scores_sets_only_rank_tier_by_percentile():
    """Rank tier is deterministic and never doubles as tradeability."""
    mod = load_score_mod()
    pool = [
        {
            "code": f"sz{i:06d}",
            "change_pct": "3%",
            "turnover": "8%",
            "volume_ratio": "1.2",
            "source_pool": "turnover",
            "enriched": {
                "real_time": {"price": 10, "high": 11, "low": 9, "vwap": 9.5},
                "money_flow": {
                    "main_net_inflow": str(1.0 + i * 0.1),
                    "super_large_net": "0.5",
                    "large_net": "0.3",
                    "medium_net": "0.1",
                    "small_net": "0.1",
                },
            },
            "technicals": {
                "boll_zone": "upper_half",
                "ma_alignment": "bullish",
                "above_ma5": True,
            },
        }
        for i in range(20)
    ]
    scored = mod.compute_scores(pool)
    for s in scored:
        expected = mod.classify_rank_tier(s["rank"], len(scored))
        assert s.get("rank_tier") == expected
        assert s.get("tier") == expected  # compatibility alias during migration
        assert "tradeability" not in s
```

- [ ] **Step 2: Run test — expect FAIL on absolute-tier mismatch**

```bash
cd E:\ashare-pilot
python -m pytest .agents/skills/intraday-strategy/tests/test_score_overnight_convergence.py::test_compute_scores_sets_only_rank_tier_by_percentile -v
```

Expected: FAIL (absolute tier vs rank tier).

- [ ] **Step 3: Fix `compute_scores` to set rank and apply `classify_rank_tier` once**

In `score_overnight.py` `compute_scores`:
- After sort, set `rank` only
- Set `rank_tier = classify_rank_tier(rank, len(scored))` once
- Set compatibility alias `tier = rank_tier` while downstream consumers migrate
- Remove duplicate reassignment loop in `main()` **or** make `main()` the only place — prefer single place inside `compute_scores` and delete the overwrite loop in `main()`

Also set on each stock for transparency:

```python
stock["rank_tier_rule"] = "rank_percentile_v1"  # top10% A, top40% B, top70% C
stock["rank_tier"] = rank_tier
stock["tier"] = rank_tier  # compatibility alias
stock["absolute_score"] = overnight_score
```

- [ ] **Step 4: Re-run tests — PASS**

```bash
python -m pytest .agents/skills/intraday-strategy/tests/test_score_overnight_convergence.py -v
```

- [ ] **Step 5: Commit**

```bash
git add .agents/skills/intraday-strategy/scripts/score_overnight.py \
        .agents/skills/intraday-strategy/tests/test_score_overnight_convergence.py
git commit -m "fix: single rank-percentile tier assignment in score_overnight"
```

### Task 2: Rewrite I02 + SKILL scoring docs to V1.2

**Files:**
- Modify: `memory/INTRADAY_RULES.md` (I02 row)
- Modify: `.agents/skills/intraday-strategy/SKILL.md` (Scoring Dimensions + Tiers)

- [ ] **Step 1: Replace I02 text**

```markdown
| I02 | **OvernightScore V1.2 (code-owned)**<br>实现: `.agents/skills/intraday-strategy/scripts/score_overnight.py` (`weights_version=V1.2_TrendQuality`)<br>九维百分位: Theme18% Capital18% Tail14% Position9% Risk-10% Intensity9% Conviction9% Consistency5% TrendQuality8%<br>`rank_tier`: **池内 rank 百分位** A=top10% B=top40% C=top70% (非绝对75/60/45门槛)<br>`tradeability`: I01/I05 的 Suitable/Watch/Extended/Avoid，独立于 rank_tier，由 Reasoning 产生 | n | ✅ 与代码对齐 |
```

- [ ] **Step 2: Fix SKILL.md tier line**

Replace:

```markdown
Tiers: A (75+) = Leader Watch, B (60-74) = Premium Candidates, C (45-59) = Early Breakout, D (<45) = Drop.
```

With:

```markdown
Rank tiers (rank percentile within scored pool, `classify_rank_tier`):
A = top 10% (Leader Watch), B = top 10–40% (Premium), C = top 40–70% (Early), D = rest.
Absolute score remains 0–100 for traces; do not use 75/60/45 as hard tier cuts.
Rank tier is not Tradeability. Suitable/Watch/Extended/Avoid is a separate Reasoning output.
```

Also fix Theme Continuity description to match code:

```markdown
| Theme Continuity | 18% | source_pool ordinal (limit_up/turnover/gain_range) blended with inflow sigmoid — **not** theme_ranking heat rank (known gap; do not claim heat rank until coded) |
```

- [ ] **Step 3: Update I01/I05 wording without aliasing it to rank tier** (same file)

Add: “I01/I05 的 Suitable/Watch/Extended/Avoid 是 `tradeability`，可读取
`absolute_score`、`rank_tier`、质量门控和规则触发结果，但不得把 A 固定翻译为 Suitable、
也不得把 B 固定翻译为 Watch。Suitable≥75 暂时保留为 Reasoning 阈值，是否调整属于后续回测计划。”

> **实施纪律：** 即使 `absolute_score>=75` 长期没有产生 Suitable，也不得在本轮把
> 75/60/45 写回 code tier，或用 `rank_tier==A` 代替 Suitable。零 Suitable 是允许的
> 业务结果；是否调整绝对阈值只能由后续回测决定。

- [ ] **Step 4: Commit**

```bash
git add memory/INTRADAY_RULES.md .agents/skills/intraday-strategy/SKILL.md
git commit -m "docs: align I02 and tier semantics with score_overnight V1.2"
```

---

## Phase 2: I11-v2 median replacement (code)

### Task 3: Detect anomalies + replace raw with pool median

**Spec (from INTRADAY_RULES I11-v2):**
1. Classify input as `valid`, `missing`, `partial`, or `contradictory`; **raw=0 alone is not an anomaly**
2. Flag a dimension only when its required source field is missing/non-numeric, or source fields are logically contradictory (e.g. non-zero price/change/turnover but high≤low)
3. Replace only `missing` / `contradictory` raw with **median of valid peer raws for that dimension**
4. If fewer than 3 valid peers exist, do not impute; preserve raw and emit `replacement_skipped=insufficient_valid_peers`
5. Recompute percentiles/scores from adjusted raws
6. Emit `anomaly_flags: [{dim, raw, replacement, reason, valid_peer_count}]` on stock

**Dimensions eligible for I11 v1:** `tail`, `conviction`, `intensity`, `consistency`, `capital`.

> **批注：不能用结果倒推“0 一定是假数据”。**
> `main_net_inflow>0` 且 `super_large_net=0` 可能表示流入主要来自 large orders，
> 也可能是字段缺失；在上游没有 provenance 时只能标记 `suspicious`，不能自动替换。
> 7/9 紫光案例用于验证检测规则，但不能因为次日上涨就直接证明 Conviction=0 是数据错误。

**Explicit acceptance boundary for the 紫光 case:**

- If `super_large_net` is missing/non-numeric, I11 may impute Conviction from valid peers.
- If `super_large_net` is present and is a genuine numeric zero, I11 must preserve zero
  and must **not** reproduce the historical “median rescue”.
- In the genuine-zero case, the miss is classified as a feature-definition problem
  (for example, Conviction may underrepresent large-order structure), not an I11 failure.
- Redesigning Conviction or adding a new feature belongs to the later parameter/feature
  plan; do not widen anomaly detection in this convergence plan to recover one outcome.

**Files:**
- Modify: `score_overnight.py`
- Test: `test_score_overnight_convergence.py`

- [ ] **Step 1: Write failing tests**

```python
def test_i11_missing_conviction_source_replaced_by_valid_peer_median():
    mod = load_score_mod()
    # Build 6 stocks; stock0 is missing super_large_net, peers have valid values.
    base = lambda i, conv_super: {
        "code": f"sz{i:06d}",
        "change_pct": "4%",
        "turnover": "8%",
        "volume_ratio": "1.5",
        "source_pool": "turnover",
        "enriched": {
            "real_time": {"price": 10, "high": 11, "low": 9, "vwap": 9.5},
            "money_flow": {
                "main_net_inflow": "5.0",
                "super_large_net": conv_super,
                "large_net": "1.0",
                "medium_net": "0.5",
                "small_net": "0.2",
            },
        },
        "technicals": {"boll_zone": "upper_half", "ma_alignment": "bullish", "above_ma5": True},
    }
    victim = base(0, None)
    victim["enriched"]["money_flow"].pop("super_large_net")
    pool = [victim] + [base(i, "3.0") for i in range(1, 6)]
    scored = mod.compute_scores(pool)
    victim = next(s for s in scored if s["code"] == "sz000000")
    assert victim.get("anomaly_flags"), "expected I11 flags"
    dims = {f["dim"] for f in victim["anomaly_flags"]}
    assert "conviction" in dims
    flag = next(f for f in victim["anomaly_flags"] if f["dim"] == "conviction")
    assert flag["reason"] == "missing_super_large_net"
    assert flag["valid_peer_count"] == 5


def test_i11_legitimate_zero_conviction_is_not_replaced():
    mod = load_score_mod()
    stock = make_stock(main_net="5.0", super_large_net="0", large_net="5.0")
    scored = mod.compute_scores([stock] + healthy_peer_pool(5))
    victim = next(s for s in scored if s["code"] == stock["code"])
    assert not any(f["dim"] == "conviction" for f in victim.get("anomaly_flags", []))


def test_i11_tail_zero_high_turnover_flagged():
    mod = load_score_mod()
    # high-low contradiction with active trading must be detected from sources,
    # not from extract_tail_raw's fallback value (currently 0.3).
    stock = {
        "code": "sz000001",
        "change_pct": "5%",
        "turnover": "27%",
        "volume_ratio": "2.0",
        "source_pool": "turnover",
        "enriched": {
            "real_time": {"price": 10, "high": 10, "low": 10, "vwap": 9.9},
            "money_flow": {
                "main_net_inflow": "2.0",
                "super_large_net": "1.0",
                "large_net": "0.5",
                "medium_net": "0.2",
                "small_net": "0.1",
            },
        },
        "technicals": {"boll_zone": "upper_half", "ma_alignment": "bullish", "above_ma5": True},
    }
    peers = []
    for i in range(2, 8):
        peers.append({
            "code": f"sz{i:06d}",
            "change_pct": "4%",
            "turnover": "8%",
            "volume_ratio": "1.2",
            "source_pool": "turnover",
            "enriched": {
                "real_time": {"price": 10, "high": 11, "low": 9, "vwap": 9.5},
                "money_flow": {
                    "main_net_inflow": "2.0",
                    "super_large_net": "1.0",
                    "large_net": "0.5",
                    "medium_net": "0.2",
                    "small_net": "0.1",
                },
            },
            "technicals": {"boll_zone": "upper_half", "ma_alignment": "bullish", "above_ma5": True},
        })
    scored = mod.compute_scores([stock] + peers)
    victim = next(s for s in scored if s["code"] == "sz000001")
    assert any(f["dim"] == "tail" for f in victim.get("anomaly_flags", []))
```

- [ ] **Step 2: Run — FAIL**

```bash
python -m pytest .agents/skills/intraday-strategy/tests/test_score_overnight_convergence.py -k i11 -v
```

- [ ] **Step 3: Implement helpers in `score_overnight.py`**

```python
import statistics

def is_present_number(obj: dict, key: str) -> bool:
    if key not in obj or obj[key] in (None, "", "-"):
        return False
    try:
        float(str(obj[key]).replace("+", "").replace("%", "").replace(",", ""))
        return True
    except (TypeError, ValueError):
        return False


def detect_dim_anomaly(dim: str, raw: float, stock: dict) -> str | None:
    """Return reason string if anomalous, else None."""
    turnover = parse_float(stock.get("turnover", "0%"))
    enriched = stock.get("enriched", {})
    mf = enriched.get("money_flow", {})
    rt = enriched.get("real_time", {})
    if dim == "conviction" and not is_present_number(mf, "super_large_net"):
        return "missing_super_large_net"
    if dim in ("intensity", "capital") and not is_present_number(mf, "main_net_inflow"):
        return "missing_main_net_inflow"
    if dim == "consistency" and any(
        not is_present_number(mf, key)
        for key in ("super_large_net", "large_net", "medium_net", "small_net")
    ):
        return "partial_money_flow_tiers"
    if dim == "tail":
        high = parse_float(rt.get("high"))
        low = parse_float(rt.get("low"))
        price = parse_float(rt.get("price"))
        if price > 0 and turnover > 20 and high <= low:
            return "intraday_range_contradiction"
    return None


def apply_i11_median_replacement(raws_by_index: dict, pool: list) -> dict:
    """raws_by_index: {i: {dim: raw}}; mutates copy; attaches flags on pool[i]."""
    dims = list(next(iter(raws_by_index.values())).keys())
    adjusted = {i: dict(raws_by_index[i]) for i in raws_by_index}
    flags = {i: [] for i in raws_by_index}

    for dim in dims:
        # median of non-anomalous
        clean = []
        for i in raws_by_index:
            reason = detect_dim_anomaly(dim, raws_by_index[i][dim], pool[i])
            if not reason:
                clean.append(raws_by_index[i][dim])
        med = statistics.median(clean) if len(clean) >= 3 else None
        for i in raws_by_index:
            reason = detect_dim_anomaly(dim, raws_by_index[i][dim], pool[i])
            if reason and med is not None:
                flags[i].append({
                    "dim": dim,
                    "raw": round(raws_by_index[i][dim], 6),
                    "replacement": round(med, 6),
                    "reason": reason,
                    "valid_peer_count": len(clean),
                })
                adjusted[i][dim] = med
            elif reason:
                flags[i].append({
                    "dim": dim,
                    "raw": round(raws_by_index[i][dim], 6),
                    "replacement": None,
                    "reason": reason,
                    "valid_peer_count": len(clean),
                    "replacement_skipped": "insufficient_valid_peers",
                })

    for i in raws_by_index:
        pool[i]["anomaly_flags"] = flags[i]
        pool[i]["i11_flagged"] = bool(flags[i])
        pool[i]["i11_applied"] = any(f.get("replacement") is not None for f in flags[i])
    return adjusted
```

Wire into `compute_scores` **after** building `raws`, **before** percentile_rank:

```python
raws = apply_i11_median_replacement(raws, pool)
# rebuild all_raws from adjusted raws
```

Add a pool-level guard before per-stock imputation:

```python
# If an entire upstream family is unavailable, do not manufacture a full
# cross-section from medians. Record outage and let existing fallback policy run.
if not money_flow_available(pool):
    skip_i11_money_flow_dims = True
```

- [ ] **Step 4: Tests PASS**

- [ ] **Step 5: Commit**

```bash
git add .agents/skills/intraday-strategy/scripts/score_overnight.py \
        .agents/skills/intraday-strategy/tests/test_score_overnight_convergence.py
git commit -m "feat: implement I11-v2 median replacement in overnight scoring"
```

### Task 4: Doc I11 as code-owned

**Files:** `memory/INTRADAY_RULES.md`

- [ ] **Step 1:** Update I11 and I11-v2 rows: status note “已实现于 score_overnight.apply_i11_median_replacement；字段 anomaly_flags / i11_flagged / i11_applied；flagged 不等于成功替换”

- [ ] **Step 2: Commit**

```bash
git add memory/INTRADAY_RULES.md
git commit -m "docs: mark I11-v2 as implemented in score_overnight"
```

---

## Phase 3: I10-v2 capital scale (code)

### Task 5: Regime capital scale applied to capital-family percentile contributions

**Spec (I10-v2, simplified for code):**

Activation: `up_ratio_pct < 40` **and** `sz_change_pct < 0`.

| up_ratio_pct | capital_scale |
|-------------:|---------------|
| ≥40 or sz≥0 | 1.0 (inactive) |
| 20–40 | 0.5 |
| 10–20 | 0.25 |
| <10 | 0.0 |

Apply scale **after percentile calculation** to weighted contributions for dims:
`capital`, `intensity`, `conviction`, `consistency`.

```python
capital_contrib = capital_pct * W["capital_continuity"] * capital_scale
intensity_contrib = intensity_pct * W["intensity"] * capital_scale
conviction_contrib = conviction_pct * W["conviction"] * capital_scale
consistency_contrib = consistency_pct * W["consistency"] * capital_scale
```

Do **not** renormalize remaining weights: I10 is an absolute confidence discount, so the
score total must fall when the regime weakens. Keep each dimension's unscaled percentile
and scaled contribution in `score_trace` for audit.

> **批注（替代原稿的 raw scaling）：** 对整个池的 raw 同乘正数不会改变相对排序和
> percentile，因此基本不会改变 OvernightScore；scale=0 还会触发零方差 50 分位。
> I10 的语义是“弱市下资金因子的预测贡献下降”，必须作用于 contribution。

**Exclude (optional v1 skip):** “主线≥4★ 维持×1.0” requires theme heat stars not in pool — **defer** star exception to Reasoning; document as known gap.

**Files:**
- Modify: `score_overnight.py` (`load_regime_snapshot`, `scaled_contribution`)
- Modify: `run_intraday_pipeline.py` (pass breadth/indices)
- Test: `test_score_overnight_convergence.py`

- [ ] **Step 1: Failing tests**

```python
def test_i10_scale_table():
    mod = load_score_mod()
    assert mod.i10_capital_scale(up_ratio_pct=50, sz_change_pct=-1) == 1.0  # not active
    assert mod.i10_capital_scale(up_ratio_pct=30, sz_change_pct=-1) == 0.5
    assert mod.i10_capital_scale(up_ratio_pct=15, sz_change_pct=-1) == 0.25
    assert mod.i10_capital_scale(up_ratio_pct=5, sz_change_pct=-1) == 0.0
    assert mod.i10_capital_scale(up_ratio_pct=15, sz_change_pct=0.5) == 1.0  # sz not < 0


def test_i10_reduces_capital_contribution_when_active():
    mod = load_score_mod()
    pool = healthy_pool(10)
    normal = by_code(mod.compute_scores(clone(pool), regime={
        "up_ratio_pct": 50, "sz_change_pct": 1, "i10_capital_scale": 1.0,
    }))
    weak = by_code(mod.compute_scores(clone(pool), regime={
        "up_ratio_pct": 12, "sz_change_pct": -1, "i10_capital_scale": 0.25,
    }))
    for code in normal:
        assert weak[code]["score_trace"]["capital_continuity"]["pct"] == normal[code]["score_trace"]["capital_continuity"]["pct"]
        assert weak[code]["score_trace"]["capital_continuity"]["contrib"] <= normal[code]["score_trace"]["capital_continuity"]["contrib"]
        assert weak[code]["overnight_score"] <= normal[code]["overnight_score"]


def test_i10_zero_scale_zeros_capital_family_contributions():
    mod = load_score_mod()
    scored = mod.compute_scores(healthy_pool(10), regime={
        "up_ratio_pct": 5, "sz_change_pct": -1, "i10_capital_scale": 0.0,
    })
    for stock in scored:
        for dim in ("capital_continuity", "intensity", "conviction", "consistency"):
            assert stock["score_trace"][dim]["contrib"] == 0.0
```

Test helpers such as `healthy_pool`, `clone`, and `by_code` must be real Python
functions in the test file; do not leave placeholder syntax in executable examples.

- [ ] **Step 2: Implement**

```python
def i10_capital_scale(up_ratio_pct: float, sz_change_pct: float) -> float:
    if up_ratio_pct >= 40 or sz_change_pct >= 0:
        return 1.0
    if up_ratio_pct >= 20:
        return 0.5
    if up_ratio_pct >= 10:
        return 0.25
    return 0.0


def parse_regime_from_files(breadth_path, indices_path) -> dict:
    try:
        breadth = read_json_object(breadth_path)
        indices = read_json_array(indices_path)
        if breadth.get("partial") is True:
            return unavailable_regime("market_breadth_partial")

        if is_finite_number(breadth.get("up_ratio")):
            up_ratio_pct = float(breadth["up_ratio"])
        else:
            up = require_nonnegative_number(breadth, "up_count")
            down = require_nonnegative_number(breadth, "down_count")
            flat = require_nonnegative_number(breadth, "flat_count")
            total = up + down + flat
            if total <= 0:
                return unavailable_regime("market_breadth_total_zero")
            up_ratio_pct = up / total * 100

        sz = next((row for row in indices if row.get("code") == "sz399001"), None)
        if sz is None:
            return unavailable_regime("sz399001_missing")
        sz_change_pct = parse_required_percent(sz.get("percent"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return unavailable_regime(f"regime_parse_error:{type(exc).__name__}")

    scale = i10_capital_scale(up_ratio_pct, sz_change_pct)
    return {
        "available": True,
        "up_ratio_pct": round(up_ratio_pct, 2),
        "sz_change_pct": round(sz_change_pct, 2),
        "i10_active": scale < 1.0,
        "i14_active": up_ratio_pct < 35,
        "i10_capital_scale": scale,
        "warnings": [],
    }


def scaled_contribution(percentile: float, weight: float, scale: float) -> float:
    return percentile * weight * scale
```

Order in `compute_scores`:
1. extract raws  
2. I11 median replace  
3. compute percentiles  
4. I10 scale capital-family contributions  
5. weighted sum without renormalization  

- [ ] **Step 3: CLI + pipeline**

`main()`:
```python
parser.add_argument("--breadth")
parser.add_argument("--indices")
# build regime; put into output["regime_snapshot"]
# pass regime into compute_scores
```

`run_intraday_pipeline.py` score_cmd append:
```python
"--breadth", str(out_dir / "market_breadth.json"),
"--indices", str(out_dir / "indices.json"),
```

- [ ] **Step 4: Tests PASS + dry-run on all four fixed cache dates**

```bash
python -m pytest .agents/skills/intraday-strategy/tests/test_score_overnight_convergence.py -k i10 -v
# required historical replay; always write trial files, never overwrite canonical cache
python .agents/skills/intraday-strategy/scripts/score_overnight.py .cache/intraday/2026-07-09/compute_pool_enriched.json --json \
  --breadth .cache/intraday/2026-07-09/market_breadth.json \
  --indices .cache/intraday/2026-07-09/indices.json \
  -o .cache/intraday/2026-07-09/opportunity_pool.i10trial.json
```

Repeat for `2026-07-07`, `2026-07-10`, and `2026-07-13`. Assert:
- 7/9: `sz_change_pct>0`, I10 inactive, score output matches the no-regime path except provenance fields;
- 7/7 and 7/13: I10 active, every capital-family contribution is non-increasing;
- 7/10: breadth is high, so I10 remains inactive under the current two-condition rule; record this explicitly rather than claiming it handles the 7/10 reversal pattern.

- [ ] **Step 5: Commit**

```bash
git add .agents/skills/intraday-strategy/scripts/score_overnight.py \
        .opencode/scripts/run_intraday_pipeline.py \
        .agents/skills/intraday-strategy/tests/test_score_overnight_convergence.py
git commit -m "feat: implement I10-v2 capital scale in overnight scoring"
```

### Task 6: Doc I10 code-owned + star exception gap

**Files:** `memory/INTRADAY_RULES.md`, `SKILL.md`

- [ ] Note: 主线≥4★ ×1.0 例外 **未编码**，Reasoning 可 overlay 仓位，不得声称分数已豁免  
- [ ] Commit: `docs: mark I10-v2 code-owned; document star-exception gap`

---

## Phase 4: VWAP + I14 (code)

### Task 7: I14 exemption inside `apply_quality_filter`

**Spec:**
- Default: `price < vwap` → exclude (`quality-filter`)
- When `i14_active` (`up_ratio_pct < 35`):
  - If deviation `< 3` and `quick_score >= 70` → **eligible for scoring**, with `i14_exemption: "watch"`
  - Else if deviation `< 5` and `quick_score >= 80` → **eligible for scoring**, with `i14_exemption: "cautious_hold"`
- `quick_score`: use only the stock field produced by `build_scan_pool.py` and carried
  through enrichment. If missing/non-numeric, I14 cannot fire (no false pass). This
  plan explicitly forbids a `change_pct + volume_ratio` or other invented proxy.

> **批注：I14 只豁免 quality filter，不直接改 `rank_tier`。**
> `watch` / `cautious_hold` 是 Reasoning 必须消费的 tradeability ceiling：
> `watch` 最终不得高于 Watch，`cautious_hold` 最终不得高于谨慎持有。
> 不能仅写一个字段后仍让普通 Tier 规则把它升级为正常持有。

**Observed coverage before implementation:** the existing enriched compute pools for
`2026-07-07`, `2026-07-09`, `2026-07-10`, and `2026-07-13` each contain numeric
`quick_score` for 120/120 stocks. This supports the current contract but does not remove
the missing-field guard. Acceptance must report the skip count and expect zero on these
four fixtures; a non-zero count is a pipeline/data-quality warning, not permission to
invent a proxy.

**Files:**
- Modify: `apply_quality_filter(pool, regime=None)`
- Test: unit tests with synthetic price/vwap/quick_score

Revise the return contract from a single VWAP-missing integer to a stats object:

```python
passed, filtered, quality_stats = apply_quality_filter(pool, regime)
# quality_stats = {
#   "vwap_missing_count": 0,
#   "i14_applied_count": 0,
#   "i14_skipped_no_quick_score": 0,
# }
```

Update `main()` and JSON serialization in the same task; keep the legacy root
`vwap_missing_count` alias temporarily if an existing consumer requires it.

- [ ] **Step 1: Failing tests**

```python
def test_vwap_hard_exclude_without_i14():
    mod = load_score_mod()
    stock = {
        "code": "sz1",
        "quick_score": 90,
        "enriched": {"real_time": {"price": 9.7, "vwap": 10.0}},
    }
    passed, filtered, _ = mod.apply_quality_filter([stock], regime={"up_ratio_pct": 50})
    assert len(passed) == 0 and len(filtered) == 1


def test_i14_micro_deviation_passes():
    mod = load_score_mod()
    stock = {
        "code": "sz1",
        "quick_score": 75,
        "enriched": {"real_time": {"price": 9.8, "vwap": 10.0}},  # 2% below
    }
    passed, filtered, _ = mod.apply_quality_filter(
        [stock], regime={"up_ratio_pct": 33}
    )
    assert len(passed) == 1
    assert passed[0].get("i14_exemption") == "watch"


def test_i14_missing_quick_score_does_not_pass():
    mod = load_score_mod()
    stock = {"code": "sz000001", "enriched": {"real_time": {"price": 9.8, "vwap": 10.0}}}
    passed, filtered, stats = mod.apply_quality_filter(
        [stock], regime={"up_ratio_pct": 33, "i14_active": True}
    )
    assert not passed and len(filtered) == 1
    assert stats["i14_skipped_no_quick_score"] == 1
```

- [ ] **Step 2: Implement exemption branch**

- [ ] **Step 3: Tests PASS**

- [ ] **Step 4: Commit**

```bash
git commit -m "feat: implement I14 VWAP micro-deviation exemption in quality filter"
```

### Task 8: Doc VWAP/I14 code-owned

- [ ] Update I14 row: 已实现于 `apply_quality_filter`; 字段 `i14_exemption`
- [ ] SKILL 持仓质量过滤器表增加 I14 两行，并写明其是 tradeability ceiling
- [ ] Commit: `docs: mark I14 as implemented in quality filter`

### Task 8.5: Propagate and validate the compute contract

**Files:**
- Modify: `build_intraday_mapper_base.py`
- Modify: `validate_intraday_mapper_json.py`
- Test: mapper base/validator tests (create focused test file if none exists)

- [ ] Copy the following root fields from `opportunity_pool.json` into
  `intraday_mapper.base.json.pool_summary`:
  - `regime_snapshot`
  - `scoring_policy_version`
  - `data_quality_summary`
  - `i14_skipped_no_quick_score`
- [ ] Preserve stock-level `rank_tier`, `absolute_score`, `anomaly_flags`,
  `i11_flagged`, `i11_applied`, and `i14_exemption` through base → mapper → overnight strategy
  where the target view exposes the stock.
- [ ] Validator requires `regime_snapshot` whenever pipeline sources include
  breadth and indices; compatibility mode without those CLI arguments must emit
  an explicit `regime_snapshot.available=false` rather than omit the object.
- [ ] Add a round-trip test proving the above fields survive publication.
- [ ] Commit: `feat: propagate overnight scoring regime and provenance`

---

## Phase 5: Reasoning skill constraints (no silent score edits)

### Task 9: Harden `intraday-strategy` SKILL Reasoning rules

**Files:** `.agents/skills/intraday-strategy/SKILL.md`

- [ ] **Step 1: Add “Score immutability” section**

```markdown
## Score immutability

- Never recompute OvernightScore, tiers, or quality/floor flags in annotations.
- I10/I11/I14 effects appear only via opportunity_pool / base.json fields
  (`regime_snapshot`, `anomaly_flags`, `i14_exemption`, `rank_tier`, `absolute_score`).
- Rank tier and Tradeability are independent. Never translate A→Suitable or B→Watch mechanically.
- When `i14_exemption=watch`, final tradeability cannot exceed Watch; when
  `i14_exemption=cautious_hold`, direction cannot exceed 谨慎持有.
- I13 (extreme weak zero position) is Reasoning-only: set all directions to 观望
  and position_cap to 0 when breadth up_ratio < 15%; do not claim scores changed.
- If annotations disagree with base numeric fields, validation / review treats base as truth.
```

- [ ] **Step 2: Commit**

```bash
git commit -m "docs: score immutability for intraday-strategy reasoning"
```

### Task 10: Required annotation validator check

**Files:** `validate_intraday_mapper_annotations.py`

- [ ] **Step 1:** Reject compute-owned fields in annotations (`overnight_score`,
  `absolute_score`, `tier`, `rank_tier`, `score_trace`, quality/floor flags) rather
  than accepting duplicate numeric truth.
- [ ] **Step 2:** Validate I13: when `up_ratio_pct<15`, every annotation direction
  must be `观望` and position cap must resolve to zero.
- [ ] **Step 3:** Validate I14 ceilings described above.
- [ ] **Step 4:** Add negative tests for silent score duplication, I13 violation,
  and I14 upgrade; commit validator and tests.

---

## Phase 6: Acceptance

### Task 11: Convergence checklist (manual)

- [ ] Grep rules vs code:

```bash
# Should NOT find old 6-factor I02 formula as active truth
rg "主线地位×0.25" memory/INTRADAY_RULES.md
# Should find implementation symbols
rg "apply_i11_median|i10_capital_scale|i14_exemption|rank_tier|absolute_score" .agents/skills/intraday-strategy
```

- [ ] Run full unit file:

```bash
python -m pytest .agents/skills/intraday-strategy/tests/test_score_overnight_convergence.py -v
```

- [ ] Re-score four fixed historical days: `2026-07-07`, `2026-07-09`,
  `2026-07-10`, `2026-07-13`; write only `*.convergence-trial.json`
- [ ] Produce a compact machine-readable comparison for each day containing:
  activation flags, score/rank deltas, quality-filter additions/removals,
  anomaly replacements/skips, opportunity-pool additions/removals, and final
  tradeability/direction changes after annotation validation
- [ ] Confirm `regime_snapshot` survives opportunity pool → base → mapper
- [ ] Confirm I10 active cases have non-increasing capital-family contributions;
  confirm inactive 7/9 is numerically unchanged except provenance fields
- [ ] Confirm legitimate zero money-flow dimensions are not imputed, while
  missing/contradictory synthetic cases are imputed only with ≥3 valid peers
- [ ] For the 7/9 紫光 case, record whether `super_large_net` was missing or genuine
  zero; accept “no median rescue” when it was genuine zero and route the case to the
  later feature plan instead of weakening I11's data-quality boundary
- [ ] Confirm I14 exemptions cannot be upgraded past their Reasoning ceiling
- [ ] Confirm `i14_skipped_no_quick_score == 0` on all four fixed fixtures
  (current observed coverage is 120/120 each); if not zero, surface data warning and
  do not substitute a proxy
- [ ] Confirm no code-tier path contains 75/60/45 and no Reasoning path mechanically
  maps rank A to Suitable; accept zero Suitable outcomes in historical replay
- [ ] Confirm I13 still **not** in score_overnight (Reasoning-only)
- [ ] Run existing mapper/base/overnight validators and renderer smoke tests
- [ ] Write short note at bottom of this plan file: “Convergence complete YYYY-MM-DD” with commit hashes

- [ ] **Final commit** if checklist edits: `docs: convergence acceptance notes`

---

## Out of scope → next plan (parameter tuning)

Only after acceptance:
1. Dimension IC vs T+1 open/10:00 returns on tradeable names
2. Weight search under fixed I10/I11/I14
3. Optional: encode theme_ranking heat into Theme Continuity
4. Optional: I03 true 30m tail flow

---

## Risk notes

| Risk | Mitigation |
|------|------------|
| I10 star-exception missing | Document; Reasoning position overlay only |
| I10 raw scaling leaves percentiles unchanged | Scale percentile contributions, assert score delta on weak historical days |
| Theme raw still contains a 30% capital blend not covered by I10 | Record as explicit known gap; do not claim all capital influence is zero when scale=0 |
| quick_score missing → I14 never fires | Log `i14_skipped_no_quick_score` count in output |
| quick_score proxy silently changes I14 meaning | No proxy in this plan; missing means skip + warning |
| Median replace over-smooths or rewrites legitimate zeros | Require missing/contradictory provenance and ≥3 valid peers; keep anomaly flags for audit |
| Genuine Conviction zero still misses a winner | Treat as later feature-engineering evidence, not an I11 anomaly |
| Rank tier vs Tradeability conflation | Separate `rank_tier`, `absolute_score`, and `tradeability`; validator rejects aliasing shortcuts |
| Pipeline callers forget --breadth | Default scale 1.0 + stderr warning |
| Regime parser drifts across callers | Pin `up_ratio`, count fallback including flat, and `sz399001.percent` in one parser with tests |
| Missing regime fields default to zero | Return `available=false`, keep I10/I14 inactive, and emit warning |
| Root regime field lost in mapper base | Required round-trip contract test |

---

## Self-review (plan quality)

| Spec item | Task |
|-----------|------|
| I02 dual truth | Task 1–2 |
| I10 dual truth | Task 5–6 |
| I11 dual truth | Task 3–4 |
| VWAP/I14 dual truth | Task 7–8 |
| Contract propagation | Task 8.5 |
| Tier vs Tradeability separation | Task 1–2, Task 9–10 |
| Historical behavior verification | Task 11 (four fixed dates) |
| No weight tuning | Non-goals |
| Reasoning cannot invent scores | Task 9–10 |
| Tests first | Tasks 1,3,5,7 |

No TBD placeholders for the four dual-truth items. Star-exception and theme-heat gap called out as known deferrals, not silent omissions.

---

## Phased delivery contract

> **批注：Task 8.5 + Task 10 扩大了实现范围，但属于消除双真相的必要工作。**
> 不要求一次性大提交；必须按以下 Phase 独立交付、验证和提交，前一阶段通过后再进入下一阶段。

| Delivery phase | Scope | Exit condition |
|---|---|---|
| A | Task 0–2: ownership, `rank_tier` / `tradeability` separation | tier tests + docs agree; no 75/60/45 code tier |
| B | Task 3–4: I11 data-quality handling | missing/contradictory tests pass; genuine zero preserved |
| C | Task 5–6: regime parser + I10 contribution scaling | parser matrix passes; active scores decrease; inactive scores stable |
| D | Task 7–8: I14 eligibility exemption | quick-score coverage/skip counters and ceilings pass |
| E | Task 8.5 + 9–10: base propagation + validators | round-trip and negative validator tests pass |
| F | Task 11: four-date replay and final convergence acceptance | machine comparison produced; all contracts validated |

Do not mark docs “implemented” ahead of the corresponding phase's code and tests.

---

## Execution handoff

Plan saved to `docs/superpowers/plans/2026-07-13-rule-code-dual-truth-convergence.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
2. **Inline Execution** — this session with executing-plans and checkpoints  

Which approach?
