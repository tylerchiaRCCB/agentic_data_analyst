# Analytical Skill: Simpson's Paradox Check

**Loaded by:** Data Profiler (risk surfacing), Root Cause Investigator (mandatory check before any aggregate causal claim), Findings Validator (revalidation step).
**Purpose:** Detect cases where an aggregate-level relationship reverses, vanishes, or strengthens when conditioned on a subgroup. Simpson's Paradox is one of the most common ways that a confidently-stated aggregate finding turns out to be wrong.

## What it is

Simpson's Paradox occurs when:
- Aggregate-level analysis shows relationship A.
- Subgroup-level analysis (within strata of a third variable) shows relationship B, where B contradicts A — either in direction, in magnitude, or in significance.

The paradox is most likely when:
- Subgroups have very different baseline rates or distributions on the outcome.
- Subgroup membership is unevenly distributed across the predictor.
- Both of the above conditions hold simultaneously.

*(Example, sales)*: an aggregate finding *"national instock improved 3 pts year-over-year"* may mask *"all regions individually got worse, but the regional mix shifted toward higher-instock regions."* The same shape appears across our CPG functional domains — *(supply chain)* aggregate fill rate up while every DC's fill rate is flat or down because volume shifted toward higher-fill-rate DCs; *(operations)* aggregate OEE up while every line's OEE is down because production volume shifted to higher-OEE lines; *(finance)* aggregate gross margin up while every account-tier's margin is down because the mix shifted toward higher-margin tiers. Mix shift driving an aggregate trend is Simpson's Paradox.

## When this check is required

The Root Cause Investigator and Findings Validator **must** run this check before stating any aggregate-level causal or directional finding involving:

- A pooled comparison across heterogeneous entities (regions, accounts, SKUs, time periods).
- A weighted mean or rate where the weights (subgroup sizes) may have shifted between the periods or groups being compared.
- An aggregate trend over time where the population mix may have changed (entity churn, segment migration).

For non-causal, non-directional, purely descriptive aggregate statistics (e.g., "national volume in Q1 2026 was X cases"), the check is recommended but not mandatory.

## Procedure

1. **Identify candidate stratifying variables.** The domain context should list dimensions that commonly cause mix-shift artifacts (region, channel, account tier, SKU class). Check each.

2. **For each candidate stratifier**:
   - Compute the aggregate-level statistic.
   - Compute the same statistic within each stratum.
   - Compare directions and magnitudes.

3. **Diagnose the disagreement pattern**:
   - **Reversal**: aggregate direction is opposite to all/most subgroup directions → classic Simpson's Paradox; the aggregate is mix-shift-driven, not effect-driven.
   - **Vanishing**: aggregate effect is large, subgroup effects are uniformly small or zero → mix shift is the sole source of the aggregate signal.
   - **Strengthening**: aggregate effect is small, subgroup effects are uniformly large in the same direction → aggregation is masking an even larger effect; the finding is real but understated.
   - **Heterogeneous**: subgroup effects vary in direction → there is no single aggregate "effect"; the right level of analysis is subgroup, not aggregate.

4. **Decompose** the aggregate change into (a) effect-within-subgroups and (b) mix-shift between subgroups. Standard decomposition: *aggregate Δ = Σ wᵢ · Δratᵢ + Σ Δwᵢ · ratᵢ*, where w is weight (subgroup size share) and rat is the outcome rate. Report the mix-shift component explicitly.

5. **Choose the right level for the finding**:
   - If subgroup effects are consistent, the aggregate finding is real — proceed.
   - If subgroup effects reverse or differ in direction, **the aggregate finding is wrong or misleading**. The Root Cause Investigator must restate the finding at the subgroup level, and the Findings Validator must downgrade any aggregate-level claim that disagrees with its subgroups.

## Required reporting

When the check is run, the artifact must record:

- Stratifying variable(s) examined.
- Aggregate statistic vs. per-stratum statistics.
- Disagreement pattern (above).
- Decomposition: effect-within vs. mix-shift contributions.
- Recommendation: aggregate finding stands / aggregate finding must be restated at stratum level.

When the check is *not* run on a finding that required it, the Validator flags this as a methodology gap and downgrades the finding.

## Anti-patterns

- Skipping the check on aggregate findings because "the data looked clean." The check is cheap; the cost of a wrong aggregate finding is high.
- Reporting an aggregate finding alongside subgroup findings without acknowledging that they contradict each other.
- Choosing the level (aggregate vs. subgroup) that supports the preferred narrative. The level should be chosen by the data shape, not the story.
- Stratifying by a variable that is *caused by* the outcome (post-treatment stratification). E.g., stratifying customer cohorts by their post-purchase satisfaction. This introduces collider bias, not removes it.

## Tie to framing

This check is one of the strongest expressions of the system's intellectual honesty. An aggregate finding that survives a Simpson's check is much more defensible than one that didn't go through it. The discipline of running the check — and being willing to retract the aggregate finding when it doesn't survive — is exactly what makes the tool more trustworthy than a careless aggregation.

## Output-shape discipline

Code execution returns the aggregate statistic, the per-stratum statistics (one row per stratum — small), and the decomposition components. Never returns the row-level data.
