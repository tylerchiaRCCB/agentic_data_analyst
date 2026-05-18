# Failure Recovery

Retry, degradation, and error-handling rules for the agentic data analyst orchestrator.

> **Framing reminder.** Failure handling must preserve honesty. When something goes wrong, the system says so — visibly, in the recipient-facing output, with the affected scope made explicit. The orchestrator never silently renders a degraded result as if it were a complete one, and it never fabricates output to fill the gap of a failed stage. The discipline of [framing-rigor-not-insights](../mvp_plan.md#core-framing-read-first) applies at least as strongly under failure as under success.

---

## 1. Principles

These principles govern every recovery rule below. When a specific case is ambiguous, fall back to these.

1. **Surface, do not paper over.** Any degradation visible to recipients must be labeled in the output. "Partial results" is the standard label.
2. **Retry sparingly.** Transient failures get one retry with backoff. Persistent failures degrade. Long retry loops obscure problems and burn budget.
3. **Skip-and-flag beats hard-fail.** If a non-critical agent fails entirely, the pipeline continues with the remaining artifacts and the final output notes what was skipped. Critical agents (Question Framer, Data Retrieval, Findings Validator under specific conditions) do hard-fail.
4. **Never silently render unvalidated findings.** If the Findings Validator fails or is unable to validate a specific claim, the affected claim is either filtered or surfaced with an explicit "validation could not be performed" caveat. See §6.
5. **Failure modes do not unlock skipped framing rules.** A failed pipeline does not bypass the discipline of empty-findings output — it produces an honest "we could not complete this analysis" output, not a fabricated finding.
6. **Every failure is logged.** Observability captures failure type, stage, retry count, error payload, and remediation taken. See [pipeline-definitions.md](pipeline-definitions.md) §9 for lineage and [src/observability/](../src/observability/) for telemetry.

### Why exactly one retry on logical failures

Most of the rules below specify one retry on schema-validation failures, lineage gaps, prompt-injection suspicions, and similar agent-side issues. Not zero. Not three. The reasoning:

- **Zero retries is too brittle.** Transient issues — a single malformed JSON response from an otherwise-correct model, a clarifying hint the model needs to satisfy the schema — would fail runs that would succeed on a second attempt. Building zero retries into the orchestrator means rebuilding ad-hoc retries everywhere.
- **Many retries waste budget on systematic failures and obscure debugging.** If a model produces malformed JSON twice in a row with the validation error fed back between attempts, more retries are unlikely to help — the model is fundamentally confused about what we want, and degradation is the honest answer. A retry loop hides the failure mode in the logs and burns tokens that should have triggered the skip-and-flag path.
- **One retry distinguishes transient from systematic.** It catches the transient case (single retry resolves) without amplifying the systematic case. It also keeps the cost model predictable — a stage costs at most 2× its base cost.

Two cases get more than one retry because the nature of the failure is fundamentally different:

| Failure type | Retries | Why different |
|---|---|---|
| **Rate limits (HTTP 429)** | Up to 5 with exponential backoff | A rate limit is by definition transient and resolves on its own. Backoff respects the upstream quota; retrying is the correct response, not a band-aid for a stuck call. |
| **Code execution errors (initial attempt + 1 retry with backoff)** | 2 attempts total | The most common cause is a model-side syntax error or a transient sandbox hiccup. The retry-with-error-feedback path corrects most syntax errors. Beyond that, the underlying problem is methodological, not transient. |

The one-retry rule is the default, not a ceiling. Specific agents or skills can override it in `pipeline_config.yaml` if a workload genuinely benefits from more (or fewer) retries — but the override has to be justified, because the default exists for a reason.

---

## 2. Schema validation failures

The orchestrator validates every artifact against its schema (see [artifact-schemas.md](artifact-schemas.md) §5) before passing to the next stage.

| Failure | Response |
|---|---|
| **Schema-shape failure** — missing required field, wrong type, malformed JSON. | Retry the agent call **once** with a clarifying user message that includes the validation error and the relevant schema excerpt. If the retry succeeds, continue. If it fails, treat as agent total failure (§4). |
| **Cross-field consistency failure** — e.g., a `Finding.evidence_statistic_ids` references a `Statistic.id` not present in the artifact. | Retry **once** with a clarifying message. If retry fails, degrade: the agent's artifact is preserved as-is but marked `status: "degraded"` with `status_notes` explaining the inconsistency. Downstream agents may treat referenced-but-missing statistics as "unknown" rather than abort. |
| **Lineage gap** — `Statistic.lineage.code_ref` missing or referencing nonexistent code. | Retry **once** specifically requesting the code reference. If retry fails, the statistic is marked with a high-severity caveat and propagated downstream. Communication Agent must carry the caveat forward. |
| **Unknown fields** | Allowed. Orchestrator logs them but does not fail. |

Retries reuse the same agent definition and skills; only the user message changes to include the validation error.

---

## 3. Data readiness failures

The Data Profiler emits `readiness_assessment: "INSUFFICIENT"` when the data cannot support the analytical pipeline the Question Framer composed.

When this occurs:

1. The orchestrator **does not proceed** to downstream analytical agents.
2. The pipeline jumps directly to the Communication Agent.
3. The Communication Agent renders a `descriptive-summary` output describing:
   - What data was loaded and what its limitations were.
   - Which baselines and quality checks failed.
   - Specifically what would have been required for the originally-requested analysis.
   - That no analytical findings are being produced because the data is insufficient.
4. Run status is `degraded`, not `failed` — the system completed its job (honestly reporting it cannot analyze this data) and the recipient receives a usable artifact.

`READY_WITH_CAVEATS` does **not** trigger this path. Pipelines proceed with caveats propagated downstream.

---

## 4. Agent total failure

A non-critical agent fails entirely when:

- Retries have been exhausted on schema validation.
- The agent's API call raises a non-retryable error (auth failure, model 4xx other than rate-limit).
- Code execution within the agent fails repeatedly and the agent emits `status: "failed"`.

Response:

- **Non-critical agents** — Relationship Analyzer, Pattern Discoverer, Time Series Analyzer, Root Cause Investigator, Opportunity Identifier: **skip-and-flag.** The pipeline continues with the remaining stages. A high-severity caveat is added to the run's caveat bag: `"Stage <agent> failed and was skipped — analytical depth in <area> is reduced."` The Findings Validator receives the partial artifact set; the Communication Agent surfaces the caveat in the output.
- **Critical agents** — Question Framer, Data Retrieval Agent: **hard-fail.** The orchestrator cannot proceed without a brief or without data. The run terminates with `status: "failed"` and writes a failure report to `output/<run_id>-failure.md` describing what happened.
- **Findings Validator**: see §6.
- **Communication Agent**: hard-fail. If the renderer itself fails, there is no recipient-facing output; the orchestrator writes a failure report and the raw upstream artifacts to `output/<run_id>-raw.json` so the failure is debuggable.

### 4.1 Code execution errors

When a skill's code execution step fails:

| Retry | Action |
|---|---|
| 1 | Retry once with exponential backoff (initial delay 2s, max 30s). |
| 2 (failure persists) | The agent marks the specific skill as failed in its `caveats` and continues with other skills. The artifact is emitted with the gap surfaced. |

Code execution errors do not by themselves trigger agent total failure unless the agent has no remaining computable output.

### 4.2 API errors

| Error type | Response |
|---|---|
| Rate limit (429) | Retry with exponential backoff. Up to 5 retries. After 5, treat as agent total failure. |
| Transient 5xx | Retry up to 3 times with backoff. |
| Auth failure (401/403) | Hard-fail the run immediately. Surface to operator, not recipient. |
| Context window exceeded | Recompose the user message with reduced artifact detail (smaller statistics tables, dropped low-confidence findings) and retry once. If still failing, treat as agent total failure. |
| Other 4xx | Log full payload, treat as agent total failure. |

---

## 5. Token budget enforcement

MVP scope: **telemetry only.** The Budget Tracker records cumulative spend per stage and emits warnings when cumulative cost crosses 75%, 90%, and 100% of `framer_brief.token_budget`. The orchestrator does not halt execution on budget exceedance in MVP.

Production scope (deferred to Phase 2): hard cap triggers graceful truncation:

1. The currently-executing stage is allowed to complete (cancelling mid-call is more expensive than finishing).
2. All subsequent stages are skipped except Communication Agent.
3. Communication Agent is invoked with whatever artifacts exist plus a high-severity caveat: `"Analysis stopped at depth N due to token budget. Recipient should not infer that absence of further findings means none exist."`
4. The output is rendered with explicit "analysis truncated" framing.

Even in production, budget exceedance does not justify silent omission. The recipient learns the analysis was capped.

---

## 6. Findings Validator failure — the special case

The Findings Validator's role is independent quality verification. Its failure must never result in silent rendering of unvalidated findings.

### 6.1 Failure modes

| Mode | Response |
|---|---|
| **Validator fails entirely** (schema retry exhausted, API error after retries) | Pipeline does NOT skip the Validator and proceed. The Communication Agent is invoked with the upstream analytical artifacts AND a system-level caveat: `"Findings Validator failed to run. No claims in this output have been independently validated."` All findings are rendered with `ConfidenceGrade: "C"` (preliminary) maximum, regardless of their original strength. The output framing makes the validation gap explicit. **This is distinct from the case where the Validator was *intentionally skipped* for a lookup or descriptive pipeline that made no analytical claims — those outputs read normally with a source line, not a system-level caveat. See [pipeline-definitions.md](pipeline-definitions.md) §3 "When the Validator is skipped — and how the output should read."** |
| **Validator runs but fails to validate specific findings** (e.g., recomputation fails on one finding only) | Affected findings receive `grade: "F"` with `layer_results.independent_recomputation: "unable_to_compute"` and are filtered from the Communication Agent's action cards. They appear in the run's audit log but not in the recipient output. |
| **Validator flags a guardrail trade-off** | Not a failure — this is the Validator working as designed. The trade-off is rendered alongside the finding in the recipient output via `ActionCard.caveats`. |
| **Validator's own code execution fails** | Same as agent code execution (§4.1) — retry, then surface the gap in the artifact and propagate the high-severity caveat. |

### 6.2 The non-bypass rule

A future contributor may be tempted to add a configuration flag that allows the pipeline to proceed past a Validator failure as if the Validator had passed everything. **Do not add this flag.** It violates the framing. The Validator is the system's epistemic backbone; the orchestrator surfacing its absence is the entire point.

Reviewers: if you see a code path that allows unvalidated findings to render without the high-severity caveat, flag it as a regression.

---

## 6a. Missing domain context

The Question Framer's brief includes `data_requirements.domain`, which the orchestrator resolves to a file in `context/domains/<domain>.md` (or `context/examples/<domain>.md` for the MVP demo). When that file does not exist or is empty:

**MVP behavior — proceed with high-severity caveat.** The pipeline runs with universal + analytical skills only, no domain context loaded. The orchestrator adds a high-severity caveat to the run's caveat bag:

> *"No domain context document was found for `<domain>`. Analysis proceeded without business-meaning context: metric definitions, guardrail pairings, known data quirks, and investigation hypothesis libraries were not available. Findings should be read as data-shape observations, not domain-grounded conclusions. The Findings Validator's guardrail-pairing check produced reduced coverage as a result."*

The Communication Agent must carry this caveat into the recipient-facing output verbatim, and should prefix the output with an explicit `Limitations` section calling out the missing context.

**⚠️ HARDENING TODO (post-MVP).** This permissive mode exists so the demo and exploratory development can proceed before every domain has a fully documented context file. It is **not** the production target. Before production rollout:

1. Add a configuration gate (e.g., `pipeline_config.yaml: require_domain_context: true`) that hard-fails the run when context is missing, with a clear operator message pointing to the missing file path and the domain-context template.
2. Until that gate is enabled, the permissive caveat above MUST appear in every recipient-facing output for runs without a domain context — reviewers should treat its absence as a bug.
3. The Findings Validator's guardrail check methodology must explicitly note that guardrail pairings come from the domain context, not the validator's prior knowledge — if context is missing, guardrails cannot be checked, and the validator says so rather than skipping the check silently.

The intent: never let a recipient consume an output that *looks* domain-grounded but isn't. The permissive mode trades a hard gate for a loud, recipient-visible declaration of what was missing.

---

## 7. Memory retrieval failures (interactive mode — Phase 2 surface area)

Interactive Q&A mode is deferred to Phase 2, but the orchestration model includes session memory. Failure rules for completeness:

| Mode | Response |
|---|---|
| Memory retrieval returns no results | Continue without prior context. No caveat needed. |
| Memory retrieval returns results for the wrong entity | The observability layer detects this via entity-id check on returned items. The orchestrator does not silently use mismatched memory — it discards the result and continues without prior context, logging the mismatch. |
| Memory store unavailable | Continue without memory. Log error. Add low-severity caveat to run that conversational continuity is unavailable. |

Memory is opportunistic context, never a source of authoritative claims; failures here degrade gracefully without affecting analytical validity.

---

## 8. Prompt injection detection at runtime

The Data Retrieval Agent sanitizes free-text columns at load time. If a downstream agent's response contains content that appears to follow injected instructions (e.g., references to fake personas, attempts to override instructions, output that does not match the user message intent), the orchestrator's response is:

1. Discard the suspect artifact.
2. Retry the agent call **once** with a clarifying user message that re-emphasizes the agent's role and explicitly instructs treating all data values as data, not instructions.
3. If the retry still produces suspect content, treat as agent total failure (§4) — non-critical agents skip-and-flag, critical agents hard-fail.

This is a coarse heuristic. The detailed detection logic lives in `src/data_access/injection_defense.py` and is consulted both at load time and on output review.

---

## 9. Surfacing failures to recipients

The Communication Agent's output is the single recipient-facing channel. Failures surface to recipients through:

- **`carried_caveats`** — every high-severity caveat from any upstream artifact (including failure caveats added by the orchestrator). The Communication Agent must include these verbatim in the rendered output, in a section labeled `Caveats` or equivalent. Lost caveats are a validation failure.
- **`output_mode`** — when failures degrade the run, the orchestrator may override the Question Framer's intended `output_mode` to `descriptive-summary` if no action cards can be honestly produced.
- **Run status banner** — when run status is `degraded`, the Communication Agent prefixes the output with a short status note (e.g., *"Partial results — one analytical stage failed and was skipped. Affected scope: <area>."*).

Recipients should always be able to read a final output and know whether the analysis ran to completion, was partial, or was unable to analyze the requested data. They should never read an output and silently consume a degraded result as complete.

---

## 10. Failure artifacts

Per failed run, the orchestrator writes:

- `output/<run_id>-failure.md` for hard-failed runs (includes failure type, stage, error payload, framer brief, partial artifacts).
- `output/<run_id>-raw.json` for any run where the Communication Agent itself failed — contains the full artifact bag in raw form so the run is debuggable.
- A failure entry appended to the run log captured by `src/observability/run_logger.py`.

These are operator-facing, not recipient-facing. They exist for debugging and audit, not delivery.

---

## 11. What this document does not cover

- **Specific agent prompt clarifying-instruction wording.** That belongs in `src/orchestrator/prompt_assembler.py` and in agent-side error handling guidance.
- **Backoff parameter values.** Defaults are in this document; tunable values live in `config/pipeline_config.yaml`.
- **Alerting and on-call rotation.** Production concern, out of MVP scope.
- **Specific UI for failure status.** MVP renders to markdown; failure visibility is via markdown sections and console output.

This document defines failure semantics. Configuration and UI are downstream concerns.
