# Analytical Skill: STL Decomposition

**Loaded by:** Time Series Analyzer.
**Purpose:** Separate a time series into trend, seasonal, and residual components so that each component can be analyzed on its own terms. STL (Seasonal-Trend decomposition using Loess) is robust to outliers and handles multiple seasonalities better than classical decomposition.

## When to apply

- Series has ≥ 2 full cycles of the suspected seasonality (e.g., ≥ 2 years for annual seasonality on weekly data; ≥ 2 weeks for weekly seasonality on daily data).
- The question depends on disentangling whether a change is trend, seasonal, or anomalous.
- A change-point search or residual-outlier search is downstream — STL residuals are usually a better input than raw values. See [change-point-detection.md](change-point-detection.md).

**Do not apply** to series shorter than 2 cycles, to series with severe non-stationary volatility (consider variance-stabilizing transformation first), or to series that are fundamentally event-driven rather than periodic.

## Period detection

If the period is not obvious from domain context:
1. Check the domain context document — most business series have a stated cadence (weekly, monthly, etc.).
2. Otherwise use a periodogram or autocorrelation function to find the dominant periodicity. Report the detected period and its strength.

For CPG demo data, weekly periodicity (period = 7 days for daily series; period = 52 weeks for weekly series tracking annual seasonality) is the typical default.

## Multiplicative vs. additive

| Choose multiplicative when | Choose additive when |
|---|---|
| Seasonal amplitude grows with the level (peaks get bigger as the series trends up) | Seasonal amplitude is roughly constant across levels |
| Series is strictly positive and varies over orders of magnitude | Series is roughly bounded |

A quick check: apply both, plot the residuals, and choose whichever produces flatter, more homoscedastic residuals. Or apply STL on `log(series)` and back-transform — this is mathematically equivalent to multiplicative for strictly-positive series and often easier to interpret.

## Required reporting

For each STL run, emit a `Statistic`-bearing structure containing:

- **Period** detected or specified.
- **Trend strength**: 1 − Var(residual) / Var(trend + residual). Range 0–1; closer to 1 means trend dominates.
- **Seasonal strength**: 1 − Var(residual) / Var(seasonal + residual). Range 0–1.
- **Residual diagnostics**: mean (should be near 0), variance, autocorrelation at lag 1 (should be near 0 for a good decomposition).
- **Residual outliers**: count and timestamps of points with |z| > 3 on the residual series (these feed change-point detection or temporal-outlier investigation).
- **Trend slope** over the most recent N periods, with a CI — quantifies the recent direction. Use `lag-lead-analysis` (deferred MVP skill) if direction matters relative to a peer series.

## Anti-patterns

- Reporting the trend component as if it were the series itself. The decomposition is descriptive; "the trend is up" doesn't mean the actual series is up if seasonality currently dominates.
- Applying additive decomposition to a clearly multiplicative series (heteroscedastic residuals are the giveaway).
- Treating residual spikes as evidence of a *cause*. A spike is a question for the Root Cause Investigator; STL just isolates it.
- Running STL on a 6-month series with claimed annual seasonality. You need enough cycles to estimate the seasonal component.
- Treating "trend up" over the last 4 weeks as a finding without checking the CI on the slope. Short-window slopes are noisy.

## Output-shape discipline

Code execution returns the component-strength scalars, residual diagnostics, residual-outlier summary (count + small list of timestamps), and trend-slope statistics — never the full trend/seasonal/residual arrays. Those stay in the sandbox. If a downstream agent needs to visualize, it queries by filter expression for the specific window.
