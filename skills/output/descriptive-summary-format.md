# Output Skill: Descriptive Summary Format

**Loaded by:** Communication Agent.
**Purpose:** Render the output for runs (or portions of runs) where no findings rose to action level. This output is **a first-class output**, not a fallback. The system says "nothing requiring action this period" with the same craft and respect for recipient attention as it brings to action cards.

If this skill is invoked, the run did its job. The data was examined, baselines were checked, and the analysis concluded — honestly — that nothing required attention. The descriptive summary documents that work so the recipient understands what was looked at and that nothing actionable was found.

**BREVITY RULES:**
- The entire visible summary (excluding `<details>` blocks) must be **under 300 words**.
- "Items approaching thresholds" = **1-3 bullets only**. Each bullet names the metric, current value, threshold, and trend. OMIT this section if nothing is approaching.
- "What would have constituted a finding" = **maximum 2 bullets**. Only the most decision-relevant thresholds.
- "Conclusion" = **1-2 sentences**. State the all-clear.
- **NO "What's stable" section in the visible body.** Stability is the default assumption. Stable metrics belong in the `<details>` audit trail only.
- **NO "Structural observations" section in the visible body.** These are background context for auditors, not decision-relevant for executives. Move them to `<details>`.
- All methodology, stable-area descriptions, structural observations, and statistical detail goes in `<details>` blocks — never in the visible body.
- **COMPRESS, DON'T DISCARD:** The `<details>` audit trail block contains the FULL record: stable metrics checked, structural observations, methodology, baselines, agents that ran. The visible body is the executive layer; `<details>` is the complete analyst record.

**PROBLEM-FIRST RULES (strict):**
- If no problems exist, say so directly in 1-2 sentences and stop.
- If metrics are approaching thresholds but haven't crossed, surface those as "Items approaching thresholds" — this is the only visible section beyond the conclusion when no action cards exist.
- Do not describe normalcy in the visible body. "Network-wide fill rate at 96.4%" is audit information, not a decision.

**PLAIN-LANGUAGE RULES (strict):**
- Write for non-analyst readers.
- No statistical terms in the visible summary body.
- Use business words, short sentences, and action-oriented phrasing.
- If a detail needs analyst interpretation, move it to `<details>`.

## Why this output exists

The strongest demonstration of the system's discipline is its ability to remain quiet when staying quiet is the right answer. A tool that fabricates findings to fill space erodes recipient trust on every run; a tool that produces a brief, useful descriptive summary on quiet weeks earns trust on every run.

This is the spec's *"nothing concerning this week, here is the descriptive summary"* output. Treat it accordingly.

## Format — rendered markdown, NOT a code-fenced block

The descriptive summary is rendered as native markdown — same principle as the action cards. **Do NOT wrap the summary in `` ``` `` code fences.** That breaks visual hierarchy and looks like terminal output.

### Canonical template

```markdown
## Summary — <domain> — <period>

### Conclusion

<One to two sentences in plain English. State the all-clear directly. No throat-clearing.>

### Items approaching thresholds

> *Optional section — OMIT if nothing is trending toward a threshold.*

- **<Metric 1>:** currently at <value>, threshold is <value>, trending <direction> over <timeframe>
- **<Metric 2>:** currently at <value>, threshold is <value>

<details>
<summary>Full audit trail — what was examined</summary>

### What was stable (no action required)
- **<Metric 1>:** <one-line — value, direction, comparison>
- **<Metric 2>:** <one-line>
- *(typically 3–6 bullets)*

### Structural observations
- **<Observation 1>:** <one short paragraph>
- **<Observation 2>:** <one short paragraph>

### Thresholds checked
- <Concrete signal 1 the system would have flagged — names the entity scope, metric, threshold>
- <Concrete signal 2>

### Methodology
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

**Source:** <dataset handle> | run <ISO timestamp>
```

- <Optional: One to three practical follow-ups for teams, even when no action cards were issued.>

### Open data gaps

| Priority | Gap | What would close it |
|---|---|---|
| HIGH | <gap 1> | <instrumentation request> |
| MEDIUM | <gap 2> | <instrumentation request> |
| LOW | <gap 3> | <instrumentation request> |

**Source:** <dataset handle> | run <ISO timestamp>
```

### Why this format works

- **Conclusion first**: executives reading top-to-bottom see the all-clear immediately without scrolling through stable metrics.
- **Items approaching thresholds**: the only visible detail section — surfaces near-misses that may become next week's action cards. This is what prevents the summary from being a pure "nothing to see here."
- **Stable areas and methodology in `<details>`**: visible if someone wants to verify thoroughness, invisible by default. Does not compete with action cards for executive attention.
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

### KEY OBSERVATIONS — stable performance highlights (AUDIT TRAIL ONLY)
These belong in the `<details>` audit trail, NOT in the visible body. Bulleted, 3–6 items. The point is to prove the system examined the data, not to describe the world to an executive. Each bullet:
- States a metric and its current value.
- Compares to the relevant baseline.
- Notes the direction and magnitude (within-noise / mildly favorable / mildly unfavorable / unchanged).

These bullets demonstrate analytical thoroughness to auditors. Executives do not read them.

If a metric moved meaningfully but the move did not rise to action level (e.g., a 5% drop on a metric where the action threshold is 8%), surface it as an **"Items approaching thresholds"** bullet in the visible body — not in the stable-metrics list.

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

## Mixed runs — action cards + summary in the same output

The Communication Agent commonly produces a *combined* output: one or more action cards for areas with findings, followed by a brief summary. The visible summary content in a mixed run is MINIMAL:
- **"Items approaching thresholds"** — only if near-miss metrics exist
- **`<details>` audit trail** — stable areas, structural observations, methodology

Do NOT produce a visible "Weekly Summary" section with "What's stable" bullets when action cards exist in the same output. The action cards ARE the output. The summary's job in a mixed run is to prove thoroughness via the `<details>` block, not to describe the world.

## Anti-patterns

- **Writing a weather report.** Describing stable performance in the visible body wastes executive attention. Stable metrics belong in `<details>` only. The visible body is for problems, near-misses, and the all-clear conclusion.
- **Padding the summary with stable-metric bullets to look thorough.** Thoroughness is demonstrated in the `<details>` audit trail, not by making executives read about things that are fine.
- **Burying the "all clear" after pages of stability description.** Lead with the conclusion. If nothing is wrong, say so immediately.
- Omitting the `WHAT WOULD HAVE CONSTITUTED A FINDING` thresholds from the audit trail. Without them, auditors cannot calibrate what the system was looking for.
- Promoting a soft signal to "concerning" to give the summary something dramatic. If it didn't rise to action, the language must not pretend it did.
- Apologizing for not having findings. "Sorry there isn't more to report this week" is corrosive — it teaches the recipient that the system *should* find something, which is exactly the opposite of the framing.

## Tie to framing

This skill is the framing made concrete. *"Nothing concerning this period, here is your summary"* is a complete and valid output. The descriptive summary's quality — its specificity, its calibration, its respect for the recipient's attention — is what earns the system the right to be trusted on action-card runs. A recipient who consistently receives well-crafted descriptive summaries learns that when an action card appears, *it has not been manufactured to fill space*.

## Output discipline

The summary is a markdown block intended for direct rendering. The Communication Agent assembles it after any action cards, applies stakeholder-communication adjustments per [stakeholder-communication.md](stakeholder-communication.md), and emits.
