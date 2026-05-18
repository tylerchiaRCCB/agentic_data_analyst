# Analytical Skill: Group Comparison

**Loaded by:** Relationship Analyzer, Root Cause Investigator.
**Purpose:** Determine whether two or more groups differ on a continuous or ordinal outcome. Choose the appropriate test, compute via code, report effect sizes (not just p-values), and stay disciplined about what "significant difference" actually means.

## Test selection

| Groups | Outcome shape | Sample size | Test |
|---|---|---|---|
| 2 independent | Continuous, roughly normal, similar variance | n ≥ 30 per group or normality confirmed | Welch's t-test (do not assume equal variance) |
| 2 independent | Skewed, ordinal, or small n | — | Mann-Whitney U |
| 2 paired | Continuous, roughly normal | — | Paired t-test |
| 2 paired | Skewed or ordinal | — | Wilcoxon signed-rank |
| ≥ 3 independent | Continuous, roughly normal | — | One-way ANOVA (followed by Tukey HSD post-hoc) |
| ≥ 3 independent | Skewed or ordinal | — | Kruskal-Wallis (followed by Dunn's post-hoc) |
| ≥ 3 paired/repeated | Continuous | — | Repeated-measures ANOVA |
| ≥ 3 paired/repeated | Skewed or ordinal | — | Friedman test |

**Default for skewed metrics:** non-parametric (Mann-Whitney, Kruskal-Wallis). The Profiler's distribution classification drives this choice. Skew is the norm across our CPG functional domains *(Examples: sales — volume, basket size, promotional lift; supply chain — days-of-supply, lead time; operations — cycle time, scrap rate; finance — margin per case, deduction values)*. See [resistant-statistics.md](../universal/resistant-statistics.md).

## Required reporting

For every group comparison, emit a `Statistic` with:

- Group means and medians (report both — they often disagree on skewed data).
- Group sample sizes.
- Test statistic and method used.
- 95% CI on the **difference** (or on each group mean separately), not just on each group's central tendency.
- p-value, with multiple-comparison correction context.
- Effect size:
  - **Cohen's d** for t-tests (small 0.2 / medium 0.5 / large 0.8).
  - **Rank-biserial r** or **Glass's delta** for Mann-Whitney.
  - **Eta-squared** or **omega-squared** for ANOVA.
- For ANOVA/Kruskal-Wallis, the post-hoc pairwise comparisons that *survive* correction (Tukey HSD or Dunn's).

## Practical vs. statistical significance

A statistically significant difference on a large sample can be substantively trivial. Always interpret in terms of:

- The effect-size tier (above).
- The business meaning of the absolute difference (e.g., is a median weekly volume difference of 12 cases between regions worth a stakeholder's attention given typical operational variance?).

The Root Cause Investigator and Findings Validator should reject "significant" findings whose effect sizes are trivial and whose business meaning is negligible. "Statistically detectable" is not a synonym for "matters."

## Anti-patterns

- Using Student's t-test (equal-variance assumption) by default. Welch's is safer and only marginally less powerful when variances are actually equal.
- Reporting only the p-value. The effect size and CI are what the reader needs to judge importance.
- Running ANOVA, finding p < 0.05, and stopping. The post-hoc step is where the actual group-pair difference lives.
- Comparing many groups pairwise without correcting for the multiplicity (each pairwise t-test inflates the false-positive rate).
- Promoting a tiny-effect significant finding to an action card. See [ethical-analysis.md](../universal/ethical-analysis.md) §1.

## Output-shape discipline

Code execution returns group summary statistics, the test statistic, p-value, CI, and effect size — never the raw group-membership vectors. The agent operates on the summary, not the rows.
