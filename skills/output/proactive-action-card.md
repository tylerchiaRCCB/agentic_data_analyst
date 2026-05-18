# Output Skill: Proactive Action Card

**Loaded by:** Communication Agent.
**Purpose:** Render a validated finding as a recipient-ready action card. The action card is the unit of output for proactive monitoring — one card per finding that the Validator passed forward at grade A, B, or grade C (preliminary).

A good action card is **specific, owned, time-bounded, and counter-metric-aware.** A recipient who reads it should know within 30 seconds: what happened, why it matters, what they should do, by when, and how it will be checked.

## Card structure

Each action card is a markdown block with the following fields in order. Each is required unless explicitly marked optional.

```
═══════════════════════════════════════════════════════════
ACTION CARD #<n>

ALERT: <one-sentence headline finding — what changed, where, by how much>

CONFIDENCE: <A | B | C>
WHY THIS MATTERS: <one to three sentences — the business reason this finding rises to action>
ROOT CAUSE: <one to three sentences — what the Root Cause Investigator established, with causation/correlation language matching the evidence strength>

RECOMMENDED ACTION: <specific, executable — see Close-the-Loop §1>
OWNER: <role, and named individual if domain context provides one>
DUE: <date or relative time bound>
FOLLOW-UP TRIGGER: <specific data threshold for resolution / escalation>

CAVEATS:
- <every severity-high caveat from upstream, verbatim>
- <Validator-required caveats>
- <guardrail trade-off line if applicable>

VISUALIZATION SUGGESTED: <chart type and what it shows, optional>
SOURCE: <dataset reference + run timestamp>
═══════════════════════════════════════════════════════════
```

## Field-by-field requirements

### ALERT — the headline
One sentence. Names the entity, the metric, the magnitude, and the timeframe. Front-loads the numeric finding — recipient reads the number first, the framing after.

- **Good (sales):** *"Account 47 instock for SKU 12345 dropped from 91% to 72% over the past 4 weeks, vs. peer-account median of 89%."*
- **Bad:** *"There may be an issue with Account 47 that warrants investigation."* — vague, no number, doesn't tell the recipient what they're looking at.

### CONFIDENCE — A, B, or C
Taken directly from the Validator's `grade` field. **Grades D and F never render.** The recipient sees the grade alongside the language calibrated to it (see [confidence-language.md](confidence-language.md)).

### WHY THIS MATTERS — business framing
Connects the statistical finding to a business consequence. Why should the recipient care? Quantify when possible.

- **Good (sales):** *"Account 47 is a top-decile distribution point for this SKU; sustained instock below 75% threatens a typical 200-case-per-week revenue stream and risks the broader account relationship."*
- **Bad:** *"This is statistically significant."* — significance is not consequence.

### ROOT CAUSE — what the investigator established
One to three sentences from the Root Cause Investigator's `primary_root_cause` output. Use causation/correlation language matching the evidence strength (see [statistical-rigor.md](../universal/statistical-rigor.md) §5):

- *"established_causal"* → *"caused by," "driven by"*
- *"strong_correlation"* → *"strongly associated with," "coincided with"*
- *"associational"* → *"is associated with"*

If the Root Cause Investigator returned `primary_root_cause: null` (no confident cause survived testing), state that honestly: *"Root cause investigation did not identify a primary driver that survived hypothesis testing. Top candidate explanations are noted in the run log but did not reach grade-A confidence."*

### RECOMMENDED ACTION — specific, executable
Bound by [close-the-loop.md](../universal/close-the-loop.md). Names the action, the contact / target if applicable, the subject. Never *"investigate further,"* *"monitor,"* *"consider."*

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

Cards rendered at grade B or C must explicitly carry the grade in the CONFIDENCE field and use the corresponding language register (see [confidence-language.md](confidence-language.md)). A grade-C card frames the finding as preliminary — *"Initial signal suggests..."* — and explicitly notes what further evidence would raise confidence. The recipient never sees a grade-C card written in grade-A language.

## What does NOT belong on an action card

- Findings the Validator graded D or F. These are filtered upstream of this skill.
- Speculative additions ("if we also look at X, we might find..."). The card is for findings the Validator passed forward, full stop.
- The system's process or methodology details. The recipient cares about the finding, not the pipeline. Methodology lives in the run log.
- Multiple findings in one card. One card per finding; if findings are related, the descriptive summary can group them, but action cards stay atomic.

## Tie to framing

The action card's discipline — specific, owned, time-bounded, counter-metric-aware, confidence-calibrated — is what makes recipient action *possible*. A card that lacks any of these elements wastes recipient attention and erodes trust in the next card. The system is in the business of producing cards the recipient acts on, not cards that look thorough; if a finding cannot produce all the required fields honestly, it belongs in the descriptive summary, not on a card.

## Output discipline

The card is a markdown block intended for direct insertion into the run's final output. The Communication Agent assembles all cards in one render pass, applies any stakeholder adaptations from [stakeholder-communication.md](stakeholder-communication.md), and emits the combined output. The card's text is the final user-facing artifact for this finding — no further transformation.
