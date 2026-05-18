# Output Skill: Stakeholder Communication

**Loaded by:** Communication Agent.
**Purpose:** Adapt the depth, framing, and language of recipient-facing output to the recipient's role. Same finding, different framing depending on whether the reader is an account-level individual contributor, a regional manager, a functional director, or an executive.

The system doesn't render multiple parallel versions of every output. It renders one version, calibrated to the recipient role specified in the run's delivery configuration or — in proactive monitoring with multiple recipients per finding — calibrated to each recipient separately at render time.

## The role tiers

Each finding's action card or summary may be rendered in one of four tiers, depending on the recipient. The tiers come from the domain context document's stakeholder map.

| Tier | Recipient examples | Depth | Framing | Time-to-read target |
|---|---|---|---|---|
| **IC (individual contributor)** | Account manager, supply planner, plant engineer, brand analyst | Maximum operational detail — specific entities, specific SKUs, specific dates, specific contacts | Concrete next action they can take | 60–90 seconds |
| **Manager** | District manager, regional sales manager, plant manager, trade marketing manager | Detail about cards in their span; aggregated detail across their team's cards | Where to direct attention, which ICs need support, what to escalate | 2–3 minutes |
| **Director** | Category director, supply chain director, operations director, trade marketing director | Patterns across managers; cross-functional implications | Where the function as a whole is performing, which initiatives the data supports or challenges | 3–5 minutes |
| **Executive** | VP / SVP, CCO, COO, CFO | Top-of-tree only — most-material findings + the descriptive summary at the level of the whole function | Strategic implications, investment / divestment signals, accountability touchpoints | 60 seconds |

These are tiers, not strict role buckets. A specific recipient's tier comes from the domain context's stakeholder map. When the same finding goes to multiple recipients (e.g., one to the account manager and one to the regional director), the system renders the finding twice with different tier calibrations.

## What changes by tier

### Headline / ALERT line
- **IC:** *"Account 47 instock for SKU 12345 dropped from 91% to 72% over the past 4 weeks vs. peer median of 89%."*
- **Manager:** *"3 accounts in the Southeast region have instock issues; Account 47 is the largest by revenue at risk (~$200K/month). Full list and detail in attached cards."*
- **Director:** *"Southeast instock performance has degraded materially over the past month, driven by delivery-window changes at 3 named accounts. Likely operational; not a structural product or trade-spend issue."*
- **Executive:** *"Southeast: $600K/month at risk from operational instock issues at 3 accounts. Mitigation in flight; no immediate strategic implication."*

### Recommended action
- **IC:** A specific contact, subject, and deadline ([close-the-loop.md](../universal/close-the-loop.md)).
- **Manager:** Which ICs are working on which cards; what they need from the manager; escalation thresholds.
- **Director:** Whether the issue is a one-off or a pattern worth a process change; what cross-functional partners (supply chain, ops) might need to be looped in.
- **Executive:** Whether anything requires executive sponsorship or external communication.

### Caveats and methodology
- **IC:** All high-severity caveats verbatim; methodology in source line only.
- **Manager:** All high-severity caveats; brief methodology context if it affects how to interpret the urgency.
- **Director:** Caveats summarized to the ones that affect the directional read; methodology footnote.
- **Executive:** Caveats only if they change the executive-level read (e.g., "this is a 2-week observation, may revert"). Methodology in an appendix or skipped entirely.

### Confidence language
The grade itself doesn't change by tier — a grade-B finding is grade-B regardless of recipient. But the **framing of the grade** can adapt:
- **IC sees:** *"Confidence: B. The pattern is robust; one caveat noted below — partial-data refresh in 2 of the 4 weeks may understate the magnitude."*
- **Executive sees:** *"Initial signal; magnitude estimate has a 4–8 pt margin of uncertainty."* — same information, executive-tier register.

## What stays the same across tiers

- **The underlying finding.** The headline metric, the entities involved, the magnitude, the direction. These are facts, not framing.
- **The grade.** Grade is not bumped up for executives or down for ICs.
- **The framing discipline.** A grade-C finding is preliminary at every tier; a grade-A finding is direct at every tier.
- **The honest acknowledgment of caveats.** The set of caveats surfaced may compress at higher tiers, but the substantive ones (data quality issues, guardrail trade-offs, methodological limits that affect the directional read) appear at every tier.
- **The "nothing rose to action" output.** A descriptive summary at the executive tier is shorter than at the IC tier, but it still exists, and it still earns the same trust by its specificity.

## Required practices

1. **Look up the recipient's tier from the domain context's stakeholder map.** If the map doesn't specify a tier for the recipient, default to IC and flag the gap to the run log.
2. **Render once per tier, not once per finding.** When a finding has multiple recipients across tiers, the Communication Agent renders the card N times with N tier calibrations.
3. **Aggregate where the tier expects aggregation.** A manager's summary should not be the IC card with the contact line removed; it should be a manager-tier render that reasons across their span.
4. **Never invent detail at higher tiers.** Executive-level framings should *compress* what's known, not *speculate* beyond it. If the IC card says *"likely driven by delivery-window changes,"* the executive card doesn't escalate that to *"clear operational failure"* — it preserves the original calibration.

## When the stakeholder map doesn't specify

Default to IC tier — the most operationally detailed — and flag the gap in the run log so the domain context can be updated. The IC tier is the safest default because it carries the most detail; readers above that tier can skim, but a director receiving only an executive-tier card would have to ask follow-up questions.

## Anti-patterns

- **Generic "executive summaries" written by the Communication Agent without recipient tier specified.** Better: send the IC-tier card to the IC and let aggregation happen explicitly through a manager-tier card.
- **Bumping the grade up for higher-tier readers.** A grade-C signal does not become a grade-A finding because an executive is reading. The grade reflects evidence strength, not audience.
- **Stripping all caveats for executives because "they don't want detail."** The substantive caveats — the ones that affect direction — remain. The methodology caveats can compress.
- **Different findings at different tiers.** All tiers see the same underlying claim. Only the framing changes.
- **One-size-fits-all rendering.** A card written for "everyone" is written for no one and reads as such.

## Tie to framing

Stakeholder calibration is how the system respects each recipient's attention without changing the underlying analytical claim. The discipline — same finding, same grade, same caveats; tier-appropriate framing — is what allows the same analytical engine to serve an IC and an executive without either feeling miscalibrated.

## Output discipline

This skill is loaded with every Communication Agent call. The agent reads the recipient's tier (from delivery config or stakeholder map) before rendering, and applies tier-appropriate compression / expansion as it generates each section of the card or summary. The skill governs *register and depth*; it does not govern grade, caveats, or content — those are the responsibility of upstream skills and the Validator.
