# Instructions for AI coding assistants

You are working on the **Agentic Data Analyst** — a multi-agent system that applies senior-data-analyst-level rigor to data nobody has time to manually examine. This file is your orientation. Read it before making any non-trivial change.

These instructions apply to **any AI assistant**: Claude Code, GitHub Copilot, Cursor, future model versions. The same file is auto-loaded by Claude Code; GitHub Copilot reads it via `.github/copilot-instructions.md` (which references this file).

---

## The single most important thing

**This is a discipline tool. The product is rigor and intellectual honesty applied repeatedly to data — not insight generation.**

Sometimes the pipeline produces an actionable finding. Sometimes it produces *"nothing concerning this week, here is a descriptive summary."* Both are valid outputs. A system that fabricates a finding to fill space is a bug, not a feature.

Every change you make must reinforce this framing. If you find yourself loosening a validation gate, removing a caveat, smoothing grade-C language to sound more confident, or adding a fallback that hides a data gap — **stop**. You are working against the product's core value.

See [README.md](README.md) "What this is — and what it is not" for the framing in the user's voice.

---

## Required reading before substantive changes

Read these three documents *in this order* before changing anything beyond a typo:

1. **[docs/architecture.md](docs/architecture.md)** — three Mermaid diagrams + capability comparison vs. Fabric Agents / Cortex Agents. Establishes the three-layer architecture (audiences → framework → data layer → providers).
2. **[docs/walkthrough.md](docs/walkthrough.md)** — the 7-step narrated tour. Knowing the user-facing flow keeps you from making changes that complicate it.
3. **[docs/quick-reference.md](docs/quick-reference.md)** — the 8 files that matter; the commands; where outputs go.

