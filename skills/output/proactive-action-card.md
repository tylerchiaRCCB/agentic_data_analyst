# Output Skill: Proactive Action Card

**Loaded by:** Communication Agent.
**Purpose:** Render a validated finding as a recipient-ready action card. The action card is the unit of output for proactive monitoring — one card per finding that the Validator passed forward at grade A, B, or grade C (preliminary).

A good action card is **specific, owned, time-bounded, and counter-metric-aware.** A recipient who reads it should know within 30 seconds: what happened, why it matters, what they should do, by when, and how it will be checked.

The card must be **executive-readable** — not analyst-readable. Senior leaders don't read statistical notation; they read business consequence. Statistical methodology belongs in a methodology footer or a `<details>` block, never in the headline or body.

**BREVITY RULES:**
- Each card body (alert through caveats, excluding `<details>`) must be **under 400 words**.
- "Why this matters" = **2-3 sentences max**. One quantified business consequence.
- "Root cause" = **2-3 sentences max**. State what's known, what's not.
- "Recommended action" = **2-3 sentences max**. Specific and executable.
- Caveats = **maximum 3 bullets**. Consolidate related caveats into one.
- If you can't say it in 3 sentences, the finding needs tightening, not more words.
- **COMPRESS, DON'T DISCARD:** Any caveats, supporting evidence, secondary analysis, or extended context beyond these limits goes into the card's `<details>` Methodology block. Nothing is lost — it moves from the executive layer to the analyst layer.

**PLAIN-LANGUAGE RULES (strict):**
- Write for a non-analyst business reader.
- Do not use test names, statistical notation, or model terms in the card body.
- Prefer common words: "moved together" over "correlated", "clear change" over "structural break".
- Keep each sentence short and direct. Prefer one idea per sentence.
- Start recommended action with a verb ("Call", "Pause", "Launch", "Audit", "Confirm").

## Card structure — rendered markdown, NOT a code-fenced block

Each action card is rendered as native markdown (headers, bold, tables, callouts) so that:
- Inline Mermaid charts render inline
- GitHub / Obsidian / any markdown viewer applies typography
- The reader's eye can scan visually instead of reading every word

**Do NOT wrap action cards in `` ``` `` code fences.** That breaks Mermaid rendering, removes visual hierarchy, and makes the output look like terminal logs.

### Canonical template (use this exactly)

```markdown
### Card N — <one-line plain-English headline>

> **<one-sentence ALERT in plain language, with the biggest number bolded>**

**Why this matters.** <One short paragraph, 2–3 sentences, plain English. Translate the analytical finding into business consequence. Quantify in business units (cases, dollars, %, accounts affected) — never raw statistical units.>

**Root cause.** <One short paragraph, 2–3 sentences. Use causation/correlation language calibrated to the investigator's `causation_vs_correlation` flag. Plain English. No p-values, no test names, no statistical notation here — those live in the Methodology footer.>

**Recommended action.** <One short paragraph. Specific, executable, time-bounded. No "monitor" / "investigate" / "consider" alone.>

**Do this now.** <One sentence that a manager can forward as-is to the owner.>

| | |
|---|---|
| **Owner** | <Role, and named individual if domain context provides one> |
| **Due** | <Specific date or "within N business days"> |
| **Follow-up trigger** | <Specific data threshold for resolution / escalation> |

> ⚠️ **Caveats:** <Every severity-high caveat from upstream, comma-separated or as a short bulleted list. Plain English.>

<Inline Mermaid block here if the chart type is one Mermaid supports — see visualization-recommendations.md. Otherwise emit a one-line "Suggested chart" prose recommendation.>

<details>
<summary>Methodology & lineage</summary>

- **Source:** <dataset handle> | run <ISO timestamp>
- **Tests & statistics:** <test names, p-values, CIs, effect sizes — put the full statistical detail here>
- **Validator layer results:** Layer 1 <pass/partial/fail> | Layer 2 <match/mismatch/unable> | Layer 3 <pass/trade_off/n/a> | Layer 4 <plausible/implausible/n/a>
- **Lineage refs:** <Statistic IDs from the upstream artifact>

