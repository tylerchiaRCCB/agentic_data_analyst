# Analytical Skill: Benchmarking Methods

**Loaded by:** Opportunity Identifier.
**Purpose:** Compare an entity's performance to a defensible reference. A benchmark is only useful if it is *appropriate*; a poorly chosen benchmark produces "underperformance" findings that are not actionable because the comparison was wrong.

## Choice of benchmark

| Benchmark | When appropriate | Risks |
|---|---|---|
| **Internal peer group** (e.g., similar accounts within region) | Most common; controls for many context variables implicitly | Peer-group definition is everything — wrong group, wrong finding |
| **Internal trend** (entity's own prior period) | Identifying acceleration / deceleration; controls for entity-specific context | Doesn't reveal relative competitiveness; doesn't account for market-wide shifts |
| **Top performer / top quartile** within peer group | Identifying the achievable upside ("if you matched the top, what would it be?") | Top performers may have unmeasured advantages; risks setting an unrealistic target |
| **Distribution-relative** (e.g., percentile rank within peers) | When the question is "where does this entity sit in the distribution?" | Loses information about absolute level |
| **Statistical model expected value** (regression-adjusted) | When the peer group is heterogeneous and observable controls exist | Requires modeling; model assumptions inherit their own risks |
| **External / industry benchmark** | When internal comparison would miss whole-population effects | Often unavailable or stale; mismatches in definition between internal and external metrics |

Internal peer groups are the MVP default. External benchmarks are aspirational; in production they require sourcing and definition-mapping.

## Peer-group construction

A peer group is good when:
1. **Operationally comparable.** Peers face similar conditions on the dimensions that matter for the metric (channel, region, account size, SKU mix, etc.). Comparability dimensions come from the domain context.
2. **Sufficiently large.** Small peer groups give noisy benchmarks. Default minimum: 10 entities. For top-quartile benchmarks, the implied minimum is higher (need enough entities for the top quartile to be stable).
3. **Defined ex ante.** The peer-group definition is fixed before the analysis runs — not chosen to make the focal entity look worst.
4. **Excludes the focal entity itself.** Including the focal entity in its own benchmark dampens the comparison.

When the peer group is small or fragile, **report the benchmark statistic alongside its uncertainty** — the median of 8 accounts has a wide CI, and that uncertainty should propagate to the gap estimate.

## Required reporting

For every benchmark applied:

- The benchmark statistic (median, mean, top-quartile threshold, percentile rank — whichever is being used) with its CI.
- The peer-group definition: criteria, count, and exclusion list.
- The focal entity's value.
- The **gap**: difference (absolute and percent) with CI. The CI on the gap is wider than the CI on either side and is the relevant uncertainty.
- The percentile rank of the focal entity within the peer group, when meaningful.
- Caveats: peer-group fragility, definitional mismatches, time-window mismatches.

## Honest benchmarking

A finding of "underperformance vs. benchmark" must survive these checks:

1. **The gap exceeds the noise band.** If the focal entity's typical week-to-week variation is ±15% and the gap to peers is 8%, the entity is not underperforming — it is within its own noise.
2. **The gap is stable across time windows.** A gap visible only in the most recent 2 weeks may be a transient blip, not a structural difference. See [triangulation.md](../universal/triangulation.md).
3. **The peer group is robust to single-entity removal.** If dropping the highest-performing peer eliminates the gap, the "underperformance" is being defined relative to a single competitor, not a peer group.
4. **The focal entity is operationally comparable.** If the entity differs from peers on a meaningful dimension (a much larger account; a different channel mix), the comparison may be invalid. Either re-define the peer group, model-adjust, or downgrade the finding.

## Anti-patterns

- "Underperforming vs. top performer" without acknowledging that top-performance benchmarks set unrealistic targets and produce systematically inflated gaps for the average entity.
- Comparing percent values without weighting (e.g., comparing a low-volume account's instock rate to a high-volume one's without considering that they have different statistical reliability).
- Peer groups defined after seeing the data ("cherry-picked peers that make the gap look bigger").
- Reporting a gap without its CI. Often the gap is not statistically distinguishable from zero on the available sample size.
- Treating a single-period gap as a finding without triangulation across periods.

## Tie to framing

The discipline of honest benchmarking — including the willingness to say *"this entity's gap to peers is within noise and does not warrant an intervention"* — is one of the strongest defenses against the false-alarm failure mode. The Opportunity Identifier must be able to look at a gap that doesn't survive these checks and conclude "no opportunity here," not manufacture an action.

## Output-shape discipline

Code execution returns benchmark statistics, the focal entity's value, gap with CI, and peer-group size — small numbers. The peer-group's per-entity values stay in the sandbox and can be queried by filter expression if needed.