For deep dives into a specific component:
- `mvp_plan.md` — 1100-line authoritative spec (use grep; don't read sequentially)
- `agents/<name>.md` — each agent's full definition
- `skills/<category>/<name>.md` — methodology files
- `orchestration/*.md` — pipeline composition, artifact schemas, failure recovery

---

## Repo layout — what lives where

```
agents/              · 11 agent definitions (markdown). Each declares role, position,
                       skills loaded, inputs, responsibilities, anti-patterns.
skills/
  universal/         · loaded with every agent call (statistical-rigor, etc.)
  analytical/        · loaded on demand by analytical agents
  validation/        · loaded by Findings Validator
  output/            · loaded by Communication Agent
  domain-specific/   · CPG-specific methodology
context/
  domains/           · per-domain context (markdown — informal in MVP)
  semantic_models/   · YAML semantic models for Cortex Analyst (Phase D2)
  templates/, examples/  · authoring templates
src/
  api/               · LLMClient protocol; ClaudeClient (Anthropic native);
                       LiteLLMClient (OpenAI/Gemini via LiteLLM)
  orchestrator/      · pipeline_executor, prompt_assembler, budget_tracker,
                       lineage_tracker, hitl_gate, schemas (Pydantic)
  data_access/       · excel_loader, injection_defense, snowflake_client,
                       cortex_analyst_client, cortex_agent_client
  observability/     · run_logger (structured JSON), tracer
  tools/             · replay_comms, synthesize_runs, extract_context_gaps
  delivery/          · (Phase 2)
config/              · pipeline_config.yaml — model selection, cost cap, HITL
data/
  generators/        · synthetic dataset generators (see "Common tasks" below)
  sample/            · generated CSVs
output/              · rendered recipient markdown per run
runs/<run_id>/       · per-run artifacts, JSONL logs, span traces, lineage
tests/               · 94+ tests; mock-SDK integration tests for orchestrator
docs/                · architecture, walkthrough, quick-reference, examples
webapp/              · self-contained web frontend (FastAPI + SQLite + htmx):
                       accounts/roles, per-user semantic-view YAML management,
                       runs with live logs, cron schedules. Own venv + tests +
                       CLAUDE.md — read webapp/CLAUDE.md before touching it.
                       adapters/agentic_pipeline.py bridges its worker contract
                       to `python -m src.main`.
```

---

## Hard rules — non-negotiable

### 1. Compute before reasoning, structurally

Every numeric claim in any artifact must come from executed code (Anthropic code execution sandbox), never from LLM reasoning. The `Statistic` Pydantic model REQUIRES a `lineage.code_ref` pointing at the cell that produced it. Group-comparison statistics REQUIRE `effect_size` AND `confidence_interval` — these are not prompt conventions, they are schema-enforced. See [skills/universal/statistical-rigor.md](skills/universal/statistical-rigor.md).

**Never** loosen `Statistic._enforce_required_fields_by_kind` to "make the validator stop rejecting things." If real Claude emissions are tripping it, fix the prompt or add a normalizer — do not remove the gate.

### 2. The Findings Validator is non-bypassable

Grades D and F are filtered from output. There is no override flag. A Communication Agent rendering a grade-D claim is a critical bug.

### 3. Causation gates

The `causation_vs_correlation` field on root-cause findings has three values: `established_causal`, `strong_correlation`, `associational`. The Communication Agent reads this and selects language. **Promoting `associational` to causal language is a render bug.** See [skills/output/confidence-language.md](skills/output/confidence-language.md).

### 4. Null-result-as-output

When the Findings Validator passes zero findings forward, the Communication Agent renders a descriptive summary. **This is a complete and valid output.** Do not add fallback code that injects placeholder findings. Do not let the LLM apologize for not having more to report. Read [skills/output/descriptive-summary-format.md](skills/output/descriptive-summary-format.md).

### 5. Tool-use structured output enforcement

Every agent emits its artifact via an `emit_<agent>_artifact` tool, NOT free-form JSON in text. Variants get caught by Pydantic normalizers as a fallback. See [skills/universal/structured-output-contract.md](skills/universal/structured-output-contract.md) and `agent_output_tool()` in [src/orchestrator/schemas.py](src/orchestrator/schemas.py).

### 6. Tracking-gaps with teeth

Data gaps surface as caveats in the artifact and the recipient output. The agent must not silently work around a missing column with a proxy without labeling the workaround. See [skills/universal/tracking-gaps.md](skills/universal/tracking-gaps.md).

### 7. Work-IP boundary

This is a personal GitHub repo owned by Coby. The user's team is at a CPG company; their work-specific configurations live in a separate work-owned repository (Azure DevOps).

**Do not commit to this repo:**
- Real account names, customer IDs, SKU codes, or any real data values
- Internal metric thresholds tied to specific business definitions (e.g., "FTPR target is 88% per Walmart JBP")
- Named coworker secrets or company-specific Azure Key Vault references
- Domain context files containing business-validated guardrail values
- Any data file with rows beyond clearly-synthetic dummy

**Do commit:**
- Generic framework code
- Schema normalizers for variant LLM outputs (variants are LLM behavior, not work IP)
- Template files (e.g. `context/semantic_models/_TEMPLATE.yaml`) — generic shapes only
- Example files explicitly marked as scaffolding (e.g., `walmart_in_store_execution.example.yaml` with PLACEHOLDER thresholds)

---

## Conventions for adding things

### Adding a new agent

1. Create `agents/<name>.md` matching the existing structure: Role, Position in pipeline, Skills loaded, Output, Inputs you receive, Responsibilities in order, What this agent does NOT do, Anti-patterns, Tie to framing.
2. Define a `<Name>Payload` Pydantic model in `src/orchestrator/schemas.py`.
3. Register the agent in:
   - `AgentName` Literal at the top of `schemas.py`
   - `_CANONICAL_AGENTS` set
   - `PAYLOAD_BY_AGENT` dict at the bottom
   - `model_per_agent` in `config/pipeline_config.yaml`
4. Add a minimal fixture under `tests/fixtures/<name>_minimal.json`.
5. Add tests verifying schema dispatch + tool spec validity.

### Adding a new skill

1. Create `skills/<category>/<name>.md` matching the existing structure: Role, Why this skill exists, When to invoke, Procedure, Mandatory practices, Anti-patterns, Tie to framing.
2. If it's a universal skill (applies to every agent), add to `UNIVERSAL_SKILL_NAMES` in `src/orchestrator/prompt_assembler.py`.
3. Reference the new skill from the agent definitions that should load it.

### Adding a schema normalizer (when an agent emits a variant)

This is the most common change. When the team's testing surfaces a new LLM-output variant:

1. Add the normalizer to the relevant `_normalize_*` model validator in `schemas.py`. Pattern: check for the variant key, coerce to canonical.
2. Add a regression test in `tests/test_artifact_schemas.py` pinning the variant input → canonical output. The test should fail before your normalizer fix and pass after.
3. Commit message format: *"Normalize <variant description> in <Payload>"* — be specific so the team can scan for what variants have been handled.

### Adding a Cortex semantic model (data layer work)

1. Copy `context/semantic_models/_TEMPLATE.yaml` to `context/semantic_models/<domain>.yaml`.
2. Fill in tables, dimensions, measures, guardrail_metric_pairings, thresholds, known_data_quirks, stakeholder_map.
3. **Do NOT commit real business thresholds** — those live in the work-owned repo. Use PLACEHOLDERs and explicit comments.
4. Validate with `uv run pytest tests/test_cortex_scaffolding.py::test_cortex_analyst_lists_available_semantic_models`.

---

## Common tasks

### Run the full test suite

```bash
uv run pytest -q       # ~2 seconds; 94+ tests
```

If you make any change to `src/orchestrator/*`, you MUST run this and it MUST pass. Orchestrator integration tests use a `MockClaudeClient` (see `tests/mocks/`) — no API tokens spent. There is no excuse for shipping orchestrator changes without test confirmation.

### Run a dry-run (plumbing check, free)

```bash
uv run python -m src.main --question "X" --data data/sample/smoke-test.csv --dry-run
```

30 seconds, $0. Assembles every agent's prompt, validates schemas, writes a report to `output/dry-run-<id>.md`. Do this after any prompt assembly or schema change.

### Generate a dummy dataset for a NEW schema (likely tomorrow's task)

**Pattern off the existing generator** at [data/generators/generate_smoke_test.py](data/generators/generate_smoke_test.py). That file is the canonical example — it generates ~21,000 rows across 40 accounts × 5 regions × 52 weeks × 10 SKUs × 3 categories with 8 intentionally-planted analytical patterns.

To extend for a new schema:

1. **Copy** `generate_smoke_test.py` to `generate_<schema_name>.py` (e.g., `generate_walmart_in_store_execution.py`).
2. **Replace** the dimension lists (REGIONS, SKUS, etc.) and column names with the new schema's.
3. **Re-implement the planted patterns** so they exercise the same analytical capabilities the new schema cares about. The smoke-test generator's 8 patterns are a guide:
   - **Persistent entity-level anomaly** — one entity (e.g., one Account Manager, one filler, one SKU) shows a sustained metric drop. Tests grade-A finding production.
   - **Regional declining trend** — one region shows weekly decline over 6-8 weeks. Tests Time Series Analyzer + change-point detection.
   - **Seasonal spike** — a clean year-end peak. Tests STL decomposition.
   - **Correlation pattern** — two metrics move together (e.g., promotional cannibalization across SKU pairs). Tests Relationship Analyzer.
   - **Simpson's Paradox** — aggregate trend reverses at the subgroup level. Tests the mandatory Simpson's check in Validator.
   - **Concentrated null values** — one entity has 30%+ missing data. Tests data-quality flagging.
   - **Injection-shaped strings in free text** — ~10% of a free-text column contains "ignore previous instructions" patterns. Tests prompt-injection defenses.
   - **~65% stable baseline** — most rows are deliberately uninteresting. Tests the descriptive-summary discipline (most entities should produce NO findings).
4. **Save output** to `data/sample/<schema_name>.csv`.
5. **Validate** by running a dry-run against the new file:
   ```bash
   uv run python -m src.main --question "smoke test" --data data/sample/<schema_name>.csv --dry-run
   ```
6. **Confirm** the dry-run report (`output/dry-run-*.md`) shows reasonable per-agent prompt sizes and ends with `Plumbing verification PASSED`.

**For the demo data specifically:** the user (Coby) decides what story the planted patterns tell. The patterns should match what he wants the system to surface at the demo. If you're generating without that direction, default to the 8 above; the user will direct refinements.

### Run the live pipeline (costs ~$10-15)

```bash
uv run python -m src.main --question "What patterns are present this period?" \
                          --data data/sample/<schema_name>.csv
```

15-30 min wall time. **Confirm the user has approved spending the $10-15 before kicking this off — it is not your money.**

### Recurring weekly runs with prior-run context

For recurring prompts (same weekly question), include prior run output as bounded
context so agents can compare trend direction and persistence:

```bash
# Auto-use latest completed run in runs/
uv run python -m src.main --scheduled \
  --prompt-config config/prompts/weekly-anomaly-scan.yaml \
  --source cortex_analyst --domain walmart-opd --backend foundry-dev \
  --use-latest-run-context

# Or use a specific prior run id
uv run python -m src.main --scheduled \
  --prompt-config config/prompts/weekly-anomaly-scan.yaml \
  --source cortex_analyst --domain walmart-opd --backend foundry-dev \
  --prior-run-id 20260618T141448Z-483d87f3
```

Guardrail: prior-run context is reference only. Agents must recompute all numeric
claims from current-run data; they must not copy forward prior claims.

### Replay just the Communication Agent (cheap iteration)

```bash
uv run python -m src.tools.replay_comms --run-id <existing_run_id>
```

~$0.30, 30 seconds. Use when iterating on output formatting / comms-agent prompts.

### Synthesize across multiple runs

```bash
uv run python -m src.tools.synthesize_runs --run-ids r1,r2,r3
```

~$5-10. Use when there are ≥2 per-function runs and you want cross-functional insights.

---

## Commit conventions

- **Subject line:** descriptive, in present tense. *"Add Synthesizer Agent"*, not *"Synthesizer changes"*.
- **Body:** explain what + why. Reference the failure mode you're closing or the capability you're adding. Multi-line is fine — the team reads commit messages.
- **No commits that include real work data.** If unsure, ask before committing.
- **Test mention:** if you added tests, say how many and what they cover. Reviewers should be able to scan `git log` and know test coverage trajectory.

---

## What NOT to do

- **Don't skip running tests** before commit. There is no excuse with a 2-second test suite.
- **Don't add error handling that hides failures.** A stage that fails should fail loudly via the existing skip-and-flag or hard-fail paths. Adding `except Exception: pass` to "make it work" is the worst possible change.
- **Don't add a fallback that injects placeholder findings.** When the validator passes zero findings, the system produces a descriptive summary — that is the design.
- **Don't promote correlations to causal language to make output read better.** The `causation_vs_correlation` flag is the gate; respect it.
- **Don't fabricate "look-good" numbers in test fixtures.** Fixtures should be minimal-valid. If a test needs a realistic statistic, write a comment explaining what it represents.
- **Don't add features beyond what the current task requires.** A bug fix doesn't need surrounding cleanup; a one-shot operation doesn't need a helper. Three similar lines is better than a premature abstraction.
- **Don't write multi-paragraph comments or docstrings.** One short line max. Names should carry the meaning. Comments for non-obvious WHY only.

---

## When you're stuck

1. Re-read [docs/walkthrough.md](docs/walkthrough.md) — most "what does this system do" questions are answered there.
2. Grep `mvp_plan.md` for the relevant section.
3. Look at a similar existing thing — every new agent / skill / normalizer has predecessors you can pattern off.
4. If the user is around: ask. If they're not: prefer minimal, conservative changes. Better to leave a TODO than to ship something fragile.

---

## Tomorrow's likely task (2026-05-26)

If you (an AI assistant) are reading this on the morning of May 26 because the data scientist on the team is using you to help with the demo prep:

The DS will paste a column schema. Your job:

1. **Build the data generator** for that schema following the "Generate a dummy dataset for a NEW schema" pattern above. Use [data/generators/generate_smoke_test.py](data/generators/generate_smoke_test.py) as the template.
2. **Default to embedding the 8 standard planted patterns** unless the user specifies a different demo narrative.
3. **Save output** to `data/sample/<schema_name>.csv`.
4. **Run the dry-run** to validate.
5. **Hand off** to the user to kick off the live $10 run — that uses their API key and budget, not yours to spend.

If the user has specified a different demo story (e.g., *"the system should find a Filler-3 downtime cluster correlated with Product-A runs"*), implement that planted pattern instead of the generic 8. Be specific in the docstring at the top of the generator about which patterns are embedded — future debugging depends on that documentation.

The framework is rock-solid (94 tests passing, full architecture documented). The only thing left for the meeting is generating data and running. You have everything you need.
