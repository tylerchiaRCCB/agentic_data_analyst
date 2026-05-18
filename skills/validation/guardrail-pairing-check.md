# Validation Skill: Guardrail Pairing Check

**Loaded by:** Findings Validator.
**Purpose:** For every finding involving movement on a primary metric, check the paired counter-metric to surface trade-offs. A "good" finding that comes at the cost of an unmonitored counter-metric is not actually good — it is a partial story that misleads the recipient. The guardrail check prevents that.

This skill is the methodology; the **specific pairings** (which metric pairs with which) live in the domain context document for each functional domain. See also [domain-specific/guardrail-metric-pairing.md](../domain-specific/guardrail-metric-pairing.md) for the general pairing-logic rules.

## The principle

Every primary metric in a CPG functional domain has at least one **counter-metric** whose movement matters when interpreting the primary. The classic patterns within our CPG company:

| Functional domain | Example primary | Example guardrail (counter-metric) |
|---|---|---|
| Sales | Volume | Gross margin per case |
| Sales | Distribution | Velocity per point |
| Supply chain | Fill rate | Inventory carrying cost / DOS |
| Supply chain | On-time-in-full | Expedite cost / freight premium |
| Operations | Throughput | First-pass quality / scrap rate |
| Operations | OEE — performance | OEE — quality |
| Trade marketing | Promotional lift | Margin per case during promo / cannibalization of base |
| Finance | Revenue | Gross margin / DSO |
| Commercial | New-account acquisition | Time-to-first-order / first-90-day retention |

The above is illustrative. The **authoritative pairings for any domain** live in `context/domains/<domain>.md` under the "Guardrail metric pairings" section. The Validator reads the pairings from the loaded domain context, not from this skill.

## When the check applies

The guardrail check runs on any finding involving:
- A movement (increase or decrease) on a primary metric.
- A comparison (group vs. group, period vs. period) where one side is the focal entity / scope.
- A recommendation that, if acted on, would push a primary metric in a stated direction.

It does **not** run on:
- Pure-descriptive characterizations with no directional claim (e.g., "the distribution is bimodal").
- Findings whose primary metric does not have a paired guardrail in the domain context (record `flag: missing_data` with a note that no pairing was checked — see below).

## Procedure

For each applicable finding:

1. **Identify the primary metric** from the finding's central claim.
2. **Look up the pairing(s)** in the domain context document. A primary metric can have more than one guardrail (e.g., volume ↔ margin AND volume ↔ trade spend); check all of them.
3. **Compute the counter-metric over the same scope and time window** as the primary. Use the same `data_slice` filter as the primary finding's `Statistic.lineage`.
4. **Compare directions:**
   - Primary up + paired up (or flat) where the direction is desirable → **no concern.**
   - Primary up + paired down (counter-direction) → **trade-off present.** Surface explicitly.
   - Primary down + paired up (offsetting) → **trade-off present in the offsetting direction.** Surface; recipient may interpret as compensating.
   - Primary down + paired down (both falling) → record as **dual concern.** The finding's bad news is worse than it looks.
5. **Flag the outcome** in the artifact's `guardrail_check_results[]` with primary direction, paired direction, statistic IDs for both, and the resulting flag (`no_concern`, `trade_off_present`, `dual_concern`, `missing_data`).

## What "trade-off present" requires the Validator to do

When the check returns `trade_off_present`:

- The finding does **not** get rejected — the primary-metric movement is real. But it is **downgraded one grade** if it would otherwise have been A.
- A **required caveat** is added that the Communication Agent must surface in the recipient output. Example (sales): *"Volume gain on this account coincided with a 3-point margin compression. Net contribution change should be evaluated alongside this finding."*
- The action card (if one is generated) must mention both metrics' movement. An action that improves volume by sacrificing margin should not look like an unqualified win.

When the check returns `dual_concern`:

- The finding is **not** downgraded — both metrics are confirming the same direction.
- The artifact records the dual move so the Communication Agent can surface both. This often strengthens the recipient's confidence that the finding is real.

When the check returns `missing_data`:

- A high-severity caveat is added to the run: *"Guardrail pairing could not be checked because the paired counter-metric is not available for the relevant scope/window. Recipient should interpret this finding as primary-metric-only."*
- The finding can still appear but at most as grade B until the pairing is computable.

## When the domain context has no pairing for a metric

If the domain context lists no guardrail pairing for the primary metric:

- The Validator records this in the artifact and adds a low-severity caveat.
- The Validator flags the absence to the run log so the domain context can be updated. Missing pairings are a domain-context-maintenance issue, not a per-run failure.
- The finding can still proceed — it just doesn't get the additional confidence boost a clean guardrail check would have given.

This is one of the patterns surfaced by [tracking-gaps.md](../universal/tracking-gaps.md): missing guardrail pairings in domain context documents are themselves "tracking gaps" the system surfaces to the domain owner.

## Anti-patterns

- Skipping the guardrail check on "obvious wins." A volume gain that comes with margin compression is the most common form of misleading "win." If the guardrail step is skipped, the misleading reading reaches the recipient.
- Letting the upstream agent's own choice of "related metrics" substitute for the domain-context pairing. The pairing exists at the domain level — it is not the agent's call.
- Treating "no pairing defined in domain context" as "no pairing needed." It usually means the domain context is incomplete.
- Computing the counter-metric over a different scope or window than the primary. Apples-to-apples is required for the comparison to mean anything.

## Tie to framing

This check is one of the strongest ways the system protects recipient trust over time. A recipient who acts on a "volume up" recommendation and later discovers margin collapsed will not trust the next recommendation. The guardrail check is what prevents that — by making the trade-off visible *with* the finding, not in a post-hoc retrospective.

## Output-shape discipline

Code execution returns the counter-metric value, its CI, and the directional comparison — a few numbers per pairing. The Validator records these as `Statistic` entries; the upstream raw data does not enter context.
