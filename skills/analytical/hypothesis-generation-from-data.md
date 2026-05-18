# Analytical Skill: Hypothesis Generation from Data

**Loaded by:** Question Framer (for generic scheduled prompts), Pattern Discoverer (after pattern detection).
**Purpose:** Convert observed structure in the data into a small set of testable hypotheses that the rest of the pipeline can investigate. This is how the proactive monitoring pipeline starts: with no specific user question, the system must look at the data and ask *"what is worth asking about?"* — but ask it in a form that can be tested, not in a form that becomes a self-fulfilling search.

The cleanest separation in any analytical pipeline is between *generating* hypotheses (this skill) and *testing* them ([hypothesis-testing.md](hypothesis-testing.md)). Each is done well only when the other is kept distinct.

## When this skill triggers

- The Question Framer is composing a pipeline for a **scheduled prompt** *(Example, the MVP demo prompt: "weekly anomaly scan for CPG distribution data"; in other functional domains: "weekly supply-chain fill-rate anomaly scan"; "monthly trade-spend efficiency review"; "weekly operations OEE-deviation scan")* with no user-specified focus. It must produce candidate hypotheses for the analytical pipeline to investigate.
- The Pattern Discoverer has detected structure (clusters, outliers, dimensionality findings) and needs to convert observations into testable claims for downstream investigation.
- A descriptive observation in any analytical agent suggests a follow-up question worth surfacing as a hypothesis.

## What a good hypothesis looks like

A good hypothesis from data is:

1. **Testable.** It states a specific relationship that can be evaluated with the available data (or, if not, names the data that would be required — see [tracking-gaps.md](../universal/tracking-gaps.md)).
2. **Falsifiable.** It can be wrong. A hypothesis that no possible data could refute is not a hypothesis.
3. **Concrete.** It names variables, populations, and time windows. "Account 47 had a volume change in the past 4 weeks" is concrete; "Something might be going on with accounts" is not.
4. **Prior-aware.** It carries a stated prior strength — weak / moderate / strong — based on how surprising or how-domain-supported the candidate is. A hypothesis with a weak prior on data that just happens to be unusual today is much weaker than a hypothesis on a known mechanism.
5. **Action-implicating, eventually.** A hypothesis that, if confirmed, would change no decision is academic. The Opportunity Identifier downstream needs hypotheses whose answers could plausibly inform an intervention.

## Procedure

1. **Survey the surfaced observations** from upstream (Profiler quality flags, Pattern Discoverer clusters/outliers, Time Series Analyzer change points, distribution anomalies).

2. **For each observation, ask the four W-questions**:
   - *What* specifically changed or differs?
   - *Where* — which entities, segments, periods?
   - *When* did it begin, and is the timing meaningful?
   - *Why* — what plausible mechanisms could produce this? Consult the domain context's investigation-hypothesis library if available.

3. **Convert the answers into hypotheses** with this template:
   > *"<Outcome> in <population> over <time window> <differs / changed / relates to> <comparison or driver>, **because** <plausible mechanism from domain context>, **and would be confirmed by** <specific testable evidence>, **and refuted by** <specific contrary evidence>."*

4. **Rank by prior strength.** Domain-grounded hypotheses (those that map to known mechanisms in the domain context) have stronger priors than novel-pattern-only hypotheses. The pipeline should test the strongest priors first, both because they are most likely to yield findings and because they consume least pipeline budget per investigated hypothesis.

5. **Cap the count.** A proactive pipeline that generates 30 hypotheses produces a noisy investigation pass. Default cap: **5–8 hypotheses per run** (configurable). The Question Framer's `pipeline_composition` should not commit to investigating more than the budget supports. Hypotheses beyond the cap go into a "for future runs" list rather than this run's pipeline.

## Avoiding self-fulfilling search

The mode of failure this skill must defend against: the system spots noise, calls it a hypothesis, finds (correlated) noise that "supports" it, and emits a confident finding from a circular search.

Defenses:

- **Hypotheses are stated before testing**, not constructed to fit the test that already ran.
- **Multiple-comparison correction applies across all hypotheses generated** in a run; the testing agents apply this (see [statistical-rigor.md](../universal/statistical-rigor.md) §4).
- **Hypotheses are graded by prior strength.** Weak-prior hypotheses that produce "significant" findings at low effect size after correction are downgraded by the Findings Validator.
- **The "no hypotheses worth pursuing" output is valid.** If the upstream agents find no patterns worth converting to hypotheses, the pipeline proceeds to the Communication Agent with a descriptive summary. This is the framing's "nothing concerning this period" output expressed at the hypothesis-generation layer. See [analysis-design-spec.md](../universal/analysis-design-spec.md) §4.

## Required output

The agent emits hypotheses as `Hypothesis` objects (see [artifact-schemas.md](../../orchestration/artifact-schemas.md) §3.3):

```ts
{ id, statement, prior_strength, testable_via, rationale }
```

Where:
- `statement` follows the template in step 3.
- `testable_via` names the skill or technique the testing agent should use (e.g., `"group-comparison"`, `"change-point-detection + simpsons-paradox-check"`).
- `rationale` is a one- to two-sentence explanation of why this is worth testing — the prior-strength justification.

## Anti-patterns

- Generating hypotheses by re-stating observations. *"Volume in region A is down"* is an observation, not a hypothesis. The hypothesis is *"volume in region A is down because of delivery-frequency changes at the largest accounts, evidenced by..."*
- Generating many hypotheses to look thorough. A focused set of 5 strong-prior hypotheses produces better findings than 20 mixed ones.
- Generating only hypotheses that align with a preferred narrative. The set should include hypotheses that, if confirmed, would *contradict* expected patterns — checking "are we wrong about Y" is as valuable as checking "is X true."
- Generating hypotheses with no falsifiable form. *"Performance might be impacted by factors"* is unfalsifiable and not a hypothesis.
- Generating a hypothesis whose answer cannot inform any decision. If no possible outcome of the test changes anything, the hypothesis is academic.

## Tie to framing

The whole proactive-monitoring loop hinges on this skill. If hypothesis generation manufactures candidates from noise, the rest of the pipeline confirms noise as findings. If hypothesis generation is honest about prior strength, holds the cap, and gracefully says "no hypotheses worth pursuing" when the data is unremarkable, the pipeline's "nothing concerning this period" output emerges naturally from the front of the pipeline rather than being patched in at the back.

## Output-shape discipline

Code execution can support pattern surfacing during hypothesis generation (e.g., computing percentile rankings, change-point candidate lists), but only returns the small summary needed to articulate hypotheses — never raw rows. The output of this skill is a short structured list of hypotheses, typically ≤ 8 entries.
