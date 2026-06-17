# Output Skill: Descriptive Summary Format

**Loaded by:** Communication Agent.
**Purpose:** Render the output for runs (or portions of runs) where no findings rose to action level. This output is **a first-class output**, not a fallback. The system says "nothing concerning this period, here is your summary" with the same craft and respect for recipient attention as it brings to action cards.

If this skill is invoked, the run did its job. The data was examined, baselines were checked, and the analysis concluded — honestly — that nothing required attention. The descriptive summary documents that work so the recipient understands what was looked at, what would have constituted a finding, and that none was found.

**BREVITY RULES:**
- The entire Weekly Summary section (excluding `<details>` blocks) must be **under 600 words**.
- "What's stable" = **3-6 one-line bullets**. Each bullet is ONE line — metric, value, direction.
- "Structural observations" = **maximum 3 bullets, each 2 sentences max**. No paragraph-length observations.
- "What would have constituted a finding" = **maximum 3 bullets**. Only the most decision-relevant thresholds.
- "Conclusion" = **1-2 sentences**. State the all-clear.
- Open data gaps table = **maximum 4 rows**. Only HIGH and MEDIUM priority.
- All methodology and statistical detail goes in `<details>` blocks — never in the body.
- **COMPRESS, DON'T DISCARD:** Any additional stable metrics, structural observations, thresholds checked, or data gaps beyond these limits go into the summary's `<details>` audit trail block. The body is the executive layer; `<details>` is the complete analyst record.

## Why this output exists

The strongest demonstration of the system's discipline is its ability to remain quiet when staying quiet is the right answer. A tool that fabricates findings to fill space erodes recipient trust on every run; a tool that produces a brief, useful descriptive summary on quiet weeks earns trust on every run.

This is the spec's *"nothing concerning this week, here is the descriptive summary"* output. Treat it accordingly.

## Format — rendered markdown, NOT a code-fenced block

The descriptive summary is rendered as native markdown — same principle as the action cards. **Do NOT wrap the summary in `` ``` `` code fences.** That breaks visual hierarchy and looks like terminal output.

### Canonical template

```markdown
## Weekly Summary — <domain> — <period>

*Covers areas examined that did NOT produce action cards.*

### What's stable

- **<Metric 1>:** <one-line plain English — value, direction, comparison>
- **<Metric 2>:** <one-line plain English>
- **<Metric 3>:** <one-line plain English>
- *(typically 3–6 bullets; each is one line)*

### Structural observations (no action required)

*Use this section for grade-C findings or relationships that are real but not card-worthy.*

- **<Observation 1>:** <one short paragraph in plain English. Statistical methodology in the Methodology footer.>
- **<Observation 2>:** <one short paragraph>

### What would have constituted a finding

> What thresholds was the system looking for that weren't crossed?

- <Concrete signal 1 the system would have flagged — names the entity scope, metric, threshold>
- <Concrete signal 2>
- <Concrete signal 3>

### Conclusion

<One to two sentences in plain English. State the all-clear or the partial-all-clear with the appropriate calibration.>

<details>
<summary>What was examined & methodology</summary>

- **Period:** <date range and granularity>
- **Scope:** <entities and dimensions covered>
- **Analytical agents that ran:** <list with one-line description per agent>
- **Baselines checked:** <list>
- **Statistical methods:** <test names, correction methods, sample sizes>
- **Validator coverage:** <how many findings reviewed, grade distribution>

</details>

### Open data gaps

| Priority | Gap | What would close it |
|---|---|---|
| HIGH | <gap 1> | <instrumentation request> |
| MEDIUM | <gap 2> | <instrumentation request> |
| LOW | <gap 3> | <instrumentation request> |