</details>
```

### What this template fixes vs the older 1980s-terminal style

| Old (broken) | New (this template) |
|---|---|
| Wrapped in `` ``` `` code fence | Native markdown — renders typography + Mermaid |
| `═══` separators + plain-text labels | Markdown headers + bold + table + callout |
| All fields equally prominent | Headline + Why + Root + Action stand out; ownership in a small table; caveats in a callout; methodology collapsed |
| Statistical notation in body | Statistical detail in `<details>` footer only |
| Wall of text | Scannable in 30 seconds — visual hierarchy guides the eye |

## Field-by-field requirements

### ALERT — the headline
One sentence in a markdown blockquote (`> **<text>**`). Names the entity, the metric, the business consequence, and the timeframe. The biggest number is **bolded** so the eye finds it first.

- **Good (sales):** *"SKU 12345 has been out of stock 1 in 3 weeks at Account 47 for the past month — **28 points below the rest of the network**."*
- **Acceptable but more technical:** *"Account 47 instock for SKU 12345 dropped from 91% to 72% over the past 4 weeks, vs. peer-account median of 89%."*
- **Bad:** *"There may be an issue with Account 47 that warrants investigation."* — vague, no number.
- **Bad:** *"A003/SKU003 instock_rate of 0.6625 vs. peer median 0.9275 (modified z = −24.46, MW U=0, p=0.0008)."* — over-technical for a headline; the test names and notation belong in the Methodology footer.

Plain-language check before finalize:
- Would a district manager understand this without analyst support?
- Could the Owner forward the "Do this now" line directly to a team lead?
- If not, rewrite.

### CONFIDENCE HANDLING — internal only
Taken from the Validator's `grade` field to calibrate wording and action strength. **Grades D and F never render.** Do not print an explicit `Confidence:` line in recipient-facing markdown.

### WHY THIS MATTERS — business framing in plain English
Connects the analytical finding to a business consequence. Why should the recipient care? Quantify in **business units** (cases, dollars, accounts affected, % of business at risk) — **never raw statistical units**.

- **Good (sales):** *"Account 47 is a top-decile distribution point for this SKU. Sustained instock below 75% threatens roughly 200 cases/week of revenue and puts the broader account relationship at risk."*
- **Bad:** *"This is statistically significant."* — significance is not consequence.
- **Bad:** *"The instock gap is non-overlapping; the floor for all other entities is 0.881 vs. A003/SKU003 ceiling of 0.739."* — over-technical. Translate: *"This product is out of stock more than 1 in 3 weeks. No other product in the network is even close to that level."*

**Statistical jargon — p-values, ρ, test names, modified-z scores, CI bounds — does NOT appear in this field.** Push all of that into the Methodology footer at the bottom of the card.

### ROOT CAUSE — what the investigator established
One to three sentences from the Root Cause Investigator's `primary_root_cause` output. Use causation/correlation language matching the evidence strength (see [statistical-rigor.md](../universal/statistical-rigor.md) §5):

- *"established_causal"* → *"caused by," "driven by"*
- *"strong_correlation"* → *"strongly associated with," "coincided with"*
- *"associational"* → *"is associated with"*

If the Root Cause Investigator returned `primary_root_cause: null` (no confident cause survived testing), state that honestly: *"Root cause investigation did not identify a primary driver that survived hypothesis testing. Top candidate explanations are noted in the run log but did not reach grade-A confidence."*

### RECOMMENDED ACTION — specific, executable
Bound by [close-the-loop.md](../universal/close-the-loop.md). Names the action, the contact / target if applicable, the subject. Never *"investigate further,"* *"monitor,"* *"consider."*

Required pattern for readability:
- Sentence 1: exact action and owner.
- Sentence 2: when it must be done.
- Sentence 3: what result means success/failure.

### OWNER — role + named individual where available
A role (account manager, supply planner, plant manager, trade finance partner) at minimum. The domain context document's stakeholder map may provide a named individual; if so, include them. If the system does not know the named owner, surface the gap: *"Owner role: account manager; specific assignee to be filled by district manager."*

