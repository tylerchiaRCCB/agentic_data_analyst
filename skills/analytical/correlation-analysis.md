# Analytical Skill: Correlation Analysis

**Loaded by:** Relationship Analyzer.
**Purpose:** Quantify and interpret the strength of association between two variables. Choose the appropriate method, compute via code, report the full picture, and stay honest about what correlation does and does not mean.

## Method selection

| Both variables | Both roughly normal? | Relationship plausibly linear? | Method |
|---|---|---|---|
| Continuous | Yes | Yes | Pearson |
| Continuous | No (skewed or outlier-prone) | — | Spearman (rank-based) |
| Continuous | — | Monotonic but not linear | Spearman |
| Continuous | — | Non-monotonic | Pearson is misleading; use scatterplot inspection + mutual information |
| Ordinal | n/a | — | Spearman or Kendall's tau |
| One continuous, one binary | — | — | Point-biserial (special case of Pearson) |
| Two binary | n/a | — | Phi coefficient (special case of Pearson) |

For skewed metrics — the Profiler's distribution classification drives this — **default to Spearman** unless the distributions are approximately normal. Skew is the norm across our CPG functional domains *(Examples: sales — volume, basket size, promotional lift; supply chain — days-of-supply, lead time; operations — cycle time, downtime; finance — gross margin per case, trade deduction value)*. See [resistant-statistics.md](../universal/resistant-statistics.md).

## Required reporting

For every correlation computed, emit a `Statistic` (see [artifact-schemas.md](../../orchestration/artifact-schemas.md) §3.1) with:

- The coefficient value.
- Sample size *n*.
- 95% confidence interval (Fisher-z transform for Pearson; bootstrap for Spearman if reporting CI).
- p-value, paired with multiple-comparison correction context. A raw p < 0.05 from one of many correlations is not a finding — see [statistical-rigor.md](../universal/statistical-rigor.md) §4 for the MVP rule (Benjamini-Hochberg FDR for exploratory, Bonferroni for confirmatory).
- Effect-size interpretation tier: trivial (|r| < 0.10), small (0.10–0.30), moderate (0.30–0.50), large (≥ 0.50). Report the tier, not just the number.

## Partial and conditional correlations

When a third variable plausibly confounds the relationship — *(Example, trade marketing)*: correlation between *promotional spend* and *volume* with *seasonality* as a likely driver — compute the partial correlation controlling for the confounder. Report both the raw and partial coefficients so the reader can see what the control changed. The Relationship Analyzer's `interaction_effects` field captures cases where the relationship's strength *depends on* a third variable — a more involved analysis than partial correlation. A dedicated `interaction-detection.md` skill is deferred to Phase 2; in MVP, report suspected interactions as `Hypothesis` entries for downstream investigation rather than computing them here.

## Anti-patterns

- Reporting a Pearson coefficient on visibly skewed data because the math runs without warning. Spearman gives a less biased answer.
- Treating |r| < 0.10 as "no relationship" without checking sample size — a small coefficient with very large *n* can still be highly statistically significant and is often substantively meaningless. The effect-size tier is the real signal, not the p-value.
- Computing 50 pairwise correlations and reporting the largest as a finding without multiple-comparison correction.
- Sliding from "X and Y are correlated" to "X drives Y." See [ethical-analysis.md](../universal/ethical-analysis.md) §2 and [statistical-rigor.md](../universal/statistical-rigor.md) §5.

## Output-shape discipline

Code execution returns the coefficient, sample size, CI, and p-value — never the underlying paired-value matrix. A correlation computed over 1M rows produces ~5 numbers in context, not 1M rows of data.
