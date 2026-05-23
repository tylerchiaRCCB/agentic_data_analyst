# Analytical Skill: Cross-Run Synthesis

**Loaded by:** Synthesizer Agent.
**Purpose:** Identify and rigorously calibrate connections between findings from independent per-function pipeline runs. Cross-functional storytelling is uniquely tempting and uniquely error-prone; this skill defines the methodology that keeps the synthesis layer disciplined.

## The synthesis primitive

A **candidate connection** is two or more validated findings, drawn from DIFFERENT source runs, that share:

1. **Entity overlap** — the same SKU, account, region, plant, customer segment, or other business entity dimension. Not "the company" or "the quarter." Specific.
2. **Time overlap** — overlapping windows. *"Sales gap in week 18-22"* and *"Supply gap in week 17-23"* overlap. *"Sales gap in Q1"* and *"Supply gap in Q3"* do not.
3. **Coherent business mechanism** — a plain-English explanation of why one finding plausibly relates to the other. The mechanism doesn't have to be proven causal — it has to be plausible.

A pair of findings that satisfies all three is a candidate. A pair that misses any one is not a connection; mention it as a non-connection if relevant.

## The synthesis grading rules

A cross-functional connection's grade is at most the WEAKEST of its constituent source findings' grades.

| Source A | Source B | Connection's ceiling |
|---|---|---|
| Grade A | Grade A | Grade A (rarely reached; requires causation evidence) |
| Grade A | Grade B | Grade B |
| Grade B | Grade B | Grade B |
| Grade A | Grade C | Grade C (preliminary) |
| Grade B | Grade C | Grade C |
| Grade C | Grade C | NOT a connection — too weak to synthesize on |

**Additionally:** the connection is downgraded one grade if:
- Domain context is missing for any source function (mechanism plausibility cannot be evaluated)
- The confounding analysis cannot rule out an obvious third variable
- The triangulation evidence is weak (the pattern is observed at one entity only)

**Additionally:** the connection is downgraded TWO grades (or rejected entirely) if:
- The two findings share entity and time but the mechanism is implausible or contrived
- The mechanism requires a directional claim that the source findings don't support

## Confounding is the primary risk

Cross-functional connections are uniquely exposed to confounding because the same upstream business event affects multiple functions simultaneously. Common cross-functional confounders:

- **Regional category decline** — both sales and supply slip in a category, but the decline is the cause, not the connection. The sales finding is real, the supply finding is real, but they're parallel effects of a category shift, not connected.
- **Competitor activity wave** — competitor promo lifts their share; your sales drop AND your distribution drops. Two real findings; one external cause.
- **Buyer transition at a key account** — execution falls across functions because of a personnel change, not because of any functional issue.
- **Promotional calendar** — heavy promo periods stress multiple functions simultaneously. Co-occurrence is expected; not connection-evidence.
- **Holiday / seasonal pattern** — both functions show abnormal patterns; the season is the explanation.

Per [confounding-analysis.md](confounding-analysis.md), name candidate confounders explicitly. The synthesis output must include a `confounders_considered` section per connection naming what was checked and what couldn't be ruled out. **No connection ships without this section.**

## Triangulation across entities

A connection that holds at multiple entities (multiple SKUs, multiple accounts, multiple plants showing the same pattern) is much stronger evidence than a one-off coincidence. Per [triangulation.md](../universal/triangulation.md):

- **Single entity, single observation:** maximum grade C — call it preliminary signal.
- **Single entity, multiple observations over time:** maximum grade B.
- **Multiple entities, consistent direction:** grade A is justifiable IF confounding ruled out + mechanism clear.

State the triangulation evidence explicitly. *"This supply-tightness ↔ sales-execution pattern was observed for SKU-7, SKU-12, and SKU-19 in the same period."*

## Non-connections: the disciplined null

One of the synthesis layer's highest-value outputs is the **disciplined non-connection**. When a per-function finding exists in one source run but the obvious cross-functional connection does NOT appear, surface that explicitly:

> *"Sales execution gap on SKU-7 in NE (grade A from sales run). Supply showed NO constraint on SKU-7 in NE in the same period. The sales gap is not supply-driven; investigate within sales (trade promo timing, field execution, account-buyer relationship)."*

This serves two purposes:
1. Prevents downstream stakeholders from assuming connections that aren't there (the "everything is connected to everything" failure mode).
2. Helps focus the next analytical cycle — the per-function root cause investigator can be invoked with the elimination of cross-functional causes already documented.

Aim for non-connections to constitute a meaningful portion of the synthesis output — typically 30-50% of the report when source runs are well-formed. If a synthesis report is 100% connections, the synthesizer is probably manufacturing them.

## The full synthesis workflow

1. **Inventory** all grade-A/B findings across source runs. List them with (run_id, finding_id, claim, entity, time window, grade, key caveats).

2. **Generate candidate connections.** Pair findings across runs that meet the entity + time + mechanism criteria. For each:
   - Name the source findings
   - State the mechanism in plain English
   - Define the entity overlap precisely
   - Define the time overlap precisely

3. **Apply confounding analysis** per [confounding-analysis.md](confounding-analysis.md). For each candidate:
   - Name the candidate confounders (use the common-cross-functional list above + domain-specific)
   - State what evidence is available to rule them out
   - State what cannot be ruled out (almost always something)

4. **Apply triangulation check.** Is the pattern observable across multiple entities? Multiple time windows?

5. **Grade the connection** per the table above; apply downgrades as appropriate.

6. **Inventory non-connections.** For each per-function finding, ask: where would the obvious cross-functional connection appear? Did it? If not, surface as a non-connection.

7. **Set causation language** per [confidence-language.md](../output/confidence-language.md). Default to `associational` for cross-functional connections; `strong_correlation` requires high-confidence mechanism + ruled-out confounders + triangulation; `established_causal` requires quasi-experimental evidence which the MVP does not produce.

8. **Carry forward every high-severity caveat** from every source finding into the connection. Caveats COMPOUND across the synthesis boundary; they do not get filtered.

9. **Render the synthesis output.** Action cards for grade-A/B connections that warrant action; descriptive summary for the rest. Always include a "non-connections" section.

## Anti-patterns

- **Inventing findings to fill the synthesis space.** If no connections rise to grade-B or above, the synthesis report is short and includes the explicit non-connections. Padding is the worst-case error class — manufactured cross-functional insights are uniquely damaging to recipient trust.
- **Promoting connection grade above the weakest constituent.** Inviolable rule.
- **Skipping the confounding analysis because "the connection is obvious."** Obvious-looking connections are the most exposed to confounding. Test, don't assume.
- **Connecting on flimsy entity overlap.** "Both findings about the company in this quarter" is not a connection.
- **Storytelling beyond the math.** The connection's narrative must NOT exceed the evidence. *"Sales is failing because procurement is failing"* sounds compelling but if neither source finding established procurement causality, the synthesis cannot either.
- **Dropping non-connections from the output to "make the report look stronger."** Non-connections ARE the report's strength.
- **Failing to surface domain-context gaps from any source run.** If any source ran without domain context, the synthesis carries that limitation.

## Tie to framing

Cross-functional synthesis is the framework's strongest differentiator vs. competing analytical AI tools — but only if it remains disciplined. A synthesis layer that manufactures connections is worse than no synthesis layer at all. The recipient learns over time what synthesis grade-A means, what grade-B means, what a non-connection means. That calibration is the durable trust the product is building. Every output that abuses the synthesis vocabulary — promoting weak findings to confident connections — sets the trust back across every per-function run too, because the same system produced both.
