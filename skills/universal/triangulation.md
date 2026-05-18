# Universal Skill: Triangulation

**Role:** A finding becomes a conclusion only when it survives examination from multiple lenses. Loaded with every agent call; primarily exercised by analytical agents and the Findings Validator.

A pattern that appears under one cut of the data and disappears under another is not yet a finding — it is a *candidate*. Triangulation is the process of testing whether a candidate is robust.

## The five lenses

Before presenting a candidate as a finding, verify it from at least three of the following five lenses (more is better):

1. **Multiple time windows.** Does the pattern hold over the last 4 weeks, last 13 weeks, and same-period prior year? A pattern visible only in a single chosen window is suspect; the window may have been selected (consciously or not) for the pattern.

2. **Multiple aggregation levels.** Does the pattern hold at the daily/weekly/monthly level? Does it hold at the account/region/national level? Patterns that exist only at one aggregation often reflect noise smoothed in or smoothed out by aggregation choice.

3. **Multiple metrics.** Is the pattern visible in related metrics that should move together? *(Examples across our CPG functional domains: volume and revenue (sales); instock and fill rate (supply chain); shipments and orders (logistics); promotional lift and trade spend (trade marketing); production output and downtime (operations); gross margin and trade deductions (finance).)* If a pattern in metric A is not echoed in any related metric, that is a red flag — either the metric is mis-measured or the pattern is spurious.

4. **Multiple comparison baselines.** Is the deviation visible against last-year baseline, against trailing-period baseline, and against peer-group baseline? Patterns that look extreme against one baseline but not others often reflect baseline anomalies, not signal.

5. **Multiple population cuts.** Does the pattern hold within demographic, geographic, or segment cuts of the relevant population? If a national-level finding disappears when split by region, the national pattern is a mixture, not a uniform signal. (This is also the Simpson's Paradox check.)

## Required practices

- For any finding promoted toward an action card (grade A or B), document in the artifact's `caveats` or in the `triangulation_evidence` portion of the finding *which* lenses were checked and what they showed.
- When fewer than three lenses confirm a candidate, the candidate must be downgraded to preliminary (grade C maximum) or filtered (grade D), not promoted.
- When lenses disagree, *both* the supportive and the disconfirming lenses must be reported. Suppressing the disconfirming lens to preserve a narrative is a methodology failure.
- The Findings Validator independently verifies triangulation — an upstream agent claiming triangulation is not sufficient; the Validator should recompute at least one lens.

## Anti-patterns

- Presenting a single-window, single-aggregation, single-metric pattern as a finding.
- Triangulation-by-citation: claiming "we checked multiple windows" without recording what each window showed.
- Choosing the time window that maximizes the apparent signal (window-shopping). Pre-commit to comparison windows when possible.
- Reporting only the confirming lens when others were also checked.
