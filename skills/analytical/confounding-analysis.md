# Analytical Skill: Confounding Analysis

**Loaded by:** Relationship Analyzer, Root Cause Investigator, Findings Validator.
**Purpose:** When an apparent association between two variables exists, determine whether a third variable (a confounder) is responsible — partially or wholly — for that association. Without this discipline, findings of "X is associated with Y" routinely turn out to be "Z drives both X and Y."

A confounder is a variable that:
1. Causes (or is associated with) the proposed cause X, and
2. Causes (or is associated with) the proposed effect Y, and
3. Is not on the causal pathway from X to Y.

If a confounder exists and the analysis fails to adjust for it, the X–Y relationship is at minimum *partly spurious* and at worst *entirely* an artifact of Z.

## When to invoke this skill

- Any finding of cross-sectional association that lacks a randomized assignment or quasi-experimental design.
- Aggregate-level findings that may dissolve at finer stratification (this is the confounding cousin of Simpson's Paradox — see [simpsons-paradox-check.md](simpsons-paradox-check.md)).
- Any time the Root Cause Investigator concludes "X is associated with Y" without ruling out an obvious third variable.
- When domain context (or universal CPG knowledge) names a likely third variable. Common CPG confounders:
  - **Seasonality** for any time-aware metric.
  - **Promotion timing** for volume, lift, margin findings.
  - **Account size / channel** for relationship findings spanning a portfolio.
  - **Region / climate zone** for distribution and supply findings.
  - **Product category / lifecycle stage** for assortment and pricing findings.

## Procedure

1. **Name the candidate confounder(s) explicitly.** *"We hypothesize that promo_active confounds the volume ↔ instock relationship because promo periods drive both retailer stocking and shopper offtake."* Without naming the confounder, you cannot test for it.

2. **Verify the confounder satisfies the three criteria.** Check the data: is the candidate associated with X? Associated with Y? Not on the causal pathway from X to Y? (The last criterion may require domain context to settle.)

3. **Run the unadjusted analysis.** Report raw association: Spearman ρ, Pearson r, mean difference, etc., with effect size + CI per [statistical-rigor.md §2](../universal/statistical-rigor.md).

4. **Run the adjusted analysis** using one of these techniques (choose by data shape):

   - **Partial correlation** when both X, Y, and Z are continuous. Report partial ρ alongside raw ρ. Computed via `pingouin.partial_corr` or regression-residual approach.

   - **Stratified analysis** when Z is categorical or can be discretized. Compute the X–Y association *within each stratum* of Z, then report the per-stratum effects and a stratum-weighted aggregate (Mantel-Haenszel for binary outcomes; weighted mean for continuous).

   - **Multivariable regression** when Z has many levels or there are multiple Zs. Fit an OLS or GLM with X as the predictor and Z as covariates; report the partial coefficient on X with CI.

   - **Doubly-robust adjustment / IPTW** for high-stakes findings where the analyst wants protection against misspecification of the adjustment model. This is heavy machinery and rarely needed in MVP scope — prefer simpler approaches and document any limitations.

5. **Compare raw and adjusted effect sizes.** Report both. Interpret the diff:

   - **Adjusted effect ≈ raw effect** → Z is not a confounder of consequence; the X–Y association is robust.
   - **Adjusted effect substantially attenuated** → Z explains some/most of the association. State the proportion of effect remaining (e.g., "60% of the raw effect persists after adjustment for Z").
   - **Adjusted effect vanishes** → The X–Y association is largely confounded by Z. The finding must be restated: *"X co-occurs with Y because both move with Z"* rather than *"X is associated with Y."*
   - **Adjusted effect reverses direction** → This is Simpson's Paradox territory; see [simpsons-paradox-check.md](simpsons-paradox-check.md) for the full decomposition workflow.

6. **Report the adjustment honestly.** The artifact must contain:
   - The candidate confounder named
   - Raw and adjusted effect sizes with CIs
   - The adjustment method used
   - The proportion of effect attenuation (or amplification)
   - Any remaining uncertainty about unmeasured confounders

## Causation gate

After confounding adjustment, language calibrates per [confidence-language.md](../output/confidence-language.md):

- Robust effect after adjustment for **all plausible** confounders → `strong_correlation`.
- Robust effect after adjustment for **some** confounders, but plausible unmeasured ones remain → `associational` with a caveat naming the unmeasured ones.
- Effect attenuated by ≥ 50% after adjustment → `associational` at most; the finding may need to be restated.
- Effect vanishes after adjustment → the finding is rejected; surface as a caveat in the artifact's `analytical_caveats`.

## Mandatory caveats

When the analysis cannot rule out all plausible confounders (the typical observational case), emit a caveat:

> *"Adjusted for {named confounders}; unmeasured confounders ({list plausible unmeasured ones}) cannot be ruled out. Finding is association-strength evidence, not causal."*

This caveat is non-negotiable for any observational finding that does not have a quasi-experimental design.

## Anti-patterns

- **Naming "everything else" as a confounder without specifics.** *"Other factors might confound this"* is meaningless. Name the candidate Z and test it.
- **Adjusting for variables on the causal pathway.** If X → M → Y, adjusting for M will erroneously attenuate the X → Y effect. The confounder must NOT be on the causal pathway; this requires domain judgment.
- **Adjusting for colliders.** If Z is a common effect of X and Y (rather than a common cause), adjusting for Z induces a spurious association. Stratify only by variables you'd want to "hold constant" — not by downstream consequences.
- **Reporting adjusted effects without the raw effects.** Both must be visible — the diff is what the recipient learns from.
- **Concluding "no confounding" without testing.** *"We don't think this is confounded"* is not a method. Name a candidate, test it, report the result.

## Tie to framing

Confounding analysis is one of the most important defenses against the failure mode this system exists to prevent: confidently publishing a finding that is later shown to be an artifact of a third variable the analyst didn't think to control for. Every observational claim should be interrogated for confounders before it earns confidence. The discipline pairs with Simpson's Paradox checking (which is the special case where stratification *reverses* the aggregate effect) and with the causation-vs-correlation language gate.
