# Universal Skill: Data Quality Standards

**Role:** Measure data quality, never assume it. Distinguish data-quality artifacts from genuine business signal. Loaded with every agent call; the Data Profiler is its primary owner, but every downstream agent uses these standards to interpret what the Profiler emitted.

## Required practices

1. **Profile completeness, freshness, grain, and distributions before analyzing.** For any metric the analysis touches:
   - **Completeness** — null rate per column over the time window in question. Note whether nulls are concentrated in specific time periods, entities, or segments (this often points to data-pipeline artifacts, not business reality).
   - **Freshness** — timestamp of the most recent record vs. the expected cadence. Stale data must be flagged.
   - **Grain** — the declared unit of analysis (one row per X) and a verified check that the actual data matches. Duplicate rows at the declared grain are a quality issue.
   - **Distributions** — shape (normal, skewed, bimodal, long-tail), location (mean, median), spread, and outlier counts. This determines test selection and informs whether resistant statistics are required (see [resistant-statistics.md](resistant-statistics.md)).

2. **Establish baselines.** A metric value with no comparison is uninterpretable. Every analyzed metric should have at least one baseline computed and stored — typical comparisons: same period prior year, trailing 4-week / 13-week average, peer-group average. Baselines live in the Profiler artifact and are consumed by downstream agents.

3. **Distinguish data-quality issues from business anomalies.** An apparent anomaly may be:
   - A genuine business event (real change in the world).
   - A data-pipeline artifact (refresh delay, ETL glitch, schema change, mapping issue).
   - A definitional artifact (metric was redefined; comparison crosses the boundary).
   Always check the second and third causes before treating an observation as a business signal. If the profiler cannot rule them out, surface the ambiguity as a high-severity caveat and let downstream agents treat the anomaly as provisional.

4. **Surface integrity risks proactively.** Simpson's Paradox risk (subgroup direction reverses aggregate direction), survivorship bias (entities present only because they survived), and selection bias (filter criteria correlate with the outcome variable) must be flagged when the data shape suggests them, even if no agent has yet asked. See `simpsons-paradox-check.md` for the explicit check methodology.

## Anti-patterns

- Stating completeness "looks fine" without computing the null rate.
- Treating a metric value as meaningful without a baseline.
- Investigating an apparent anomaly without first asking "could this be a data pipeline artifact?"
- Reporting an aggregate without checking whether subgroup behavior tells a different story.
- Reading completeness as "we have the columns" rather than "the values in the columns are present and at the expected grain."
