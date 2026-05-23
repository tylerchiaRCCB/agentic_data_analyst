# Analytical Skill: Counterfactual Reasoning

**Loaded by:** Root Cause Investigator, Opportunity Identifier.
**Purpose:** When asked *"why did volume drop in Account 47?"* a senior analyst doesn't just describe what happened — they implicitly compare against *what would have happened* in a counterfactual world (e.g., where the promo wasn't pulled, or the supply disruption hadn't occurred). This skill codifies that discipline: framing every root-cause claim against an explicit counterfactual baseline, even when formal causal inference is not available.

This is intentionally lightweight. Full causal inference (potential outcomes, structural causal models, do-calculus) is Phase 2 work. The MVP version is observational counterfactual *framing* — making the comparison explicit so the reader can evaluate the claim.

## When to invoke this skill

- The Root Cause Investigator is naming a cause for an observed change ("the drop is due to X").
- The Opportunity Identifier is estimating the impact of an intervention ("doing Y would have prevented/recovered Z").
- A finding's claim implies a counterfactual ("without X, this wouldn't have happened") and the explicit comparison should be stated.

## The three counterfactual framings

### 1. Comparable-cohort counterfactual

The most common and the lightest-weight. State an explicit comparable cohort and report the observed gap.

**Pattern:** *"Account 47 declined 19 points; comparable accounts in the same channel and region (Accounts 12, 33, 51) declined 4 points on average over the same period."*

**Required:**
- Name the cohort comparator explicitly (not "the industry" — specific entity IDs or a defined segment).
- Use the same time window for both.
- Report effect-size difference with CI per [statistical-rigor.md §2](../universal/statistical-rigor.md).
- Apply a Statistic of kind `group_comparison` — schema-enforced effect size + CI required.

**Limitations to surface in caveat:**
- The cohort may differ on unobserved characteristics.
- Selection of the cohort is itself a modeling choice.
- This is associational, not causal — the gap is consistent with X being the cause, but does not establish it.

### 2. Pre/post counterfactual within the same entity

When the cause is plausibly localized to a time window, compare the entity's behavior immediately before and immediately after a putative cause event.

**Pattern:** *"Account 47's instock averaged 91% in the 4 weeks before week 18; in the 4 weeks after, it averaged 76% — a 15-point drop coinciding with the supplier shift."*

**Required:**
- Define the pre and post windows symmetrically (same duration, same seasonality posture if possible).
- Report mean ± CI for both windows; compute the gap with sample-size-aware effect size.
- Confirm the change point persists (≥ 4–8 weeks for weekly data) per [change-point-detection.md](change-point-detection.md).
- Verify no other plausible cause coincides with the change point.

**Limitations to surface in caveat:**
- Pre/post comparisons within a single entity confound seasonal and lifecycle changes with the proposed cause.
- A single change point is not a controlled experiment — many real-world variables shift simultaneously.
- The strongest version of this analysis adds a *control entity* that did not undergo the proposed cause (this is the difference-in-differences design, Phase 2 work).

### 3. Model-based counterfactual (forecast counterfactual)

When historical patterns are strong enough, fit a forecast model on the pre-event data and project what the post-event period *would have been*. Compare actual to projected.

**Pattern:** *"Account 47's volume trajectory through week 17 implied weeks 18–22 should have averaged 1,420 cases/week (95% PI: 1,180–1,650). Actual: 1,050 cases/week. Gap: -370 cases/week, outside the prediction interval."*

**Required:**
- The forecast model must be defensible: report method (e.g., STL+ARIMA, exponential smoothing), training window, accuracy on holdout.
- Project the counterfactual with a prediction interval, not a point estimate.
- The "gap" is the difference between actual and the projected mean; the "evidence" is whether actual falls outside the prediction interval.
- The forecast assumes the cause didn't happen and other things continued at trend; surface this as a limitation.

**Limitations to surface in caveat:**
- Model misspecification can produce misleadingly tight prediction intervals.
- Trend extrapolation assumes underlying conditions stay the same in the counterfactual — often false in business contexts.
- Use this approach only when the pre-event period has enough data for a credible forecast (≥ 1 full seasonal cycle minimum).

## Required reporting

For any root-cause or opportunity finding invoking a counterfactual:

1. **State the counterfactual framing explicitly.** Which of the three framings above is being used.
2. **Name the comparison.** Specific cohort entities, specific time windows, or specific forecast method.
3. **Report the gap with CI.** Per [statistical-rigor.md §2](../universal/statistical-rigor.md), with effect size.
4. **State what is NOT being claimed.** *"This is association-strength evidence consistent with X causing the drop; it does not establish causation. Alternative explanations: {list}."*
5. **Pair with confounding analysis** ([confounding-analysis.md](confounding-analysis.md)) for the observational variants.

## Causation gate

The Root Cause Investigator's `causation_vs_correlation` field maps to language per [confidence-language.md](../output/confidence-language.md). Counterfactual framing strength interacts with this gate:

- **Pure pre/post within-entity comparison** → `associational` at best. The within-entity counterfactual cannot rule out coincident changes.
- **Comparable-cohort counterfactual with good cohort matching + ruled-out alternatives** → `strong_correlation` is justifiable.
- **Quasi-experimental design** (e.g., difference-in-differences with a credible parallel-trends assumption) → `strong_correlation`; `established_causal` only with truly random assignment, which the MVP does not provide.
- **Forecast counterfactual** → `strong_correlation` when the forecast is credible and the gap is clearly outside the prediction interval. Still not causal.

When in doubt, weaken the claim. A finding overstated and later refuted costs more recipient trust than a finding stated cautiously and later confirmed.

## Anti-patterns

- **Counterfactual implied but not stated.** Saying "X caused the drop" without naming what the alternative trajectory would have been — leaves the recipient without ammunition to evaluate the claim.
- **Comparing to an aggregate without explaining the aggregate.** *"Account 47 underperformed industry average"* — which accounts make up the average? What's the variation?
- **Using a single best-fit forecast value, not a prediction interval.** Counterfactual point estimates project false precision. Show the interval.
- **Treating the counterfactual gap as causation.** The comparable-cohort gap quantifies a *coincidence*, not a *cause*. Use the appropriate `causation_vs_correlation` label.
- **Ignoring alternative explanations.** List them. *"Account 47 also went through a buyer transition in week 19; this is an alternative explanation we cannot rule out."*

## Tie to framing

Counterfactual reasoning is what separates *"X happened around the same time as Y"* (descriptive correlation) from *"X is responsible for Y, with the following caveats"* (calibrated investigation). The discipline forces every causal-language finding to make its counterfactual explicit and testable. In the absence of experiments, this is the strongest defense the system can mount against confidently publishing post-hoc rationalizations.
