# Universal Skill: Close the Loop

**Role:** Every recommendation produced by the system must be specific, owned, measurable, and trigger-bound. No vague language — "monitor," "investigate further," "consider" — without the structural elements that make the recommendation actionable. Loaded with every agent call; binding on the Opportunity Identifier and Communication Agent.

A recommendation without these four elements is not a recommendation — it is a feeling.

## The four required elements

1. **Specific action.** Concrete enough that the recipient could write it on their calendar today.
   - **Bad:** *"Investigate the underperforming entity's issues."*
   - **Good (illustrated in sales, the MVP demo domain):** *"Call the account manager for Account 47 by Friday to discuss Tuesday delivery delays for SKU 12345; confirm whether the Tuesday window shift requested in their April email is the driver."*

   The pattern transfers across our CPG functional domains: a recipient role *(account manager (sales), supply planner (supply chain), plant manager (operations), trade finance partner (trade), category director (commercial))*, a time bound (by Friday), an entity *(account, DC, line, campaign, region)*, a specific subject *(delivery delays, fill-rate degradation, line downtime, promotional under-lift, deduction backlog)*, and a hypothesis to verify.

2. **Owner.** A role (and where possible a named person via the domain context) who is accountable. If the system does not know the owner, it surfaces the gap rather than invents one: *"Owner role: [account manager]; specific assignee to be filled by district manager."*

3. **Success criterion.** A measurable, time-bounded statement of what "done" means. The criterion must be checkable from the data the system will have on the next run.
   - **Bad:** *"Improve the metric."*
   - **Good (illustrated in sales):** *"Account 47 instock for SKU 12345 returns to ≥ 90% by the week of {date+14 days}, measured on the next weekly run."* In a supply chain context the criterion might be *"DC Atlanta fill rate returns to ≥ 95% within 7 days"*; in operations *"Line 4 changeover time returns to ≤ 22 minutes by next scheduled changeover"*. The metric and entity nouns change with the functional domain; the structure (target value, deadline, measurement source) does not.

4. **Follow-up trigger.** A specific condition that determines what happens next. The trigger must be observable and unambiguous.
   - **Bad:** *"Monitor for further drops."*
   - **Good:** *"If next week's run shows the metric below 85%, escalate to district manager. If at or above 90%, mark resolved."*

## Required practices

- The `intervention_recommendations` field on the Opportunity Identifier artifact MUST include all four elements per recommendation.
- The `ActionCard` rendered by the Communication Agent MUST include all four elements per card. Missing elements are a validation failure.
- When the data does not support a specific success criterion (e.g., the metric needed isn't tracked), `tracking-gaps.md` applies — produce an instrumentation request instead of a vague criterion.
- Do not promote a finding to an action card unless all four elements can be honestly filled. A finding without a specific action belongs in the descriptive summary, not in a card.

## Tie to framing

This skill is one of the strongest defenses against the failure mode of *manufacturing volume to look thorough.* If the only available "action" is vague, the card should not exist. The discipline to leave a card off the report — to let the descriptive summary stand alone for that area — is the discipline the product exists to enforce.

## Anti-patterns

- "Monitor," "watch," "track," "investigate further," "consider," "evaluate" — without the four elements. These words signal that the recommender did not actually have an action in mind.
- Sweeping recommendations covering broad classes ("educate the team," "improve processes") without a concrete first step.
- Success criteria stated in feelings ("improve relationship," "increase confidence") rather than data the next run can check.
- Follow-up triggers that depend on human judgment ("if it looks bad") rather than data thresholds.
