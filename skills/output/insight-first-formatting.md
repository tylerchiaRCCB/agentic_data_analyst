# Output Skill: Insight-First Formatting

**Loaded by:** Communication Agent.
**Purpose:** Structure recipient-facing output so the most important information appears first. The recipient — typically a busy stakeholder — should be able to read the first 30 seconds of any card or summary and walk away with the most important point, even if they read no further.

This skill is the pyramid principle applied to analytical output: lead with the conclusion, support with evidence, end with detail and methodology. The opposite — building from data to interpretation to conclusion — works in academic writing and fails in operational communication.

## Report-level Executive Summary — required at the top of any output with 2+ action cards

Before any cards or descriptive summary, the rendered output MUST begin with an Executive Summary section. Format:

```markdown
## Executive Summary
- **<Card 1 in one line — entity, metric, business consequence>**
- **<Card 2 in one line>**
- Network performance otherwise <stable / mixed / soft>.
```

Rules:
- Maximum 5 bullets total. If more than 4 cards exist, group the lower-grade ones ("3 grade-C structural observations — see below").
- Each bullet is **one line**. If a card needs more than one line to summarize, the card itself is too dense — tighten the card's headline first.
- Do not append grade letters in parentheses.
- The third bullet (or last bullet, if only 2 cards) summarizes the descriptive-summary state of the rest of the network in 5 words or fewer.
- Executive Summary is for executives who will read **only this section**. Make it count.

A senior leader should be able to read the Executive Summary, decide whether to read further, and route the relevant cards to direct reports — all in under 20 seconds.

## The pyramid for action cards

The action card structure (see [proactive-action-card.md](proactive-action-card.md)) already enforces this order:

1. **ALERT** — the headline conclusion in one sentence, with the number out front.
2. **WHY THIS MATTERS** — business consequence.
3. **ROOT CAUSE** — what the investigator established.
4. **RECOMMENDED ACTION + OWNER + DUE + FOLLOW-UP** — what to do.
5. **CAVEATS** — limitations.
6. **VISUALIZATION + SOURCE** — supporting detail.

The recipient who reads only field 1 has the finding. The recipient who reads 1–4 has enough to act. The recipient who reads 1–6 has the full picture. This is the operating model.

## The pyramid for descriptive summaries

The descriptive summary (see [descriptive-summary-format.md](descriptive-summary-format.md)) follows a parallel pattern:

1. **CONCLUSION first in the recipient's mental model**, even though it's near the bottom of the markdown layout — the section headers ("PERIOD EXAMINED", "WHAT WAS EXAMINED", "KEY OBSERVATIONS") let the eye scan and the CONCLUSION sentence delivers the headline.
2. **KEY OBSERVATIONS** before methodology — recipient sees the state of the world before learning how the system arrived at it.
3. **WHAT WOULD HAVE CONSTITUTED A FINDING** at the end — calibration detail for the recipient who wants to understand the threshold.

## Required practices when rendering

1. **Lead every recipient-facing block with the conclusion, not the journey.** A finding's headline is the conclusion. A summary's conclusion sentence is the conclusion. Methodology, caveats, and lineage are support — they come after.

2. **Front-load numbers.** *"Volume dropped 28% vs. prior 12-week baseline"* beats *"After examining the data, we found a substantial decline."* The number is the headline.

3. **One sentence per idea, in the headline.** If the headline needs a semicolon or a parenthetical to make the point, it has two ideas. Split or simplify.

4. **Use scannable structure — short paragraphs, bullets, bolded keywords.** Recipients skim before they read. The layout should reward skimming with the most important information.

5. **Apply the 30-second test.** Read the top of each card/summary. In 30 seconds, can the recipient state the finding back? If not, the structure has buried the headline.

6. **No throat-clearing.** Cut openings like *"This analysis examines..."* or *"It is important to note that..."*. The first words of a card or summary should carry information.

## What insight-first does NOT mean

- **It does not mean omitting caveats.** Caveats are part of the finding, not optional context. They have their own section near the bottom of the card so they don't bury the headline, but they appear in every card that has high-severity caveats.
- **It does not mean dropping confidence calibration.** A grade-B finding is stated with the appropriate hedge in the headline itself (see [confidence-language.md](confidence-language.md)) — *"Initial signal suggests..."* rather than *"X is happening"* — but it still leads with the most important thing.
- **It does not mean simplifying methodology away.** Lineage and methodology live in the SOURCE field and the run's `lineage.json`. They are not omitted; they are placed where they don't compete with the headline for attention.

## Anti-patterns

- **Building up to the finding.** *"After running clustering analysis followed by change-point detection followed by hypothesis testing..."* — the recipient stopped reading. The finding belongs first.
- **Headlines without numbers.** *"There has been a decline in volume in the Southeast."* — vague. With numbers it becomes *"Southeast weekly volume dropped 12% over the past 4 weeks vs. trailing-13-week baseline."*
- **Headlines that are questions.** *"Should we be concerned about Account 47?"* — the system already determined whether to be concerned by issuing the card. The headline states the determination.
- **Multi-finding headlines.** *"Several accounts showed unusual patterns, including issues with delivery, fill rate, and trade promotion."* — three findings cobbled together. Each gets its own card.
- **Throat-clearing prefixes.** *"It is worth noting that..."*, *"Our analysis suggests..."*, *"After careful consideration..."* — cut all of these. The card already exists because the analysis was done.

## Tie to framing

Insight-first formatting respects the recipient's time. Recipients are busy; the system's job is to deliver useful information in proportion to the time it asks of them. A well-formatted card or summary that the recipient reads in 30 seconds and acts on is the product. A meandering card the recipient skims and ignores wastes the run's compute and the recipient's attention both.

## Output discipline

This skill governs *layout and prioritization* of content the Communication Agent has already determined to render. It does not change what content is rendered — that's determined by the Validator's outputs and the relevant output-format skill (action card, descriptive summary). This skill is loaded with every Communication Agent call to ensure the rendered markdown follows the pyramid pattern across all output modes.
