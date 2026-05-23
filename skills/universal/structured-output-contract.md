# Universal Skill: Structured Output Contract

**Loaded with every agent call.** This skill describes the contract between you and the orchestrator for emitting your final artifact.

## The contract

Every stage in the pipeline ends with you emitting exactly one **structured artifact** matching your agent's schema. The orchestrator provides a tool named `emit_<agent>_artifact` (e.g., `emit_data_profiler_artifact`, `emit_findings_validator_artifact`). You MUST call this tool exactly once, at the end of your work, with the artifact as the tool input.

The orchestrator will use the tool's JSON-Schema-validated input as your artifact. It bypasses all text-parsing — there are no opportunities to "explain" your output in prose that won't get through the schema gate.

## What this means in practice

- **Use code_execution for all numeric work.** This is non-negotiable per [statistical-rigor.md](statistical-rigor.md) — every numeric claim in your artifact must come from a computation, not from reasoning.
- **Use the emit tool exactly once, at the end.** Not as you go. Run all your analysis, compute all your statistics, then emit the final artifact with everything filled in.
- **Don't emit free-form JSON in the text response.** The text channel is for your own reasoning, scratch work, and intermediate explanations. The structured channel is for the artifact. Confusing the two will cause your artifact to be lost.
- **Every field in the schema is required if the schema says it is.** The orchestrator will reject your artifact if required fields are missing. You cannot ship a Finding without a `claim`. You cannot ship a Statistic without `lineage.code_ref` pointing at the cell that produced it.

## Why this matters

In the absence of structured-output enforcement, models drift over time: field names vary (`detail` vs. `text`), enums get verbose (`"HIGH (Grade B) — ..."` instead of `"B"`), required fields go missing under output pressure. The orchestrator handles these variants with normalizers, but normalizers are technical debt that grows every run.

With structured-output enforcement, the schema IS the enforcement boundary. Variants stop appearing at the source. The system becomes more reliable over time, not less. This is the production-grade pattern; the normalizer-only pattern is the MVP one.

## What if you cannot satisfy the schema?

If your analysis legitimately cannot produce a valid artifact (e.g., the data is unreadable, the question is malformed, an essential field cannot be computed):

1. **Do not fabricate values.** Empty arrays are valid where the schema allows them. `null` is valid where the schema allows it.
2. **Emit the artifact with the analytical state honest** — including a high-severity `Caveat` describing what couldn't be done and why.
3. **The Findings Validator will downgrade or filter your outputs as appropriate.** That's the system working as designed.

Never ship a fabricated number to satisfy a required field. Per [statistical-rigor.md](statistical-rigor.md), this is the most damaging error class in the system.

## Anti-patterns

- **Emitting JSON in the text response *and* via the tool.** The orchestrator prefers the tool output, but emitting both wastes tokens and may signal you're uncertain which channel to use. Use the tool. Period.
- **Forgetting to call the emit tool.** You'll see this when the orchestrator retries your stage with a clarification prompt. The fix is always: call the emit tool with your final artifact.
- **Calling the emit tool early and then "fixing" your analysis afterward.** Once you emit, you're done. Run all analysis first, then emit once.