**Source:** <dataset handle> | run <ISO timestamp>
```

### Why this format works

- **What's stable section first**: executives reading top-to-bottom see the all-clear before any caveats.
- **Structural observations are clearly labeled as no-action**: they don't compete with cards for executive attention.
- **Audit trail in collapsible `<details>`**: visible if someone wants it, invisible by default.
- **Open data gaps as a table**: visually scannable, prioritized, with the "what would close it" column right there.
- **No `═══` separators**: visual hierarchy from markdown headers, not from ASCII art.

## Section-by-section requirements

### PERIOD EXAMINED — date range and granularity
Specific. *"Week of 2026-05-11 through 2026-05-17, weekly granularity"* — not *"the past week."*

### SCOPE — entities and dimensions covered
Names the scope so the recipient knows what *was* in the analysis. *(Example, sales):* *"All accounts across all regions; SKU-level for top-200 products by volume; weekly granularity."* If the scope was narrower than the full domain, say so explicitly so the recipient knows what was not examined.

### WHAT WAS EXAMINED — areas covered
A bulleted list of the analytical areas the pipeline ran. *(Example, proactive monitoring):*

- *Pattern Discoverer scanned for clustering anomalies and structural outliers across accounts.*
- *Time Series Analyzer ran STL decomposition and change-point detection on weekly volume series.*
- *Relationship Analyzer examined correlations between distribution and velocity at the SKU-account level.*
- *Findings Validator independently re-computed all candidate findings.*

The recipient learns what work was done. This is what differentiates *"nothing rose to action"* from *"we didn't look."*

### BASELINES CHECKED — comparisons made
Lists the baseline reference points the analysis compared against. *(Example, sales):*
- *Same period prior year (weeks of 2025-05-12 to 2025-05-18).*
- *Trailing 13-week average.*
- *Peer-account-group median within region.*

This makes the recipient's confidence in the "all clear" calibrated: the data wasn't merely "looked at" — it was compared against specific, defensible reference points.

### KEY OBSERVATIONS — stable performance highlights
Bulleted, 3–6 items. The point is to give the recipient a brief picture of state without manufacturing concern. Each bullet:
- States a metric and its current value.
- Compares to the relevant baseline.
- Notes the direction and magnitude (within-noise / mildly favorable / mildly unfavorable / unchanged).

*(Example, supply chain):*
- *Network-wide fill rate at 96.4%, within 0.3 pts of trailing-13-week average. No DC fell below the 92% concern threshold.*
- *Days-of-supply distribution stable; median 12.4 days, IQR 8.7–18.2 days. No SKU-DC pairs crossed the 30-day surplus threshold.*

If a metric moved meaningfully but the move did not rise to action level (e.g., a 5% drop on a metric where the action threshold is 8%), name it — *"observed but below action threshold"* — so the recipient sees the system noticed it and made a discipline call to not escalate.

### WHAT WOULD HAVE CONSTITUTED A FINDING — calibrate "all clear"
One to three concrete examples of what kind of signal would have triggered an action card *this period*, based on the actual thresholds the pipeline used. *(Example, sales):*

- *An account-level instock drop below 85% sustained for 2+ weeks.*
- *A regional volume decline > 8% vs. prior-year and trailing-baseline triangulation.*
- *A trade-promo lift below 0.7× expected, with margin compression > 2 pts.*

This is the section that earns the recipient's trust. The recipient learns the system was looking for something specific; they can judge whether the threshold is right, but they can no longer assume "all clear" means "didn't look."

### CONCLUSION — explicit, calibrated
One to two sentences. Three patterns depending on the run's nature:

- **Full all-clear:** *"No findings rose to action level this period. All examined areas operated within their stable bands and baselines."*
- **Mixed (some action cards generated, plus stable areas in the same run):** *"3 action cards generated for distribution issues at named accounts. Outside those areas — performance was stable across the network; no other items required attention this period."*
- **All clear with a noted soft signal:** *"No findings rose to action level. One area (Southeast distribution velocity) showed a 4% softening vs. baseline that did not cross the 8% threshold; it will be re-examined on next run."*

The conclusion must match the rest of the summary. Do not declare full all-clear if the body acknowledged a soft signal.

### OPEN DATA GAPS — from tracking-gaps
If any agent surfaced a tracking gap via [tracking-gaps.md](../universal/tracking-gaps.md), aggregate them here. This makes the cumulative instrumentation case visible to the recipient in one place. Brief; one line per gap. Skip the section entirely if there are no gaps to surface.

## Mixed runs — action cards + descriptive summary in the same output

The Communication Agent commonly produces a *combined* output: one or more action cards for areas with findings, followed by a descriptive summary covering stable areas. This pattern is the norm, not the exception. The descriptive summary's `WHAT WAS EXAMINED` and `KEY OBSERVATIONS` sections cover the areas that did *not* produce action cards.

The summary should make explicit the partition: *"This summary covers areas outside the action cards above"* in the header. Recipients should never read a descriptive summary and wonder whether it overlaps with the action cards.

## Anti-patterns

- Padding the summary with marginal observations to make it look longer. A 4-bullet summary is fine. A 14-bullet summary is the system manufacturing volume.
- Burying the "all clear" in vague phrases. *"Performance was within expected ranges"* is weaker than *"Network-wide fill rate at 96.4%, within 0.3 pts of trailing-13-week average."* Specificity beats reassurance.
- Omitting the `WHAT WOULD HAVE CONSTITUTED A FINDING` section. Without it, the recipient cannot calibrate "all clear" against what the system was looking for.
- Promoting a soft signal to "concerning" to give the summary something dramatic. If it didn't rise to action, the language must not pretend it did.
- Apologizing for not having findings. "Sorry there isn't more to report this week" is corrosive — it teaches the recipient that the system *should* find something, which is exactly the opposite of the framing.

## Tie to framing

This skill is the framing made concrete. *"Nothing concerning this period, here is your summary"* is a complete and valid output. The descriptive summary's quality — its specificity, its calibration, its respect for the recipient's attention — is what earns the system the right to be trusted on action-card runs. A recipient who consistently receives well-crafted descriptive summaries learns that when an action card appears, *it has not been manufactured to fill space*.

## Output discipline

The summary is a markdown block intended for direct rendering. The Communication Agent assembles it after any action cards, applies stakeholder-communication adjustments per [stakeholder-communication.md](stakeholder-communication.md), and emits.
