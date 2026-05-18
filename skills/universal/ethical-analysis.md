# Universal Skill: Ethical Analysis

**Role:** Match the strength of attribution to the strength of the evidence. Address confounders before causal claims. Consider base rates, counterfactuals, and disparate impact. Loaded with every agent call.

## Required practices

1. **Evidence supports specificity of attribution.** The strength of a claim must match the strength of the evidence underneath it. *"The metric for entity X dropped"* is supportable from a count. *"The metric for entity X dropped **because of** the operational change"* requires evidence connecting the change to the drop and ruling out alternative explanations. The wider the attribution gap, the weaker the language must be: prefer "is associated with," "coincided with," "is consistent with" over "caused" unless an experimental or quasi-experimental design supports causation. *(Example, CPG: "Account 47's instock dropped" vs. "Account 47's instock dropped because of the new delivery schedule.")*

2. **Address confounders before causal claims.** When making any directional or causal-adjacent claim:
   - Identify the plausible alternative explanations (other entities, time effects, seasonality, definitional changes, sampling differences).
   - Test or control for each one that the data permits.
   - Report the confounders you could not control for as caveats.
   See `confounding-analysis.md` for the methodology (deferred to Phase 2; in MVP, apply the practice using partial correlations and stratified analysis as covered in `correlation-analysis.md` and `simpsons-paradox-check.md`).

3. **Consider base rates.** A 30% rate of X among group A is uninterpretable without knowing the rate of X in the broader population or in comparable groups. Always compute the baseline rate against which a group-specific rate is being interpreted, and report both.

4. **State counterfactuals when proposing actions.** Recommended actions should be paired with the implicit counterfactual: *"If we do X, we expect Y; if we do nothing, we expect Z."* The Opportunity Identifier's `intervention_recommendations` and the Communication Agent's action cards must be readable in counterfactual form, even if not always written that way explicitly.

5. **Check disparate impact.** Recommendations that affect groups of entities (accounts, regions, DCs, plants, employee cohorts) must be checked for whether they fall disproportionately on a subgroup. If a "fix to underperforming entities" turns out to disproportionately target entities of a single demographic or geography in ways unrelated to the stated metric, surface this. The system is a decision-support tool; biased decision support is a harm.

6. **Match recipient confidence language to evidence grade.** A grade-A finding can be stated directly. A grade-B finding requires a stated caveat. A grade-C finding must be framed as preliminary. See `confidence-language.md` for the translations.

## Anti-patterns

- Causal language without controls. Phrases like "this drove Y" require an evidentiary backing that goes beyond correlation.
- Reporting a group rate without a baseline.
- Recommendations stated as absolutes without the implicit counterfactual.
- Action plans targeting an entity class without checking whether the class is defined by the metric or by something correlated with the metric.
- Promoting a preliminary signal to a confident claim because the recipient prefers crisp language. Recipient preference does not change the evidence.
