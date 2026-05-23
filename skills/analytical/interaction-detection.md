# Analytical Skill: Interaction Detection

**Loaded by:** Relationship Analyzer, Pattern Discoverer, Root Cause Investigator.
**Purpose:** Test whether the relationship between X and Y *depends on the level of Z*. A main effect that holds on average can be silent (or reversed) in a key subgroup; treating "X is associated with Y" as a unconditional statement is a common analytical failure mode, especially in CPG data where seasonality, region, and channel routinely modify effects.

## Core distinction: main effect vs. interaction

- **Main effect:** the average association between X and Y, ignoring Z.
- **Interaction (effect modification):** the X–Y association is *different* at different levels of Z.

Where confounding adjustment tries to *remove* a third variable's contribution, interaction detection asks whether the relationship X→Y *varies* across the third variable's levels. They're different questions and require different procedures.

## When to invoke this skill

- Whenever the Relationship Analyzer finds an X–Y association in aggregate data that spans heterogeneous entities (regions, channels, categories, time periods).
- When domain context names a plausible effect modifier — *"promo lift varies by region"* is a hypothesis about interaction, not confounding.
- After a finding emerges and the Investigator wonders whether it generalizes uniformly.
- When the recipient is likely to take action on a subset of the data — *"target accounts where the lift is strongest"* requires per-subgroup effect estimates, not the aggregate.

## Pre-specify or post-hoc?

This matters because post-hoc interaction hunting in many subgroups inflates false positives dramatically. State which mode you're in:

- **Pre-specified:** the moderator was named *before* the analysis was run. Reports treat the interaction as a confirmatory test.
- **Post-hoc:** the moderator emerged from exploring the data. Treat as exploratory; apply multiple-comparison correction; surface as a hypothesis for follow-up rather than a finding.

A post-hoc interaction with no correction and no follow-up plan is not a finding — it's noise mining.

## Procedure

1. **Define the moderator Z.** Continuous, ordinal, or categorical. State *why* you expect modification — domain mechanism if available, statistical exploration if not.

2. **Test the main effect on the full sample first.** Report effect size + CI + p-value. This is your baseline.

3. **Apply the interaction test appropriate to data shape:**

   - **Both continuous (X, Z, and Y all continuous):** Fit an OLS regression with interaction term: `Y ~ X * Z`. Test H₀: β_{X·Z} = 0. Report β with CI; interpretation requires plotting predicted Y across Z values.

   - **X continuous, Z categorical (most common CPG case):** Fit `Y ~ X * C(Z)`. Report the X-slope within each stratum of Z, plus a global interaction-effect test (F-test on the interaction term). Equivalently: stratified regression with formal slope-comparison test.

   - **X categorical, Z categorical (group comparison varying by moderator):** Two-way ANOVA with interaction term. Report main effects of X and Z, and the X·Z interaction F-test and effect size (η²_interaction).

   - **Binary outcome:** Logistic regression with interaction term; report OR for X within each level of Z; test interaction via likelihood-ratio test.

4. **Estimate and report per-stratum effects.** Even when the interaction test isn't statistically significant, present the per-stratum effect sizes with CIs. The recipient cares about the *magnitude* of the difference more than the *significance* of the test — a noisy interaction that nonetheless suggests a 30% effect in one subgroup and a 5% effect in another is informative even if p > 0.05.

5. **Report effect heterogeneity honestly:**

   - **No interaction (test n.s. AND per-stratum effects similar):** finding is general; state the main effect as the headline.
   - **Significant interaction with clear directional pattern:** restate the finding as conditional. *"The X–Y association holds in Z=A but is attenuated or absent in Z=B."*
   - **Significant interaction with no clear pattern:** report subgroup heterogeneity as a caveat; recommend further investigation. The aggregate finding is misleading.
   - **No significant interaction but per-stratum effects vary widely (underpowered):** state honestly. *"Per-stratum estimates ranged from X to Y; sample size was inadequate to distinguish."*

## Mandatory companion analyses

- **Effect-size heterogeneity should be quantified.** Report I² or τ² if running stratified estimates across multiple Z levels — gives a defensible single number for "how much does the X–Y relationship vary across Z."
- **Pair with confounding analysis ([confounding-analysis.md](confounding-analysis.md)).** Interactions and confounding are separate concerns but both belong on any observational finding involving heterogeneous data.
- **Pair with Simpson's Paradox check ([simpsons-paradox-check.md](simpsons-paradox-check.md)).** When stratification *reverses* the aggregate effect (not just weakens it), the issue is Simpson's, not interaction in the conventional sense.

## Reporting the result

The artifact must contain:
- Pre-specified or post-hoc (be honest)
- The interaction test statistic and p-value (with correction if post-hoc)
- The per-stratum effect sizes with CIs
- The interaction effect size (β for continuous moderator; difference in slopes for categorical)
- A plot description (or actual figure where the Communication Agent can render one) showing the X–Y relationship at each level of Z
- A clear restatement of the finding incorporating the moderator if present

## Anti-patterns

- **Reporting only the main effect when an interaction is significant.** This is the single largest analytical sin in business analytics: claiming "X drives Y" when really "X drives Y in Region A and does nothing in Region B." The aggregate is technically correct and operationally useless.
- **Hunting for interactions in many moderators without correction.** Try 10 moderators, find 2 with p < 0.05, claim victory — these are spurious by construction. Pre-specify or correct.
- **Conflating interaction with confounding.** A confounder *explains away* an effect; a moderator *changes* it. Use the right framing.
- **Reporting interaction p-value without per-stratum effect sizes.** The p-value is a hypothesis test; the effect sizes are the finding. Report both.

## Tie to framing

Most actionable CPG findings are conditional — an intervention that works on certain accounts, in certain regions, in certain seasons. Treating all CPG findings as main effects, without surfacing the interaction structure, leaves the recipient with a less actionable claim than the data supports. Interaction detection is what turns *"X is associated with Y"* into *"X is associated with Y in this segment but not that one"* — much more useful to act on.
