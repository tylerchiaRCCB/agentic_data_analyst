# Analytical Skill: Cohort Analysis

**Loaded by:** Time Series Analyzer.
**Purpose:** Track how groups defined by a shared starting condition evolve over time. Cohort analysis is the right tool when the question is *"how does X change as time-since-start grows"* rather than *"what was X at a given calendar date."*

## When to apply

- The analysis depends on time-since-entry (tenure, lifecycle, weeks-since-onboarding) rather than calendar time.
- Comparing groups that began at different points is misleading on calendar-time axes — promo lift in week 3 of a new launch should compare to week 3 of past launches, not to last Tuesday.
- Retention, repeat purchase, ramp curves, post-event recovery — all natural cohort questions.

## Cohort definition

Three decisions to record explicitly:

1. **Cohort identifier.** What event defines membership? First purchase week. Onboarding date. Promotion start. Specify the event and how it is operationalized (column name, filter logic).

2. **Cohort granularity.** Weekly, monthly, quarterly cohorts. Trade-off: finer granularity gives more cohorts but smaller per-cohort *n*. Common defaults: monthly cohorts for launch / signup analysis; quarterly for slower-moving outcomes.

3. **Maturity axis.** Weeks-since-cohort, months-since-cohort. Time-since-start, not calendar.

Record all three in the artifact under `cohort_findings[].cohort_definition`.

*Examples of cohort definition across our CPG functional domains:* sales — product-launch cohorts by launch week; commercial — new-account cohorts by activation month; supply chain — SKU-introduction cohorts by first-shipment week; trade marketing — promotional-event cohorts by event-start week; HR / people analytics — new-hire cohorts by quarter; operations — production-line cohorts by commissioning date.

## Required computations

For each (cohort, maturity-period) cell:
- Sample size (count of entities in the cohort still present in the maturity period).
- Central tendency of the outcome metric (median preferred on skewed; see [resistant-statistics.md](../universal/resistant-statistics.md)).
- Spread (IQR or CI on the central tendency).
- For retention-style metrics: surviving fraction relative to cohort-period-0 count.

The result is a **cohort matrix** (cohorts × maturity periods). Two summary views:

- **Triangle / heatmap** view: show the full matrix as a heatmap on a chart (recommended via [visualization-recommendations.md](../output/visualization-recommendations.md) in MVP output — the tool does not render).
- **Curve view**: each cohort as a line on a (maturity-period, outcome) chart, overlaid.

## What to look for

- **Cohort-on-cohort regression**: later cohorts performing worse at the same maturity than earlier cohorts. Signals a structural change in the underlying process (acquisition quality, market conditions, product changes).
- **Maturity-period anomalies**: a specific tenure where outcomes drop sharply (e.g., week 4 dip across all cohorts). Often reflects a structural artifact (subscription renewal point, contract decision point).
- **Cohort-specific anomalies**: one cohort behaving differently across all maturity periods. Points to an event-at-onboarding cause.

Distinguish the three patterns; they have different downstream implications. Cohort-on-cohort regression is the Opportunity Identifier's concern. Maturity-period dips are Root Cause Investigator territory. Cohort-specific anomalies trigger an event-coincidence check against the domain context's quirks section.

## Required reporting

For each notable pattern, emit a `Finding` with:
- Cohort and maturity-period coordinates of the observation.
- Effect size relative to a stated reference (most common: same maturity period, prior cohort, or pooled-across-cohorts baseline).
- Sample sizes at the relevant cells — small cohorts produce unreliable curves.
- Triangulation (see [triangulation.md](../universal/triangulation.md)): does the pattern hold under different cohort granularities or different baseline choices?

## Anti-patterns

- Comparing cohorts on calendar time rather than maturity time. Defeats the purpose.
- Reporting cohort curves without sample sizes. The last few maturity periods of a cohort are noisy because they are sparse.
- Treating a single cohort's behavior as a finding without comparing to other cohorts at the same maturity.
- Cohort definitions that drift across the analysis (e.g., "promo cohorts" defined by participation in *any* promo without specifying which one).

## Output-shape discipline

Code execution returns the cohort matrix as a small aggregated table (cohorts × maturity periods × outcome stats). For typical CPG cohort analysis this is on the order of 12–24 cohorts × 12–52 maturity periods — small. Never return the per-entity, per-period long-format frame.
