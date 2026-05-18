# Analytical Skill: Predictive Readiness Assessment

**Loaded by:** Opportunity Identifier.
**Purpose:** Decide whether an observed pattern warrants building a predictive model — or whether it's better treated as a direct, immediately-actionable insight. This skill is the funnel from the agentic analyst to the data science team.

The tool's job is not to build models. Its job is to identify when a pattern is *worth* a model, route that recommendation to the data science team, and stay quiet when the pattern is something simpler — an insight to act on now, a one-off event, or noise that doesn't warrant modeling.

## When a pattern warrants a model

A pattern is a candidate for predictive modeling when **all** of these hold:

1. **The decision is repeated.** The downstream action is a recurring choice, not a one-time call. Models pay off when the same decision recurs many times.
2. **The pattern is stable.** The relationship has held over multiple time windows, multiple cohorts, multiple aggregation levels — see [triangulation.md](../universal/triangulation.md). A model trained on a fragile pattern doesn't generalize.
3. **Sample size is adequate** for the candidate model class. Rough heuristics:
   - Linear / GLM models: 10–20 observations per predictor as a floor, more for noisy data.
   - Tree-based / gradient boosting: hundreds to thousands of rows per outcome class.
   - Deep models: usually ≥ tens of thousands of labeled examples.
   These are not bright lines; they are starting points. Domain context and effect size matter.
4. **Features are available at decision time.** If the most predictive variables are only knowable in hindsight, the model would be backward-looking, not predictive. Features must be observable before the action is taken.
5. **The cost of being wrong is significant enough** to justify the model build, deployment, monitoring, and retraining overhead.
6. **A simpler heuristic does not suffice.** If a rule like "alert when X < threshold Y" achieves most of the predictive value, the model adds complexity without commensurate benefit.

## When a pattern does NOT warrant a model

- **The pattern is one-off** — a single event whose conditions won't recur, or a structural change that's already happened.
- **The action is the same regardless of prediction value** — if the recommended response is uniform across the predicted range, the prediction adds no decision value.
- **The pattern is already detectable by a threshold rule** with comparable precision/recall to a candidate model.
- **The data infrastructure cannot support model inference at decision speed** (e.g., the model would be batch but the decision is real-time).
- **The intervention cost is fixed regardless of who you target** — modeling who to target helps when the intervention is targetable.

A pattern that does *not* warrant a model is still often an opportunity — to act now, on the cases the agentic analyst has surfaced directly. The Opportunity Identifier produces an `intervention_recommendation` in that case, not a model-build flag.

## Required output for each candidate pattern

For each candidate pattern, emit:

- **Pattern description** — what was observed, with the supporting Statistic.
- **Warrants model: yes / no.**
- **Rationale** — which of the criteria above are met, and which are not. Be specific about which are uncertain (e.g., "sample size is at the floor for tree-based methods; would benefit from 3 more months of data").
- **Sample size adequacy** — explicit assessment.
- **Feature availability assessment** — "all candidate features are observable at decision time" or "feature X is only known post-decision; alternatives are Y and Z."
- **Suggested model class** — only if `warrants_model: yes`, and only as a starting point for the data science team, not a binding choice.
- **Estimated business value** — qualitative when MVP can't quantify; in production, paired with ROI estimation.

## Routing convention

When `warrants_model: yes`, the Opportunity Identifier's artifact flags the pattern in `predictive_readiness_assessment.candidates` with `warrants_model: true`. The Communication Agent then routes this finding to the data science team via the appropriate output channel (in MVP: rendered in the action card as a "Routed to data science" item).

The recipient sees that the system identified a pattern bigger than a single action card — that the agentic analyst is acting as the upstream funnel to the modeling team, exactly as the spec's Part 8 framing intends.

## Anti-patterns

- Treating "we have a pattern" as sufficient for "we should build a model." Most patterns don't pay back the cost of modeling.
- Recommending a model class without addressing feature availability at decision time. A model that requires hindsight features is not deployable.
- Failing to consider a simpler heuristic baseline. Models that beat the heuristic by 0.5 pts of AUC rarely justify the lifecycle cost.
- Routing every multi-factor finding to data science. Some multi-factor findings are simply complex insights that should be acted on directly.

## Tie to framing

This skill makes the tool's place in the broader org explicit. The agentic analyst surfaces, validates, and triages; the data science team builds models when patterns warrant. The two roles are complementary, not competitive. The tool's discipline — being honest about when a pattern does not warrant a model — prevents drowning the DS team in low-value model-build requests.

## Output-shape discipline

Code execution returns the readiness assessment values (scalars and short strings per candidate) — no row-level data. The candidate list is typically small (≤ ~5 per pipeline run).
