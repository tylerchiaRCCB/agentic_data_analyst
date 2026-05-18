# Universal Skill: Statistical Rigor

**Role:** Every quantitative claim is backed by computed evidence, never by reasoning *about* numbers. This is the single most important defense against hallucinated statistics.

## The non-negotiables

1. **Compute, don't reason.** Any numeric claim — a count, a percentage, a mean, a correlation, a p-value, an effect size — must come from executed code, run on the actual dataset, returning the actual result. Never state a statistic that the model has produced in prose without a corresponding code execution backing it. Statistics in agent output must reference a `Statistic` artifact (see [artifact-schemas.md](../../orchestration/artifact-schemas.md) §3.1) with `lineage.code_ref` pointing to the execution that produced it.

   **Code execution returns summaries, not row dumps.** Request `df.groupby(...).agg(...)`, `df.describe()`, scalar values, and small (≤ ~50 rows) tables of *computed results*. Never `print(df)` or `df.head(1000)` on a wide dataset — that floods context with raw data the LLM is not supposed to be reasoning over. Deliberate small samples (e.g., the 12 outlier rows being investigated) are allowed; bulk row dumps are not. See [pipeline-definitions.md](../../orchestration/pipeline-definitions.md) §10.

2. **Report the full statistical picture.** A claim of "significant difference" without sample size, effect size, and confidence interval is not a complete claim. For every test or comparison, report:
   - Sample size (n for each group, or total).
   - Effect size (Cohen's d, Cramér's V, relative difference, etc. — appropriate to the test).
   - Confidence interval at a stated level (typically 95%).
   - p-value when relevant — but **never as the sole evidence**. Practical significance lives in the effect size and CI, not in p alone.

3. **Choose the right test.** Selection rules:
   - Continuous, normal-ish, two groups: independent-samples t-test (Welch's by default — do not assume equal variance).
   - Continuous, skewed or ordinal, two groups: Mann-Whitney U.
   - Continuous, multiple groups: one-way ANOVA (parametric) or Kruskal-Wallis (non-parametric).
   - Categorical, two variables: chi-squared if expected counts ≥ 5; Fisher's exact otherwise.
   - Continuous-continuous association: Pearson if both roughly normal and the relationship is linear; Spearman otherwise.
   - Paired observations: paired t-test or Wilcoxon signed-rank.
   For skewed metrics — the norm across our CPG company's functional domains (sales: volume, basket size, promotional lift; supply chain: days-of-supply, lead time; operations: cycle-time, downtime duration; finance: gross margin per case, trade deduction value; trade marketing: campaign lift) — default to non-parametric or resistant alternatives. The Profiler's distribution classification drives this choice. See [resistant-statistics.md](resistant-statistics.md).

4. **Apply multiple-comparison correction when running many tests.** When examining many variable pairs, group comparisons, or anomaly candidates in a single run, the family-wise false-positive rate grows fast. Default: Benjamini-Hochberg FDR control at q = 0.10 for exploratory analysis (most agent work). Use Bonferroni for confirmatory tests. Report the correction method applied; an uncorrected p-value from a large search is not a finding.

5. **Distinguish correlation from causation, explicitly.** Statistical association is association — full stop. Causal language ("X caused Y", "X drove Y") requires either an experimental design or a documented causal-inference methodology with stated assumptions. In the MVP, default to associational language: *"X is associated with Y after controlling for Z."* The Root Cause Investigator may go further, but only with the `causation_vs_correlation` field on its primary cause set honestly (often `strong_correlation`, not `established_causal`).

## Anti-patterns

- Producing a numeric claim in prose without a corresponding executed computation.
- "Statistically significant" as a stand-alone phrase. Pair it with effect size and sample size, or do not use the phrase.
- Promoting a strong correlation to "the cause" because no other candidate appears stronger. Absence of competing evidence is not evidence.
- Reporting p < 0.05 from one of many tests as a finding without correction.
- Using parametric tests on visibly skewed distributions because the parametric output is more familiar.
