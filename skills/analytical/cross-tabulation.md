# Analytical Skill: Cross-Tabulation

**Loaded by:** Relationship Analyzer.
**Purpose:** Examine the joint distribution of two (or more) categorical variables. Choose the appropriate test of independence, compute via code, and interpret residuals to find *where* the dependence lives, not just whether it exists.

## Test selection

| Table dimensions | Cell counts | Test |
|---|---|---|
| 2 × 2 | All expected counts ≥ 5 | Chi-squared test of independence (with Yates' continuity correction for 2×2) |
| 2 × 2 | Any expected count < 5 | **Fisher's exact test** |
| R × C, R or C > 2 | All expected counts ≥ 5 | Chi-squared test of independence |
| R × C | Some expected counts < 5 but ≥ 1 | Chi-squared with caveat; consider collapsing low-count categories |
| R × C | Very sparse | Fisher's exact (or Monte Carlo simulation if too large) |
| Stratified 2 × 2 across a third variable | — | Cochran-Mantel-Haenszel; check for Simpson's Paradox (see `simpsons-paradox-check.md`) |

## Required reporting

For every cross-tab analysis, emit a `Statistic` with:

- Observed counts table dimensions and total *n*.
- Test statistic (chi-squared value or Fisher's exact p directly).
- Degrees of freedom.
- p-value.
- **Effect size**: **Cramér's V** for tables larger than 2×2; **phi coefficient** for 2×2. (Phi small ≈ 0.10, medium ≈ 0.30, large ≈ 0.50; Cramér's V scales with min(R−1, C−1).)
- **Standardized residuals** for cells where |residual| > 2 — these point to which cells contribute the dependence. A significant overall chi-squared without residual analysis is half a finding.
- Multiple-comparison correction context if examining many tables.

## Residual analysis — where the dependence lives

A significant chi-squared tells you the variables are not independent; it does not tell you *how* they are dependent. Standardized residuals (or adjusted residuals for R×C > 2) identify the cells that drive the result:

- Residual > +2: observed count substantially higher than expected under independence.
- Residual < −2: observed count substantially lower than expected.
- |Residual| ≤ 2: cell is roughly as expected.

Always report the residual pattern alongside the test statistic. The Relationship Analyzer's `notable_findings` should describe the residual pattern in plain language ("regions A and B over-represented in the 'low instock' category; region D under-represented").

## Categorical variable handling

- **High-cardinality categoricals** (e.g., 500 accounts): consider rolling up to a meaningful grouping (region, tier) before testing, or restrict to top-N entities by frequency. Expected-count constraints fail at high cardinality.
- **Ordinal categoricals**: chi-squared ignores ordering. If both categoricals are ordinal, consider Spearman/Kendall on the rank versions, or use a test of trend (Mantel-Haenszel chi-squared with ordinal scores).
- **Mixed levels**: collapsing categories changes the inference; document any collapse decision in `caveats`.

## Anti-patterns

- Reporting a significant chi-squared without residuals. The reader knows there's an association but not where.
- Running chi-squared on a table where expected counts violate the ≥ 5 rule. Use Fisher's exact.
- Stratifying after seeing a marginal result without checking the marginal first (or vice versa) — Simpson's Paradox lives at this seam. See `simpsons-paradox-check.md`.
- Treating Cramér's V close to 0.1 on n = 10M as a strong finding. Effect size is the signal; statistical significance with huge *n* picks up trivial associations.

## Output-shape discipline

Code execution returns the contingency table (counts and percentages), test statistic, p-value, effect size, and residuals matrix — small for the table dimensions in scope. Never return the underlying long-format data; the table is the summary.
