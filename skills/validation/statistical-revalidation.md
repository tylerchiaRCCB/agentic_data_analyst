# Validation Skill: Statistical Revalidation

**Loaded by:** Findings Validator.
**Purpose:** Independently re-compute every claim made by upstream analytical agents. The Validator does not take the investigator's numbers on faith — it runs the math itself, on the original data, and either confirms, downgrades, or rejects each claim. This is the system's epistemic backbone.

The investigator and the validator are deliberately separated. The investigator's incentive is to produce findings; the validator's incentive is to refuse findings that don't survive scrutiny. Statistical revalidation is the mechanism of that refusal.

## The four-layer validation

Every finding receives four checks. The result of each is recorded in `ReviewedFinding.layer_results` (see [artifact-schemas.md](../../orchestration/artifact-schemas.md) §4.9):

### Layer 1 — Statistical rigor
Examine the methodology the upstream agent used to produce the claim:
- Was the appropriate test selected for the data shape? (See [statistical-rigor.md](../universal/statistical-rigor.md), [resistant-statistics.md](../universal/resistant-statistics.md).)
- Were sample sizes adequate? Compute the **achieved power** for non-significant claims being reported as "no effect."
- Was multiple-comparison correction applied when the upstream search examined many candidates?
- Were effect sizes reported alongside p-values? Is the effect size practically meaningful, not just statistically detectable?
- Were resistant statistics used on skewed metrics?

Outcome: `pass` / `partial` / `fail`. A `fail` here downgrades the finding regardless of subsequent layers.

### Layer 2 — Independent recomputation
Re-run the actual computation that produced the central statistic. Do not rerun the upstream agent's exact code (which might re-produce the same bug); write fresh code from the finding's stated `data_slice`, `metric`, and `computation`. Compare:

- If the Validator's recomputed value matches the upstream value within tolerance (default: relative difference < 1% for floats; exact match for integers), record `match` and proceed.
- If they disagree, record `mismatch` with both values and an explanation of which is correct. The Validator's value is authoritative; the upstream value is flagged as a methodology defect.
- If the recomputation cannot be performed (e.g., underlying data inaccessible, code reference broken), record `unable_to_compute`. **Findings with this status receive grade F and are filtered from output** — the system never renders a claim it cannot independently verify when verification was required.

Outcome: `match` / `mismatch` / `unable_to_compute`.

### Layer 3 — Guardrail pairing check
For each finding involving a primary metric movement, check the paired counter-metric per the domain context. See [guardrail-pairing-check.md](guardrail-pairing-check.md) for the methodology and [skills/domain-specific/guardrail-metric-pairing.md](../domain-specific/guardrail-metric-pairing.md) for the general rules. Outcome: `pass` / `trade_off` / `n/a`.

### Layer 4 — Domain plausibility
Read the finding against the domain context document's known quirks, anomaly thresholds, and historical patterns. Implausibility checks:

- Does the magnitude exceed any historically observed range without an explanation?
- Does the finding coincide with a known data artifact in the quirks section (system migration date, definition change, refresh delay window)?
- Does the finding contradict a known invariant in the domain (e.g., a "negative inventory" claim, a "fill rate > 100%" claim)?

Outcome: `plausible` / `implausible` / `n/a`. Implausibility doesn't necessarily reject — sometimes the finding *is* something genuinely unusual that the domain context didn't anticipate — but it forces a downgrade and a caveat surfacing the implausibility.

## Grading from the four layers

| Statistical rigor | Recomputation | Guardrail | Plausibility | Grade |
|---|---|---|---|---|
| pass | match | pass / n/a | plausible | **A** |
| pass | match | trade_off | plausible | **B** *(trade-off must be surfaced)* |
| partial | match | any | plausible | **B** *(rigor caveat required)* |
| pass | match | any | implausible | **C** *(implausibility surfaced; preliminary framing)* |
| any | match | any | any | at most the lowest grade above |
| fail | any | any | any | **D** *(filtered from recipient output)* |
| any | mismatch | any | any | **D** or **F** *(depending on magnitude)* |
| any | unable_to_compute | any | any | **F** *(filtered)* |

The Validator's `justification` field records *which combination of layer outcomes produced the grade*, so a reviewer auditing a particular finding can see the chain of reasoning.

## When the Validator's recomputation produces a different number

If Layer 2 returns `mismatch`, the Validator does not silently overwrite the upstream value. It records both values in `revalidation_summary.discrepancy_details` with an `explanation`. The Communication Agent surfaces neither directly in the recipient output — the discrepancy is a methodology flag for the run, not part of the finding. The recipient sees the finding filtered (grade D/F) and the run log records why.

## Required output

Per [artifact-schemas.md](../../orchestration/artifact-schemas.md) §4.9, each `ReviewedFinding` carries:
- `finding_id`, `finding_claim` (restated)
- `grade` (A–F)
- `justification` (which layer outcomes drove the grade)
- `layer_results` (the four outcomes above)
- `required_caveats` (caveats that must accompany the finding if it reaches output)
- `recommended_actions_for_investigator` (when grade is B or below — what would need to happen for this finding to reach grade A)

## Anti-patterns

- Rubber-stamping the investigator's numbers without independent recomputation. The whole point of separation is that the Validator runs the math itself.
- Promoting a finding to A because it "looks right" in the absence of a guardrail check. Layer 3 is required, not optional.
- Recording `unable_to_compute` and then rendering the finding anyway with a caveat. The system never renders a claim it cannot verify when verification was required.
- Failing Layer 4 (implausibility) and then promoting the finding to A on the strength of Layers 1–3. Implausibility is a downgrade, not optional context.
- Using the upstream agent's own helper functions or cached results for "recomputation." Fresh code on the original data, every time.

## Tie to framing

The Validator is the system's epistemic backbone. Recipient trust in the tool depends on the recipient's experience over many runs that *when a finding appears, it survived this process*. Grade D and F findings filtered out are not "lost work"; they are exactly the work the tool exists to do — separating what holds up from what doesn't.

A run in which the Validator filters every finding is not a failed run. It is a run in which the data had no claim worth surfacing. The Communication Agent's descriptive-summary path takes over from there.

## Output-shape discipline

Code execution during revalidation returns scalars and small summary tables — same as the investigator's outputs. The Validator's code execution operates on the same `dataset_handle`; it does not re-load data into context or request row-level dumps. Per the discipline rules in [pipeline-definitions.md](../../orchestration/pipeline-definitions.md) §10.
