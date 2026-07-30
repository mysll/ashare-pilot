---
name: manage-expert-rules
description: Interview the user and safely list, inspect, add, or physically remove Expert Rules in memory/EXPERT_RULES.md. Use when the user wants to maintain manually authorized natural-language rules for DAILY_STRATEGY or OVERNIGHT_STRATEGY, including requests to add a trading constraint, inspect current expert rules, or delete one.
---

# Manage Expert Rules

Manage Expert Rules through the project CLI. Never edit
`memory/EXPERT_RULES.md` directly.

Expert Rules are immediately active after addition. They are not learned
rules, have no evidence lifecycle, and are not evaluated for effectiveness.
`OPERATION_GUIDE` does not consume them.

## Choose the operation

- List: call `automation rules expert list`.
- Show: call `automation rules expert show E###`.
- Add: follow the complete interview and confirmation workflow below.
- Remove: follow the destructive confirmation workflow below.
- Modify: remove the existing rule, then add a new rule with a new ID. There
  is no in-place update.

## Add a rule

### 1. Load authoritative context

Read completely:

```text
references/system-capabilities.md
memory/EXPERT_RULES.md
memory/RULE_GOVERNANCE.md
```

Then read learned rules relevant to the requested consumers:

- `DAILY_STRATEGY`: `memory/RULES.md` and `memory/SHARED_RULES.md`
- `OVERNIGHT_STRATEGY`: `memory/INTRADAY_RULES.md` and
  `memory/SHARED_RULES.md`

Do not infer a system capability from general knowledge or repository code.
The capability reference is a closed whitelist: absent means unsupported.

### 2. Interview one decision at a time

Ask one question per turn until all seven contract fields are unambiguous:

```text
name
applies_to
decision_layer
condition
exclusions
action
```

The CLI assigns `id`. Use only these decision layers:

```text
RISK_CONTROL
REGIME
ELIGIBILITY
ENTRY_POSITION
RANKING
```

Translate the user's intent into precise natural language, but never invent a
threshold, field, exception, or action. Ask when meaning could change.

### 3. Check system support

Map every atomic condition and action to the capability reference:

- verify the exact source field exists for every selected consumer;
- verify it is available at that consumer's decision time;
- verify the requested action is writable by that consumer;
- preserve missing-data behavior and higher-level system constraints.

If any part is unsupported, stop without calling `add`. Name the unsupported
data or interface and the affected consumer. Do not substitute a proxy metric
or silently narrow the rule.

### 4. Check duplicates and conflicts

Compare the draft with the complete current Expert Rule set and relevant
learned rules.

- Semantic duplicate of an Expert Rule: reject and cite its ID.
- Conflict with an Expert Rule: do not overwrite; ask the user to remove the
  old rule or clarify non-overlapping conditions.
- Same-layer conflict with a learned rule: allowed, but disclose every
  learned-rule ID the Expert Rule will override.
- Conflict with a higher decision layer or system invariant: reject.

Decision-layer order is:

```text
system invariants
RISK_CONTROL
REGIME
ELIGIBILITY
ENTRY_POSITION
RANKING
```

Expert Rules outrank learned rules only within the same layer. If two Expert
Rules remain ambiguous at the same layer, the strategy must produce
`NO_TRADE_CONFLICT`; do not create the conflicting rule.

### 5. Validate and preview

Build a JSON draft containing exactly:

```json
{
  "name": "string",
  "applies_to": ["DAILY_STRATEGY"],
  "decision_layer": "ENTRY_POSITION",
  "condition": "string",
  "exclusions": [],
  "action": "string"
}
```

Run:

```bash
uv run --frozen ashare-pilot automation rules expert add \
  --input <draft.json> --dry-run
```

Show the normalized preview to the user, including:

- allocated ID;
- every contract field;
- capability mapping for each condition and action;
- any learned rules that will be overridden.

Ask for explicit confirmation of this exact version. Silence, an ambiguous
reply, or any field change invalidates confirmation. After a change, rerun
dry-run and show the complete preview again.

### 6. Add only after confirmation

After explicit confirmation, run:

```bash
uv run --frozen ashare-pilot automation rules expert add \
  --input <draft.json>
```

Report the added ID. Do not claim semantic capability was checked by the CLI;
the Skill performed that check.

## Remove a rule

First run:

```bash
uv run --frozen ashare-pilot automation rules expert show E###
```

Show the complete rule and ask for explicit deletion confirmation. Without
confirmation, do not continue. After confirmation run:

```bash
uv run --frozen ashare-pilot automation rules expert remove E### --yes
```

Deletion is physical and irreversible. It preserves no rule body, tombstone,
version, author, or removal reason. Historical strategy outputs are not
rewritten, and IDs are never reused.

## Constraints

- Maximum current Expert Rules: 20.
- Never add or remove a rule without explicit confirmation.
- Never add `OPERATION_GUIDE` to `applies_to`.
- Never add status, version, author, evidence, time, or evaluation fields.
- Never calculate or report Expert Rule effectiveness.
- Never place orders or turn qualitative tiers into numeric position sizing.
- Use CLI JSON output as the source of truth after a write.
