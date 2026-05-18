# Analytical Skill: Change Point Detection

**Loaded by:** Time Series Analyzer.
**Purpose:** Identify points in a time series where the underlying generating process shifts — a level change, a variance change, or a slope change. Distinguish *changes* from *anomalies*: a change point is a durable shift; an anomaly is a single-period excursion.

## Method selection

| Question | Method | Notes |
|---|---|---|
| Where did the mean of this series shift? (Online or near-real-time) | **CUSUM** (cumulative sum) | Sensitive; tunable via reference value `k` and decision threshold `h`. Best for detecting small persistent shifts. |
| Where are the optimal segmentation breakpoints? (Retrospective) | **PELT** (Pruned Exact Linear Time) with appropriate cost function | Computationally efficient on long series; choice of cost function (RBF, L2, normal) determines what kind of change is detected. |
| Bayesian / probabilistic change points? | **Bayesian online change-point detection (BOCPD)** | Returns a probability per timestamp; useful when uncertainty quantification matters. Heavier compute. |
| Multiple change points with sparse signal? | **Binary segmentation** or **WBS (wild binary segmentation)** | Recursive; can be unstable on noisy data — validate against PELT. |
| Variance shifts (not mean)? | Use a cost function that detects variance change, e.g., **changepoint::cpt.var** style. | Many CPG metrics have variance shifts (volatility regime changes) without mean shifts. |

For most CPG series in the MVP demo (weekly counts and rates), **PELT with an L2 cost** on the **STL residual** (see [stl-decomposition.md](stl-decomposition.md)) is the default. Running on raw values dominates the detection with seasonality.

## Required steps

1. **Preprocess.** For seasonal series, decompose first and run change-point detection on the residual. For volatile / heavy-tailed series, apply a Hampel filter first to reduce single-point dominance. See [resistant-statistics.md](../universal/resistant-statistics.md).

2. **Select penalty / threshold.** Penalty (PELT) or threshold (CUSUM) controls sensitivity. Two strategies:
   - **BIC- or AIC-based** penalty (default for PELT) — principled and reproducible.
   - **Cross-validation** on held-out segments — more accurate but heavier.
   Report the penalty value used; over-sensitive detection produces lots of spurious "changes."

3. **Validate.**
   - **Magnitude check**: for each detected change point, compute the difference in means (or appropriate parameter) before vs. after. If the change is smaller than the noise band of the series, downgrade to noise.
   - **Persistence check**: the new regime should last at least N periods (define N from domain context — for weekly CPG data, often 4–8 weeks). Single-period excursions are anomalies, not change points.
   - **Cross-method sanity**: if multiple methods agree on a timestamp, confidence is higher. If only one method finds it, treat as candidate, not finding.

4. **Cross-reference with known events.** The domain context document's quirks section lists known artifacts (system migrations, definition changes). A "change point" that aligns with a known artifact is a data event, not a business event — flag accordingly.

## Required reporting

For each detected change point, emit:

- Timestamp.
- Metric.
- Magnitude of the shift (with CI).
- Method used and penalty/threshold value.
- Confidence: low / medium / high based on validation steps above.
- Coincidence with known events from the domain context, if any.
- Type: mean shift / variance shift / slope shift.

## Anti-patterns

- Running change-point detection on raw seasonal series — you find the season, not the change.
- Reporting every detected point as a finding without persistence and magnitude checks. Most change-point algorithms over-detect by default.
- Asserting a *cause* for a detected change point. Detection identifies *when* the regime shifted; the *why* is for the Root Cause Investigator.
- Single-method confidence. Cross-validate before promoting to grade A.
- Treating an unconfirmed change point at the very end of the series as confirmed. The most recent periods always look uncertain because the post-change regime has few observations.

## Output-shape discipline

Code execution returns the list of detected timestamps with their magnitudes and confidence levels — typically very small (≤ ~20 detections). Never return the full filtered or decomposed series.
