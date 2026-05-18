# Analytical Skill: Outlier Typology

**Loaded by:** Data Profiler (univariate outliers), Pattern Discoverer (multivariate / structural outliers), Time Series Analyzer (temporal outliers).
**Purpose:** Distinguish *types* of outliers, route each type to the right agent, and treat outliers as questions to investigate rather than rows to filter.

An outlier is not a single thing. It is the answer to "this point doesn't fit a model of the rest." The model determines what counts. Different models surface different outliers, and conflating them produces bad analysis.

## The four types

### 1. Univariate outliers
Definition: a row whose value on a single variable is extreme relative to the rest of the values on that variable.

Owned by: **Data Profiler.**

Detection:
- For approximately normal distributions: |z-score| > 3.
- For skewed distributions (the default for most business metrics): **modified z-score** (0.6745·(x − median) / MAD) > 3.5. See [resistant-statistics.md](../universal/resistant-statistics.md).
- For long-tailed: also report quantile position (e.g., "above 99.5th percentile").

What they mean: usually a data-quality flag (entry error, unit error, system bug) or a known business edge case. Most univariate outliers are not "interesting findings" — they're cleanup candidates or known-special cases.

### 2. Multivariate / structural outliers
Definition: a row whose *combination* of values is unusual, even if no single value is extreme. E.g., an account with average volume *and* average promo frequency is unremarkable on each axis but unusual if those two are typically inversely correlated.

Owned by: **Pattern Discoverer.**

Detection:
- **Mahalanobis distance** on a robust covariance estimate (e.g., Minimum Covariance Determinant) — threshold via chi-squared quantile on degrees of freedom equal to the feature count.
- **Isolation Forest** for non-Gaussian feature distributions.
- **DBSCAN noise points** (see [clustering-algorithms.md](clustering-algorithms.md)).

What they mean: candidates for investigation. A multivariate outlier is often a business story — an account that broke the typical relationship between two operational variables.

### 3. Temporal outliers
Definition: a row whose value at a specific point in time is extreme relative to its own history (and possibly its peers' contemporaneous values).

Owned by: **Time Series Analyzer.**

Detection:
- **Hampel filter** residuals (median absolute deviation in a rolling window).
- **STL residuals** outside a stated band after seasonal/trend removal.
- **Z-score on the differenced series** for non-stationary data.

What they mean: a one-period spike or drop. May be a real event (stockout, promo, system outage) or a data artifact (refresh delay). Always cross-check against known events in the domain context.

### 4. Contextual / conditional outliers
Definition: a row that is unusual *given* a third variable. E.g., a sales value is fine for August but extreme for January.

Owned by: **Relationship Analyzer** (when the conditioning variable is structural) or **Time Series Analyzer** (when conditioning is temporal).

Detection: residuals from a fitted model that controls for the conditioning variable (e.g., regression residuals; cohort-relative scores; conditional quantile thresholds).

What they mean: usually the most analytically interesting class. A point that looks normal in aggregate but unusual when conditioned on context often points to the "why" question.

## Required practices

1. **Always state the outlier type.** "Account 47 is an outlier" is incomplete. "Account 47 is a multivariate outlier on (volume, promo_frequency, days_of_supply) using robust Mahalanobis with Minimum Covariance Determinant" is a finding.
2. **Compute resistantly.** Mean ± 3·SD is fragile on skewed data — the SD itself is inflated by the outliers, so the threshold over-counts on small data and under-counts on large. Default to median/MAD or quantile-based.
3. **Distinguish data quality from business signal.** A univariate outlier of −9999 on a sales field is a sentinel value, not a business event. The Profiler should flag it as a data-quality issue, not pass it to the Root Cause Investigator.
4. **Do not auto-filter.** Removing outliers without an explained reason silently changes the analysis. If a record is excluded, the exclusion criterion and count appear in the artifact's `caveats`.
5. **Outliers are questions, not answers.** A 3-sigma deviation is "worth investigating," not "the finding." Downstream agents must investigate; the Validator must grade.

## Anti-patterns

- Using a single method for all outlier types. Univariate methods miss structural outliers; structural methods miss temporal ones.
- Reporting outlier counts without typology. The reader cannot interpret without knowing what counts.
- Treating outlier removal as data cleaning by default. On a distribution that *is* heavy-tailed, the tails are the data — removing them produces a fictional smooth dataset.
- Promoting a univariate outlier to an action card. Most are not actionable findings; route them to data quality, not to stakeholders.

## Output-shape discipline

Code execution returns outlier counts by type, threshold parameters, and *small* lists of specific outlier IDs (typically ≤ 50) for downstream agents to investigate. Never return the entire post-filter dataset.
