# Domain-Specific Skill: Guardrail Metric Pairing

**Loaded by:** Findings Validator, Opportunity Identifier.
**Purpose:** Define the general rules for what makes a guardrail pairing meaningful in our CPG company, and how to interpret movement on a paired counter-metric when the primary metric moves.

This is the **methodology** skill. The **specific pairings** — which primary metric pairs with which guardrail in which functional domain — live in the relevant functional-domain context document under "Guardrail metric pairings." This skill explains the logic; the context documents fill in the table.

For the validation procedure itself, see [validation/guardrail-pairing-check.md](../validation/guardrail-pairing-check.md), which is the runtime check.

## What makes a pair a meaningful guardrail

A counter-metric is a meaningful guardrail when it satisfies three conditions:

1. **It moves in response to the same operational levers** that move the primary metric. If a recommended action would push the primary one way, the paired metric must be one that the same action plausibly affects.
2. **The direction of "good" on the paired metric can conflict with the direction of "good" on the primary.** Pairings exist to catch trade-offs; if both metrics improve together under every plausible action, the pairing surfaces nothing useful.
3. **The paired metric is observable at the same scope and grain as the primary.** A primary metric at the SKU × week level needs a paired metric also computable at SKU × week. Mismatched grains make the comparison uninterpretable.

A pairing that fails any of these is not a guardrail — it's noise. The functional-domain context documents should not list metric pairs that fail these conditions.

## Patterns of guardrail pairing

The most common pairing patterns within our CPG company:

### Pattern 1 — Volume vs. margin / unit economics
The most universal CPG trade-off. Volume gains that come from discounting or trade-spend escalation can compress margin per unit. Pairings of this shape:

- *Sales volume ↔ gross margin per case*
- *Promotional lift ↔ promo ROI*
- *Account-level volume ↔ trade-spend-as-percent-of-revenue*

### Pattern 2 — Service level vs. cost
Better customer service often comes at higher operating cost. Pairings:

- *Fill rate ↔ inventory carrying cost / days-of-supply*
- *On-time-in-full ↔ expedite freight cost*
- *Delivery-window precision ↔ logistics labor hours*

### Pattern 3 — Throughput vs. quality
Operations efficiency can sacrifice quality. Pairings:

- *Production throughput ↔ first-pass yield*
- *OEE — performance component ↔ OEE — quality component*
- *Changeover time reduction ↔ defect rate within first run of new SKU*

### Pattern 4 — Acquisition vs. retention
Growth at the top of the funnel can come at the cost of retention quality. Pairings:

- *New-account acquisition rate ↔ first-90-day retention*
- *New-SKU shelf placement count ↔ velocity per point on new SKUs*
- *Promotional reach ↔ repeat-purchase rate among promo-exposed households*

### Pattern 5 — Aggregate vs. mix
Aggregate metric improvements can mask within-mix problems. Pairings:

- *Aggregate revenue ↔ same-account revenue growth* (catches portfolio mix shift)
- *Aggregate fill rate ↔ minimum DC fill rate* (catches a small-DC service collapse hidden by network-wide average)
- *Aggregate promo lift ↔ promo lift dispersion across events* (catches a few big-lift events masking many flat ones)

This pattern overlaps with the Simpson's-Paradox check ([simpsons-paradox-check.md](../analytical/simpsons-paradox-check.md)) — the guardrail pairing is the procedural way to make the mix-shift check routine.

## Rules for the functional-domain context documents

When a functional-domain context document populates its "Guardrail metric pairings" section, each entry should specify:

```
Primary metric: <name>
Paired guardrail: <name>
Why it pairs: <one-sentence rationale referencing the relevant pattern above>
Direction of concern: <e.g., "primary up + paired down → trade-off">
Scope where the pairing applies: <e.g., "account × week" / "SKU × month" / "DC × week">
```

Multiple pairings per primary are fine and often appropriate (e.g., volume might pair with both margin AND trade-spend ratio). The Validator checks all of them.

## Interpreting paired movement

When the runtime check ([guardrail-pairing-check.md](../validation/guardrail-pairing-check.md)) returns one of the four outcomes, the interpretation guidance:

| Outcome | What the finding's framing should reflect |
|---|---|
| **No concern** | The finding stands as a clean primary-metric story. Paired-metric value can be mentioned briefly to demonstrate the check was made. |
| **Trade-off present** | The finding is incomplete without the trade-off mention. The action card's CAVEATS section must include the counter-direction movement, and the recommended action should account for it (e.g., a recommendation to increase volume that ignores margin compression is incomplete). |
| **Dual concern** | The finding is more serious than a primary-metric-only reading suggests. Both metrics confirming bad news typically warrants escalation in the action card's WHY-THIS-MATTERS section. |
| **Missing data** | The check could not be performed. The finding can still surface, but with a high-severity caveat that the paired check was not made. This is an instrumentation gap to surface to the domain owner. |

## When a domain has under-defined pairings

Many functional domains are likely to start with sparse pairings — only the most obvious primary metrics have explicit guardrails defined. This is acceptable as a starting state, not a target state.

The system surfaces pairing gaps in two ways:
- Findings on primary metrics with no defined guardrail get a low-severity caveat noting the absence.
- The aggregate gap list across runs feeds back to the domain-context-maintenance process so domain owners can prioritize which pairings to define next.

Over time, the pairing set in each functional domain becomes more complete. The system's confidence in its findings increases proportionally.

## Anti-patterns

- **Pairing a primary metric with another primary metric.** Two primaries are not a guardrail pair; they're two findings. The guardrail is specifically a *counter-metric* that captures a trade-off, not a co-primary.
- **Pairing metrics at different grains and treating them as comparable.** A SKU-week primary metric paired with a brand-quarter "guardrail" is not a meaningful comparison.
- **Defining pairings to make a preferred finding look better.** The pairing exists at the domain level, pre-committed, before findings are run. Findings cannot retroactively pick their own guardrails.
- **Skipping the check on "good" findings.** A volume gain story sounds clean — until margin compression turns it into a partial story. The check exists especially for the findings that look unambiguous.

## Tie to framing

Guardrail pairings are how the system avoids one of the most common recipient-trust failures: the "we acted on the recommendation and the side effect surprised us" failure. Every action card that ships with its guardrail check made and its trade-off surfaced is one more reason the recipient trusts the next card. The pairing methodology is the structure that makes this routine, not heroic.

## Output discipline

This skill governs methodology and the contract between functional-domain context documents and the Validator's check. The check itself (running the comparison, recording the outcome) is in [guardrail-pairing-check.md](../validation/guardrail-pairing-check.md). Specific pairings live in `context/domains/<domain>.md`.
