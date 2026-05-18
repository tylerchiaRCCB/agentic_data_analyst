# Output Skill: Visualization Recommendations

**Loaded by:** Communication Agent.
**Purpose:** Recommend an appropriate chart type for each finding, based on the data shape and the analytical purpose. The MVP tool does not render charts; the recommendations guide the downstream user or BI team that builds the chart.

A good visualization recommendation does three things: (1) names a specific chart type, (2) names the variables and aggregations the chart should use, (3) explains what the chart should reveal that the prose alone does not.

## Chart selection by analytical purpose

| Analytical purpose | Recommended chart type | What it shows |
|---|---|---|
| **Compare values across a small number of categories** *(e.g., top 5 entities by metric)* | Horizontal bar chart, sorted | Magnitude ranking; easy to read entity names |
| **Compare values across many categories** | Dot plot, sorted, or strip plot | Avoids visual clutter of long bar charts |
| **Show distribution of a single metric** | Histogram (normal-ish data) or box plot (skewed; shows median, IQR, outliers) | Distribution shape, location, spread, outliers |
| **Compare distributions across groups** | Side-by-side box plots, or violin plot if shape detail matters | Group-level differences in median, spread, outlier presence |
| **Show change over time** | Line chart, single or small-multiple | Trend, seasonality, change points |
| **Show change over time with seasonality stripped** | Two-panel line chart: raw series + trend component from STL | Separates seasonal from underlying trend |
| **Show change points / regime shifts** | Line chart with vertical change-point markers + before/after means | Highlights the timing and magnitude of detected shifts |
| **Show relationship between two continuous variables** | Scatter plot, with regression line if linear; with rolling-mean overlay if not | Direction, strength, presence of outliers, linearity |
| **Show relationship between two continuous variables conditional on a third** | Scatter plot faceted by the third variable, or color-encoded | Reveals conditional patterns that aggregate scatter hides |
| **Show contributions to a total** | Stacked bar (across time / categories) or waterfall | Decomposition of the aggregate into components |
| **Show progress / share** | Bar chart with reference line at target; or 100% stacked bar | Where each entity stands vs. the goal |
| **Show retention / cohort curves** | Cohort triangle heatmap, or overlaid line chart per cohort | Cohort behavior across maturity periods |
| **Show clustering** | Scatter on first 2 components (PCA / UMAP) colored by cluster | Cluster structure in reduced space |
| **Show Simpson's-Paradox-style mix shift** | Pair of bar charts: aggregate vs. stratified; or paired box plots with aggregate line overlay | Direction reversal between aggregate and subgroup |

## Anti-patterns in chart choice

These come up often and should be flagged when an upstream analytical agent's preferred chart would mislead:

- **Pie charts for more than ~5 categories.** Bar/dot plots are more readable.
- **3D bar charts.** Depth distorts magnitude comparison. Use 2D.
- **Dual-axis line charts** when the two axes have very different scales or units. Often misleading; prefer separate panels or normalized series.
- **Truncated y-axes** that exaggerate small differences. The chart should not over-dramatize the finding the prose has stated with calibrated language.
- **Default-binned histograms** on skewed data. Default bin choices can create false bimodality or hide real structure. Recommend `bins='auto'` or a domain-appropriate bin count.
- **Line charts on categorical x-axes.** Lines imply continuity; if the x-axis is categorical, use bars or dots.
- **Connecting averages with lines across discrete categories** ("trend lines" through bars). Suggests a trend that doesn't exist.

## Format of the recommendation

For each finding worth visualizing, the recommendation in the artifact's `visualization_recommendations[]` carries three fields:

```json
{
  "finding_id": "<refs the Finding.id>",
  "chart_type": "<specific type from the table above>",
  "rationale": "<what the chart should reveal, named axes / variables, any aggregation / normalization>"
}
```

Example rationale (sales finding): *"Line chart of Account 47's weekly instock rate (y-axis, 0–100%) over the past 16 weeks (x-axis), with a horizontal reference line at the 90% concern threshold and a vertical marker at the detected change-point (week of 2026-04-13). Reveals the magnitude and timing of the drop, and visually distinguishes single-week noise from the sustained shift."*

## When NOT to recommend a chart

- **Pure single-value findings.** *"Account 47's instock is 72%"* doesn't need a chart; the number is the finding.
- **When the recommended chart would require data the recipient cannot access.** If the chart depends on a slice the recipient doesn't have BI access to, recommend it but flag the access gap.
- **For grade-C findings.** Visualizations can over-substantiate a preliminary signal. For grade-C, prefer a short text framing without a chart, or recommend a chart with the caveat that it should be read as a candidate pattern, not a confirmed one.

## Practical defaults for proactive monitoring

In the proactive-monitoring pipeline, the most common chart recommendations the Communication Agent will issue:

- **Time series with change point** for any finding from the Time Series Analyzer's change-point detection. Recipient sees the timing of the shift.
- **Box plot comparison** for any group-comparison finding from the Relationship Analyzer. Recipient sees medians, spreads, outliers across the compared groups.
- **Sorted bar / dot plot** for top-N entity findings. Recipient sees where the focal entity sits.
- **Decomposition waterfall** for performance-gap-analysis findings. Recipient sees which components contribute what share of the gap.
- **Cohort heatmap** for cohort-analysis findings. Recipient sees cohort-on-cohort regression or maturity-period patterns.

## Anti-patterns

- Recommending charts the recipient cannot build. The recommendation is only useful if the underlying data and tooling are available to the recipient or their BI team.
- Recommending the same chart type for every finding. Different findings have different shapes; the recommendation should match.
- Over-recommending. Not every finding needs a chart — text-only is fine when the number is the finding.
- Vague recommendations. *"Make a chart of the trend"* is not useful. The recommendation names the chart type, the axes, the aggregation, and what the chart should reveal.

## Tie to framing

A good chart recommendation gives the recipient the option to see for themselves. A recipient who builds a recommended chart and finds the pattern visible in the data is recipient earning their own trust in the finding — which is the most durable trust the system can produce. A chart recommendation that would over-dramatize, mislead, or selectively show the data violates that trust; recommend honestly.

## Output discipline

This skill is loaded with every Communication Agent call. Visualization recommendations go in the artifact's `visualization_recommendations` array and are surfaced in action cards via the *VISUALIZATION SUGGESTED* field (see [proactive-action-card.md](proactive-action-card.md)). The MVP tool does not render charts; production may add rendering via a downstream BI integration.
