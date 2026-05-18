# Universal Skill: Analysis Design Spec

**Role:** Force every analysis to be designed before it is executed. Loaded with every agent call.

Before doing any analytical work, an agent must answer five questions. The answers do not need to be rendered to the recipient, but they must be reasoned through internally and must shape what work is done.

## The five questions

1. **What is the question?** State it in one sentence, in falsifiable form. *(Example, sales)* — "Are Southeast volumes down" is not a question; "Did Southeast weekly volume decline by more than 5% in the last 4 weeks vs. the prior 12-week baseline" is. The pattern transfers across our CPG functional domains (supply chain: "Did DC Atlanta fill rate fall below 95% in the past 4 weeks?"; operations: "Did Line 4 changeover time exceed 25 minutes on more than 20% of changeovers last month?"). The question should name the entity scope, the metric, the comparison, and the magnitude threshold that would count as a positive answer. If the question came in vague, sharpen it; if it contains an embedded premise (e.g., "Why is share declining"), verify the premise before proceeding.

2. **What decision does this analysis inform?** If no decision is downstream of the answer, the analysis is exploratory characterization — say so and adjust depth accordingly. If a decision is downstream, the analysis must produce evidence at the granularity the decision requires (e.g., "which accounts" if the action is account-level).

3. **What data is needed?** Required columns, required time window, required grain, required filters. Note explicitly what data would be ideal but isn't available, and what that limits.

4. **What does success look like?** Define this before running anything. Crucially: success includes the case where the honest answer is *"nothing of significance was found."* A run that concludes no anomaly, no opportunity, or no causal driver — and supports that conclusion with the work done — is a successful run, not a failed one. If you cannot articulate what a null result would look like, the analysis is not designed well enough to start.

5. **What are the limitations?** What confounders could explain the result? What biases are baked into the data? What alternative explanations should be considered before claims are made? These become caveats in the output.

## Required practices

- Write down (in working scratch, not output) the answer to all five before producing analytical claims.
- If question 1 cannot be sharpened to a falsifiable form, escalate that as a clarification need — do not improvise a question.
- If question 4 cannot include a null-result definition, the analysis is under-specified.

## Anti-patterns

- Skipping the design step and going straight to "let me check this data." Without a design, the analysis drifts toward whatever pattern is easiest to find, not what the question requires.
- Defining success only as "found a finding." This biases the analysis toward manufacturing one. Always define what a null result looks like.
- Treating the embedded premise of a question as established. Test it.
