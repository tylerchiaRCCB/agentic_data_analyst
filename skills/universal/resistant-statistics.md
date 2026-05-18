# Universal Skill: Resistant Statistics

**Role:** For skewed and heavy-tailed distributions — the norm across our CPG company's functional domains (sales volume, supply chain DOS, manufacturing cycle times, finance margin per case, trade lift) — use resistant statistics instead of mean/SD. Loaded with every agent call; primarily exercised by the Data Profiler, Relationship Analyzer, Pattern Discoverer, and Time Series Analyzer.

The mean and standard deviation are dominated by extreme values. On a right-skewed distribution, the "average" describes neither the typical value nor the bulk of the data — it describes a value that almost no record actually has. Inference built on these statistics misleads. Resistant statistics replace them.

## When to use which

Default decision rule, applied after the Data Profiler classifies the distribution shape:

| Distribution shape | Center | Spread | Standardization | Outlier detection |
|---|---|---|---|---|
| Approximately normal | mean | standard deviation | z-score | mean ± 3·SD |
| Right-skewed, left-skewed, heavy-tailed | **median** | **MAD** (median absolute deviation) | **modified z-score** (0.6745 × (x − median) / MAD) | **\|modified z\| > 3.5** |
| Bimodal | report both modes; do not summarize with a single center | IQR per mode | mode-specific | requires segmentation first |
| Long-tail (e.g., velocity) | **median** + **trimmed mean** (10–20%) | **IQR** | **Hampel filter** for time series | Hampel |
| Categorical | mode + frequency table | n/a | n/a | rare-category flagging |

The Data Profiler's `distributions[<metric>].use_resistant_statistics` boolean drives this. When `true`, downstream agents must use resistant statistics for that metric. When `false`, classical statistics are appropriate.

## Required practices

1. **Profile before summarizing.** Never report a mean without first checking distribution shape. The Profiler does this for every metric; downstream agents consult the Profiler's classification.

2. **Pair the center with the spread.** Median is meaningful only alongside IQR or MAD. Mean is meaningful only alongside SD. Reporting one without the other is incomplete.

3. **Apply Hampel filtering before time-series methods on skewed series.** Mean-shift change-point detection on raw skewed series produces too many false positives because spikes (promotional periods, one-off events, sparse high-magnitude observations) dominate. Hampel-filter the series first, then run change-point detection on the residual or the smoothed series.

4. **Use rank-based tests when assumptions of parametric tests fail.** Spearman correlation, Mann-Whitney U, Kruskal-Wallis — these have lower power than parametric alternatives when the parametric assumptions hold, but they don't break when those assumptions fail. The Profiler's shape classification should drive this choice; see [statistical-rigor.md](statistical-rigor.md) §3.

5. **For comparison to baseline, prefer percent change against median over percent change against mean** on skewed metrics — a single high-magnitude period can move the mean enough to make a normal period look anomalous.

## Common cases across our CPG functional domains

The pattern below recurs across the functional domains the system serves; the named metrics are illustrations, not the rule:

- **Entity-level transaction volume** *(Example, sales: account-level weekly cases; supply chain: shipments per DC per day)*. Right-skewed — a small share of entities dominates. Use median + IQR. For ranking, decile or quartile membership is more interpretable than absolute volume.
- **Stock or supply metrics** *(Example, supply chain: days-of-supply per SKU-account; operations: WIP inventory by line)*. Long-tailed — most are fine; a few are deeply over- or under-stocked. The outliers are the finding, not the summary; report median and surface the tails separately.
- **Lift or response metrics** *(Example, trade marketing: promotional lift by event; commercial: incremental volume by initiative)*. Skewed because most interventions are flat and a few are large. Median and quartile boundaries describe the experience better than the mean.
- **Duration / cycle-time metrics** *(Example, operations: changeover time per line; supply chain: order-to-ship cycle time; finance: days sales outstanding by customer)*. Right-skewed with long tails. Trimmed mean (10–20%) or median + IQR rather than mean + SD.

## Anti-patterns

- Reporting "average X" without checking shape. On a skewed distribution, the average misrepresents typical performance.
- Defining "outlier" via mean ± 3·SD on a skewed distribution — this either flags far too many normal records or fails to flag genuine extremes.
- Running parametric tests on visibly skewed data because their output (t-statistic, R²) is more familiar than rank-based alternatives.
- Treating a high standard deviation as "high variability" without checking whether one or two extreme records produced it.
