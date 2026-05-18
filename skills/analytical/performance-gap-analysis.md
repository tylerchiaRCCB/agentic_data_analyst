# Analytical Skill: Performance Gap Analysis

**Loaded by:** Opportunity Identifier.
**Purpose:** Quantify the difference between an entity's actual performance and its achievable potential, decompose that gap into addressable components, and translate the decomposition into a basis for intervention. Pairs with [benchmarking-methods.md](benchmarking-methods.md), which establishes what "potential" means.

## What a gap analysis produces

For each focal entity (or group), a gap analysis produces:

1. **Actual** — the entity's current value on the outcome metric, with CI.
2. **Potential** — the comparable benchmark value (see `benchmarking-methods.md`) — peer median, top-quartile, modeled expected, etc.
3. **Gap** — actual minus potential, with CI propagated.
4. **Decomposition of the gap** — what subcomponents contribute, and by how much.
5. **Addressability assessment** — which decomposition components are levers a stakeholder can act on, vs. fixed context (e.g., geography, account size).

The decomposition is the analytical core. A "10% gap on the primary metric" is a number; *(illustrated in sales)* — *"10% volume gap = 6 pts from lower instock + 3 pts from fewer transactions + 1 pt from lower basket size"* — is a direction for action. The same logic applies across our CPG functional domains *(supply chain: fill-rate gap → on-hand inventory component + cycle-time component + allocation component; operations: OEE gap → availability component + performance component + quality component; finance: margin gap → price realization + cost-of-goods + trade-spend leakage)*.

## Decomposition methodologies

| Decomposition style | When to use |
|---|---|
| **Multiplicative decomposition** of a derived metric (e.g., velocity = sales / distribution; revenue = traffic × conversion × order-size) | When the outcome metric is a known product of inputs. Take logs to convert to additive contributions. |
| **Additive contribution analysis** across components (e.g., total = sum of segments) | When the outcome is a sum across categories (regions, products). Each component contributes its share of the gap. |
| **Counterfactual decomposition** ("if this entity matched the benchmark on dimension X, what would actual be?") | When the relationship is not naturally multiplicative or additive. Estimates the gap if a single dimension were closed at a time. |
| **Shapley-value style decomposition** | When components interact and the order-of-attribution matters; averages across all permutations. Heavier compute, more honest about interaction. |

The right decomposition is **functional-domain-specific** and should be specified in the domain context document for the primary metric. Common patterns across our CPG functional domains:

- *Sales / commercial:* multiplicative through the velocity equation — *volume = ACV-weighted distribution × velocity per point*, plus a residual. Detailed in `domain-specific/cpg-derived-metrics.md`.
- *Supply chain:* multiplicative or additive depending on the metric — *fill rate = perfect orders / total orders*; *on-time-in-full = on-time component × in-full component*; cycle time additive across stages.
- *Operations / manufacturing:* multiplicative through OEE — *OEE = availability × performance × quality*. Each component decomposes further (availability → planned vs. unplanned downtime; performance → speed losses; quality → defect rates).
- *Trade marketing:* multiplicative through promo ROI — *incremental volume = base volume × promo lift*; *promo ROI = incremental volume × price / trade spend*.
- *Finance:* additive in dollars — *gross margin = revenue − COGS − trade deductions*; revenue decomposes through *price × volume*.

The skill's job is to apply the appropriate decomposition; the choice of decomposition lives outside the skill, in the functional-domain context document. If the context does not specify one, flag this in the artifact's caveats and use the closest analog from the patterns above, labeled as a default.

## Required reporting

For each gap analyzed, the artifact records:

- Actual, potential, and gap (with CIs).
- Decomposition: each component's contribution, percent of total gap, and CI.
- Addressability flag per component: addressable / partially-addressable / fixed.
- Sensitivity check: how much does the gap or its decomposition change under a different (defensible) benchmark? If the answer is "a lot," the finding is benchmark-dependent and must be caveated.
- Notable observations: components that contribute negatively (i.e., the focal entity is ahead of benchmark on that component) — these are strengths that should appear in the output, not be hidden.

## Honest reporting of negative gaps

A "performance gap" framing biases toward finding underperformance. Sometimes the analysis reveals the focal entity is *ahead* of the benchmark on one or more components. **These overperformance findings must be reported too** — both because they're informative *(Example, CPG: "this entity's instock is strong; the volume gap is purely from transaction frequency")* and because suppressing them violates intellectual honesty.

The Opportunity Identifier's `opportunity_areas` should include strengths-to-preserve alongside gaps-to-close when both exist for the same entity. The Communication Agent's action card may include a "what's working" line when relevant.

## When the gap doesn't warrant an intervention

A computed gap is not automatically an opportunity. The Opportunity Identifier must check:

1. **Is the gap larger than the entity's noise band?** If it isn't, see [benchmarking-methods.md](benchmarking-methods.md) "Honest benchmarking" §1.
2. **Is the gap addressable?** A gap whose decomposition is dominated by fixed context (region, account size, channel structure) cannot be closed by intervention. Report it as context, not opportunity.
3. **Does the cost of intervention plausibly exceed the value of closing the gap?** This is qualitative in MVP — the spec does not require ROI estimation — but flagrant cases (gap of 50 cases, intervention costs hundreds of person-hours) should be flagged as "not a priority" rather than promoted to an action card.

If none of these survive, the right output is "gap exists, but not actionable at this time" — a descriptive observation, not an action card.

## Anti-patterns

- Promoting every gap to an opportunity. Many gaps reflect structural differences that no intervention will close.
- Decompositions that are arithmetic only — e.g., "the gap is 10% and 60% of it is from instock" — without addressability analysis. The decomposition without addressability is half the work.
- Hiding overperformance components. A balanced finding includes both directions of difference.
- Choosing the decomposition method that produces the largest "addressable" share. Pre-commit to a decomposition appropriate to the metric structure.

## Tie to framing

This skill is one of the system's primary tools for distinguishing *interesting gaps* from *actionable opportunities*. The Opportunity Identifier's job is the latter; the descriptive summary can carry the former. The discipline to say "we found a gap but it's not actionable" — and to route that conclusion to the descriptive summary rather than an action card — is exactly the product framing.

## Output-shape discipline

Code execution returns the gap, the decomposition (one row per component — small), and addressability flags. Never returns the entity-level data underlying the decomposition.
