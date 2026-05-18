# Analytical Skill: Effect Size Calculation

**Loaded by:** Relationship Analyzer, Root Cause Investigator, Findings Validator, Opportunity Identifier.
**Purpose:** Quantify *how large* an effect is in standardized, interpretable units. Effect size is what separates "we can detect a difference" from "the difference matters."

Statistical significance answers "is the effect distinguishable from zero given the sample size?" Effect size answers "how big is the effect?" The first scales with *n*. The second does not. A p-value of 0.001 on n = 1,000,000 may correspond to a Cohen's d of 0.02 — detectable, trivial. Always report and interpret effect size.

## Choosing the right metric

| Test family | Effect size | Interpretation tiers |
|---|---|---|
| Independent t-test | **Cohen's d** = (mean₁ − mean₂) / pooled SD | 0.2 small / 0.5 medium / 0.8 large |
| Welch's t-test (unequal variance) | **Hedges' g** (small-sample-corrected d) | Same tiers as Cohen's d |
| Mann-Whitney U | **Rank-biserial r** or **Glass's delta** | r: 0.1 small / 0.3 medium / 0.5 large |
| Paired t-test | **Cohen's d_z** = mean(diff) / SD(diff) | Same tiers as Cohen's d |
| One-way ANOVA | **Eta-squared (η²)** or **omega-squared (ω²)** | η²: 0.01 small / 0.06 medium / 0.14 large; ω² is less biased |
| Chi-squared 2×2 | **Phi (φ)** = √(χ² / n) | 0.1 / 0.3 / 0.5 |
| Chi-squared R×C | **Cramér's V** = √(χ² / [n · min(R−1, C−1)]) | depends on df; commonly 0.1 / 0.3 / 0.5 for small df |
| Pearson correlation | **r** | 0.1 / 0.3 / 0.5 |
| Spearman correlation | **ρ** (treat like r) | 0.1 / 0.3 / 0.5 |
| Logistic / binary outcome | **Odds ratio** or **risk ratio** | OR ≈ 1.5 / 3.5 / 9 by Chen et al. convention; or compare to baseline rates directly |
| Variance-of-effect | **R²** (proportion of variance explained) | Domain-dependent; 0.05 small / 0.13 medium / 0.26 large per Cohen for behavioral sciences |

For business metrics generally, **also report relative percent difference** alongside the standardized effect size — stakeholders interpret *"the metric is 12% lower"* (Example, sales: *"instock is 12% lower"*; supply chain: *"fill rate is 4 pts lower"*; operations: *"OEE is 6 pts lower"*) more readily than *"Cohen's d = 0.6."* Report both.

## Required reporting

For every effect size emitted:

1. **The effect size value and its 95% CI.** A point estimate with no uncertainty quantification is incomplete. CIs on Cohen's d, r, and similar quantities are widely implemented — use them.
2. **The interpretation tier** for this metric, with the convention cited (Cohen, Sawilowsky, Chen).
3. **Business-units restatement** when applicable. *(Example, sales)*: *"A Cohen's d of 0.6 between region A and region B corresponds to a median weekly volume difference of 142 cases (95% CI: 98–186)."* The structure transfers across functional domains: standardized effect → CI on the absolute business-unit difference *(supply chain: cases per delivery; operations: minutes per changeover; finance: dollars per transaction)*.
4. **Comparison to the relevant baseline of typical effect sizes in the domain** if known from the domain context. Some domains routinely see large effects, some routinely see small ones; the *absolute* tier label can mislead without that grounding.

## Practical-significance heuristics

An effect size that passes a statistical-significance threshold but fails the practical-significance threshold should not become an action card.

- **Decision-impact heuristic** — would the recommended action change for a stakeholder if the effect were half as large? If no, the effect is below the decision threshold.
- **Operational-noise heuristic** — is the effect within the typical week-to-week variation of the metric? If yes, the effect is not separable from noise at the operational level even if it is separable at the statistical level.

The Opportunity Identifier and Findings Validator should both apply these heuristics. The Validator may downgrade findings that fail them (grade C or D); the Communication Agent may fold them into the descriptive summary rather than an action card.

## Anti-patterns

- Reporting an effect size without its CI. The CI is half the information.
- Citing Cohen's 0.2/0.5/0.8 tiers without acknowledging they are domain-general heuristics. In a domain where typical effects are tiny, d = 0.3 may be enormous; in another, it may be trivial.
- Using effect-size tiers to inflate findings. "Medium effect" sounds substantive; sometimes it isn't.
- Promoting a large effect on a tiny sample to a finding without checking CI width. A large point estimate on n = 8 has a CI that often includes zero.
- Reporting raw percent change without standardization on highly skewed metrics where median percent change and mean percent change disagree by a lot.

## Tie to framing

The discipline of effect-size honesty is one of the strongest defenses against "manufactured findings." A statistically significant trivial effect dressed up as a finding wastes recipient attention. Reporting effect size in standardized *and* business-units terms forces the question: *does this matter enough to act on?* If the answer is "not really," the finding belongs in the descriptive summary, not on a card.

## Output-shape discipline

Code execution returns the effect-size scalar and its CI bounds — a few numbers per test. Never returns the per-row contributions to the effect.
