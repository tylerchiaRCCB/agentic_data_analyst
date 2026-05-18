# Analytical Skill: Hypothesis Testing

**Loaded by:** Relationship Analyzer, Root Cause Investigator, Findings Validator.
**Purpose:** Formalize the act of testing a claim against data. Stating a hypothesis, choosing a test, computing the statistic, reporting the full picture, and interpreting the result in proportion to the evidence.

This skill is the connective tissue across [correlation-analysis.md](correlation-analysis.md), [group-comparison.md](group-comparison.md), and [cross-tabulation.md](cross-tabulation.md) — those define the *what* of each test; this defines the *how* of conducting any test rigorously.

## State the hypothesis

Before any computation:

1. **Null hypothesis (H₀)** — the default state assumed in the absence of evidence. State it explicitly. E.g., *"No difference in median weekly volume between Account 47 and the peer group's pooled distribution."*
2. **Alternative hypothesis (H₁)** — the claim being tested. Specify whether it is one-sided or two-sided.
   - One-sided is appropriate when domain reasoning genuinely justifies a single direction (e.g., *"Account 47's volume is **lower** than peers"*) and that direction was decided **before seeing the test result**. Otherwise, two-sided.
3. **Significance level (α)** — default 0.05 for individual tests; **lower (e.g., 0.01) when running many tests** unless multiple-comparison correction is applied (preferred — apply Benjamini-Hochberg FDR at q = 0.10 for exploratory work, Bonferroni for confirmatory; see [statistical-rigor.md](../universal/statistical-rigor.md) §4. A dedicated `multiple-comparison-correction.md` skill is deferred to Phase 2).
4. **Decision rule** — what the agent will do with each possible outcome (significant, non-significant, marginal). Pre-commit to this. The decision rule especially matters for the "non-significant" case — see Required Reporting below.

## Choose the test

Test selection is determined by the data structure (continuous vs. categorical, paired vs. independent, normality, sample size, etc.). See the selection tables in [correlation-analysis.md](correlation-analysis.md), [group-comparison.md](group-comparison.md), and [cross-tabulation.md](cross-tabulation.md). Default to non-parametric / robust alternatives on skewed data unless the Profiler has confirmed normality.

## Compute

All test statistics, p-values, confidence intervals, and effect sizes come from executed code, returning small scalar results. Emit a `Statistic` per test.

## Report the full picture

For every test, the artifact must include:

- The hypothesis pair (H₀, H₁).
- The test name and any assumption checks performed.
- Sample size(s).
- Test statistic value.
- **Confidence interval on the parameter of interest** (the difference, the correlation, the ratio — not "on the test statistic" but on the underlying quantity).
- p-value.
- **Effect size** with its interpretation tier (Cohen's d / Cramér's V / etc.). See [effect-size-calculation.md](effect-size-calculation.md).
- Multiple-comparison correction context if applicable.
- Decision: H₀ retained / H₀ rejected / inconclusive (and why).

## Interpreting non-significant results

A non-significant test is **not** evidence that H₀ is true. It is the absence of evidence sufficient to reject it. Distinguish:

- **Adequately powered, non-significant** → reasonable evidence that the effect, if it exists, is smaller than the minimum detectable effect at this sample size. Report the **minimum detectable effect size** so the reader knows what was ruled out.
- **Underpowered, non-significant** → the test cannot distinguish "no effect" from "a real effect we couldn't detect." Report the achieved power; if it is < 0.80, the test is inconclusive, not "no effect."

Hypotheses that the Root Cause Investigator tests and finds non-significant should be reported in `rejected_hypotheses` only when the test was adequately powered. Underpowered non-significance belongs in `open_questions`.

## Anti-patterns

- Choosing one-sided after seeing the data. Inflates the false-positive rate.
- Reporting only "p < 0.05" without effect size, CI, or sample size. Recipients cannot judge importance.
- Treating non-significance as evidence of "no effect" without checking power.
- Adjusting the hypothesis after seeing the data ("HARKing" — Hypothesizing After Results are Known). Pre-specify; if the data suggests a new hypothesis, that hypothesis must be tested on different data or labeled exploratory.
- Running many tests, picking the one with p < 0.05, and reporting it without correction. See [statistical-rigor.md](../universal/statistical-rigor.md) §4.
- Reading a confidence interval that includes zero as "no relationship." It means "the data are consistent with effects ranging from <lower> to <upper>" — the CI bounds are the actual finding.

## Tie to framing

The discipline this skill enforces is what allows the system to honestly report negative or null findings. *"We tested this hypothesis at adequate power; it was not supported"* is a complete and valid finding. The Communication Agent can fold such results into the descriptive summary or, in interactive mode, surface them directly. They are not failures of the analysis.

## Output-shape discipline

Code execution returns scalars (test statistic, p-value, CI bounds, effect size) and small descriptive summaries (group sizes, means/medians). Never returns raw vectors of group-membership labels or per-row residuals to context.
