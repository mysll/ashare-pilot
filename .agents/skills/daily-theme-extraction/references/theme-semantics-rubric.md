# Daily Theme semantic rubric

Use only the evidence and optional structured `market_signals` supplied for
each canonical theme. Reject false positives by excluding their refs from
`accepted_refs`; do not invent themes or evidence.

## Semantic fields

- `confidence`: overall theme-to-accepted-evidence confidence, 0-100. Values
  below 60 remain in the formal output but Python marks them discarded.
- `attention_direction`: use exactly one of:
  - `bullish`: evidence is consistently positive.
  - `panic`: evidence is consistently negative or shows a broad sell-off.
  - `mixed`: positive and negative evidence materially conflict.
  - `neutral`: evidence has no meaningful directional effect.
  - `unknown`: supplied evidence is insufficient to judge direction.

  Never use `bearish` for `attention_direction`; use `panic` for consistently
  negative evidence. `bearish` is valid only for `policy_polarity`. Do not
  change `panic` to `mixed` unless positive and negative signals both exist.
- `market_action`: 0-100. Use supplied price, volume, limit-up, commodity, or
  structured theme market signals. Strong positive confirmation is high;
  broad sell-off or limit-down evidence is low. Do not infer unavailable
  market data.
- `emotion_raw`: direction-independent attention intensity, 0-100.
- `capital`: 0-100 only with explicit inflow/outflow evidence. Use 45 when no
  valid capital evidence exists.

## Policy

`policy_tier` is one of:

- `none`
- `local`
- `ministry`
- `state_council`
- `national_strategy`

`policy_polarity` is `bullish`, `neutral`, or `bearish`. When the tier is
`none`, use neutral polarity and a null `policy_ref`. Otherwise `policy_ref`
must be one accepted canonical ref. Judge the policy's effect on the theme,
not the tone of the article.

## Catalyst

Default to null. A catalyst may be declared only when it is fresh, same-day,
nameable, bullish or neutral, and traceable to one accepted ref. Use:

```json
{
  "type": "landmark_ipo",
  "evidence_ref": "news#12"
}
```

Allowed types:

- `landmark_ipo`: first or bellwether A-share industry listing
- `first_national_policy`: first-ever national strategy or policy
- `bellwether_product_or_breakthrough`: flagship launch or industry-level
  technology breakthrough by a bellwether
- `major_national_contract`: national-level or far-above-expectation major
  contract

Routine contracts, minor launches, stale policy, generic positive headlines,
or sold-off events do not qualify. Python applies a heat floor to at most two
qualified catalysts and performs the stable selection; the LLM never writes a
promotion score.

## Reason

Write one concise, auditable sentence, no more than 240 characters. State why
the accepted evidence supports the semantic scores. Do not include formulas,
trade recommendations, stock selection, or Step 3 Direction.