### DUE — concrete deadline
A date or a clearly-bounded relative time. *"Within 5 business days"* is fine; *"soon"* is not.

### FOLLOW-UP TRIGGER — observable resolution condition
Specific enough that the next run can evaluate it. Two patterns:

- **Resolution trigger:** *"Mark resolved if next week's run shows Account 47 instock ≥ 90% for SKU 12345."*
- **Escalation trigger:** *"Escalate to district manager if next week's run still shows instock below 85%."*

Most cards have one of each.

### CAVEATS — every severity-high caveat surfaces
Every `severity: "high"` `Caveat` from the upstream artifacts must appear here. Three sources:
- Profiler caveats (data quality issues, sample-size limits, mandatory caveats).
- Investigator caveats (analytical limitations, rejected hypotheses worth noting).
- Validator-required caveats (per the Validator's `required_caveats` for this finding).
- Guardrail trade-off (if the guardrail check returned `trade_off_present` — must appear as a card-level statement, not buried).

Caveats are not optional. Missing a high-severity caveat is a render bug.

### VISUALIZATION SUGGESTED — optional
A short note specifying the chart type and what it would show. See [visualization-recommendations.md](visualization-recommendations.md). The tool does not render charts in MVP; the recipient or downstream BI can build it.

### SOURCE — dataset reference + timestamp
`Source: <dataset handle> | run <ISO timestamp>`. Lineage detail is in `lineage.json` for the run, not in the card.

## When the Validator's output forces a downgrade

Cards rendered at grade B or C must use the corresponding language register (see [confidence-language.md](confidence-language.md)). A grade-C card frames the finding as preliminary — *"Initial signal suggests..."* — and explicitly notes what further evidence would raise confidence. The recipient should not see an explicit letter grade label.

## What does NOT belong on an action card

- **Findings the Validator graded D or F.** These are filtered upstream of this skill.
- **Findings where the recommended action would be "no immediate action," "monitor," "be aware," or similar.** A card with no action is not an action card; it's a note. Those belong in the descriptive summary's "Structural observations" subsection, NOT as a card. A real action card must have a *specific, executable, time-bounded* action — see [close-the-loop.md](../universal/close-the-loop.md). If you can't fill the Recommended Action / Owner / Due / Follow-up Trigger fields with substance, the finding is not card-worthy. **Promote sparingly: an exec scanning 4 cards gives equal weight to all 4. Three cards that are real actions + one structural awareness note in the summary is far stronger than four cards of varying actionability.**
- **Speculative additions** ("if we also look at X, we might find..."). The card is for findings the Validator passed forward, full stop.
- **The system's process or methodology details** in the body. Statistical methodology lives in the `<details>` Methodology footer at the bottom of the card. The body uses plain business language.
- **Multiple findings in one card.** One card per finding; if findings are related, the descriptive summary can group them, but action cards stay atomic.

## Card-promotion criteria — explicit gates

Before writing a card, verify ALL of these are true:

1. The finding has Validator grade A, B, or C *and* survives the Validator's filtering.
2. There is a **specific, named action** the recipient can take this week.
3. There is a **specific owner role** (and ideally a named individual from the domain context).
4. There is a **specific due date or time bound** — not "soon."
5. There is a **specific follow-up trigger** the next run can check.

If any of those is "no" or "n/a," the finding is **NOT** a card. It belongs in the descriptive summary as a structural observation or, if grade C, in a "preliminary signals" subsection.

## Tie to framing

The action card's discipline — specific, owned, time-bounded, counter-metric-aware, confidence-calibrated — is what makes recipient action *possible*. A card that lacks any of these elements wastes recipient attention and erodes trust in the next card. The system is in the business of producing cards the recipient acts on, not cards that look thorough; if a finding cannot produce all the required fields honestly, it belongs in the descriptive summary, not on a card.

## Output discipline

The card is a markdown block intended for direct insertion into the run's final output. The Communication Agent assembles all cards in one render pass, applies any stakeholder adaptations from [stakeholder-communication.md](stakeholder-communication.md), and emits the combined output. The card's text is the final user-facing artifact for this finding — no further transformation.
