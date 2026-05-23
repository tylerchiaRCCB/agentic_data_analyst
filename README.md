# Agentic Data Analyst

An AI system that embeds senior-data-analyst-level exploratory data analysis across teams with validated data domains, applied at a scale and consistency humans cannot match.

## What this is — and what it is not

**This is a discipline tool.** The product is *rigor and intellectual honesty* applied repeatedly to data nobody has time to manually examine. Sometimes that produces an actionable finding worth a stakeholder's attention. Sometimes it produces *"nothing concerning this period, here is a descriptive summary."* Both outputs are valuable.

**This is not a magic insight machine.** It does not promise dramatic new findings every run. A system that feels obligated to manufacture a finding when none is warranted is a bug, not a feature. The discipline to stay quiet when no finding rises to action is the product.

Every design decision — every agent, every skill, every prompt — must reinforce this framing rather than undermine it. A run that produces zero high-confidence findings is a *successful run*, not a failed one. The Communication Agent's "no actionable findings this period" output is a first-class output, not a fallback.

## How it works (high level)

The system runs as a composed pipeline of specialized agents, dynamically assembled per question or scheduled prompt:

1. **Question Framer** classifies the input, generates testable hypotheses, and outputs a pipeline composition.
2. **Data Retrieval Agent** loads data and applies prompt-injection defenses on free-text columns. It is read-only.
3. **Data Profiler** assesses quality, completeness, freshness, grain, and distributions via executed code.
4. **Relationship Analyzer, Pattern Discoverer, Time Series Analyzer** apply the analytical techniques the question requires — all statistical claims are computed, never reasoned about.
5. **Root Cause Investigator** explains why specific deviations occurred, with computed evidence.
6. **Opportunity Identifier** translates findings into forward-tense actions, or flags patterns that warrant a predictive model rather than an immediate intervention.
7. **Findings Validator** independently re-computes every claim, checks guardrail pairings, and assigns A–F confidence grades. Grades D and F do not reach output.
8. **Communication Agent** renders an action card when findings warrant action, or a descriptive summary when they do not. It never invents a finding to fill space.

Agents are stage-level decision-makers (what to do). Skills are methodology files (how to do it). Each API call assembles `agent + relevant skills + universal skills + domain context`. Domain meaning lives in markdown context documents, version-controlled and owned by data + business partners — not hardcoded in agent prompts.

The full architecture, agent specifications, skill catalog, orchestration design, and MVP scope are in [mvp_plan.md](mvp_plan.md). That document is the authoritative spec; this README is the orientation.

## MVP scope

The MVP demonstrates **proactive monitoring** against a generated demo dataset with intentional anomalies. It runs the full analytical pipeline end-to-end and produces action cards — or a descriptive summary if nothing rises to action. Interactive Q&A mode is deferred to a later phase.

The CEO demo is structured to feature the system's discipline: the strongest moment is when the pipeline runs against a stable region or segment and produces a brief "all clear" summary instead of fabricating a finding. That demonstration — *the tool will not cry wolf* — is the differentiator.

## Repository layout

```
agents/                    Agent definitions (one markdown per agent)
skills/
  universal/               Always loaded with every agent call
  analytical/              Loaded on demand by analytical agents
  validation/              Loaded by Findings Validator
  output/                  Loaded by Communication Agent
  domain-specific/         CPG-specific methodology
context/
  templates/               Template for new domain context documents
  domains/                 Per-domain context (populated as domains are added)
  examples/                Demo domain context for MVP
orchestration/             Pipeline composition, artifact schemas, failure recovery
src/
  orchestrator/            Pipeline executor, prompt assembler, memory, budget, lineage
  api/                     Anthropic API client wrapper
  data_access/             Excel/CSV loader; injection defenses; Snowflake stub
  observability/           Tracing and run logging
  delivery/                Report writer; live demo runner
  main.py                  Entry point (created later)
data/
  generators/              Demo data generator script
  sample/                  Generated demo files
output/                    Generated reports and action cards land here
config/                    Pipeline config, thresholds, delivery config
tests/                     Schema, prompt-assembly, pipeline composition tests
docs/                      Architecture, agent/skill authoring guides, demo walkthrough
```

Detailed layout — including the specific markdown and Python files that will populate each directory — is in Part 2 of [mvp_plan.md](mvp_plan.md).

## Build status

System definition is complete:
- 10 agent markdowns in `agents/`
- 33 skill markdowns across `skills/{universal, analytical, validation, output, domain-specific}/`
- 3 orchestration design documents in `orchestration/`
- Core runnable code: orchestrator, Claude API client, data loader, observability, Pydantic artifact schemas, scaffolded tests

Not yet built (deferred): demo data generator (no scenarios until late next week), full delivery formatting, parallel-group execution, Snowflake / Cortex Analyst data path, persistent memory.

## Quickstart

Requires Python 3.11+ and (for real runs) an `ANTHROPIC_API_KEY` environment variable.

```bash
# Install with uv (recommended)
uv sync

# Or with pip
pip install -e .
```

### Verify locally (no API calls, no tokens spent)

```bash
# Unit tests
uv run pytest

# Generate the smoke-test CSV (100 rows, generic CPG-shaped — NOT the real demo data)
uv run python -m data.generators.generate_smoke_test

# Dry-run: loads data, sanitizes free-text, assembles every agent's prompt, validates
# schemas, writes a report to output/dry-run-<id>.md. Zero API calls.
uv run python -m src.main \
  --question "smoke test" \
  --data data/sample/smoke-test.csv \
  --dry-run
```

A successful dry-run prints a per-agent prompt-size table and confirms `Plumbing verification PASSED`.

### First real run

First, set up your API key. Two equivalent options:

**Option A — `.env` file (recommended; persists across terminal sessions):**
```bash
cp .env.example .env
# Edit .env and replace the placeholder with your real key.
# The .env file is gitignored — it will never be committed.
```

**Option B — shell export (ephemeral, per-terminal):**
```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

Then run:
```bash
uv run python -m src.main \
  --question "What patterns are present in this dataset?" \
  --data data/sample/smoke-test.csv
```

### Production-style invocations

```bash
# Proactive monitoring with a scheduled prompt config
uv run python -m src.main \
  --scheduled \
  --prompt-config config/prompts/weekly-anomaly-scan.yaml \
  --data path/to/your.csv

# Once a domain context document exists, name it with --domain
uv run python -m src.main \
  --question "..." \
  --data path/to/your.csv \
  --domain commercial-sales
```

Outputs:
- **Recipient-facing markdown** — `output/<run_id>.md` (the Communication Agent's rendered output)
- **Per-run artifacts and logs** — `runs/<run_id>/`:
  - `run.log` — structured log lines (tee'd to stdout while running)
  - `spans.jsonl` — per-stage span trace
  - `artifacts/NN-<agent>.json` — every stage's typed artifact, for replay and audit
  - `lineage.json` — every claim's provenance (source, slice, code reference, agent)
  - `<run_id>-failure.md` — operator-facing failure report (only on hard-fail)

### Production-grade resilience features

The system enforces several disciplines structurally, not just via prompts:

- **Hard cost cap.** `max_cost_usd` in [config/pipeline_config.yaml](config/pipeline_config.yaml) (default $25) aborts a run cleanly when cumulative API spend crosses the cap. Soft warnings at 50/75/90%.
- **Tool-use structured output enforcement.** Every agent receives an Anthropic tool spec built from its Pydantic schema. Claude is expected to emit the artifact via tool_use; the structured channel is preferred over text-parsing. This eliminates ~70% of LLM-output variants over time.
- **Required-field rigor on Statistics.** Group comparisons, correlations, and regressions REQUIRE `effect_size` and `confidence_interval` at the schema layer — they cannot be omitted. The validator's rigor check is now backed by the artifact format itself.
- **Prompt versioning.** Every artifact carries `prompt_sha256` + `skill_hashes` (universal + agent block). Reproducibility holds even after skill files are edited — you can always tell which prompt-version produced an old artifact.
- **Parallel execution.** When the Question Framer emits a parallel group (e.g., the 3 analytical agents), the executor runs them concurrently in a thread pool. ~6-8 min off typical full-run wall time.
- **Human-in-the-loop gate.** Set `hitl_review_threshold` (e.g., `"A"`) to hold high-confidence findings for human review before delivery. Disabled by default; enable for production deployments where findings drive business-impacting decisions.
- **Structured JSON logs.** `runs/<run_id>/run.jsonl` is machine-parseable; each line carries timestamp, level, run_id, msg, and structured attrs. Ready for ingestion by Datadog/Splunk/etc.
- **Mock-SDK integration tests.** Orchestrator behavior (retry-once, skip-and-flag, hard-fail, budget-cap abort) is fully unit-tested without spending real API tokens. Regressions found in 1 second of pytest, not $10 of API calls.

### Tools — partial-pipeline replay and context-gap extraction

The pipeline saves typed artifacts for every stage under `runs/<run_id>/artifacts/`. Two tools operate on those artifacts and do **not** require running the full pipeline again.

**Replay only the Communication Agent against an existing run.** Use when you want to iterate on output formatting / prompts without re-running the analytical stages (~$0.30 vs ~$10+ for a full run):

```bash
uv run python -m src.tools.replay_comms --run-id 20260520T223548Z-89dba6ec
```

Reads `runs/<run-id>/artifacts/00-question-framer.json` through the validator's artifact, calls only the Communication Agent, and writes:
- `output/<run-id>-replay.md` — the rendered recipient markdown
- `runs/<run-id>/artifacts/05-communication-agent-replay.json` — the replay artifact

This is the right tool whenever the question is *"does the output look right?"* — you don't need to re-pay for the analytical pipeline to iterate on rendering.

**Extract context gaps across one or many runs.** Pulls every caveat, data gap, integrity risk, and unanswered hypothesis the agents surfaced — useful for converting contextless test runs into a requirements list for the domain-context conversation with the business:

```bash
# Single run
uv run python -m src.tools.extract_context_gaps --run-id 20260520T223548Z-89dba6ec

# Aggregate across all runs in runs/
uv run python -m src.tools.extract_context_gaps --aggregate
```

**Synthesize across multiple per-function runs.** Identify cross-functional connections (e.g., *"sales execution gap on SKU-7 caused by supply tightness"*) and notable non-connections across separately-validated runs. The Synthesizer never invents findings — it only connects already-validated ones, with confounding analysis and causation calibration. Strongest differentiator vs. Microsoft Fabric Agents / Snowflake Cortex Agents (which run per-function but do not validate cross-functional synthesis):

```bash
# Synthesize across explicit run IDs (typical: one run per business function)
uv run python -m src.tools.synthesize_runs --run-ids sales-run-id,supply-run-id,trade-run-id

# Or use a glob over runs/
uv run python -m src.tools.synthesize_runs --runs-glob "20260530T*"
```

Outputs `output/synthesis-<ts>.md` (or `-pending-review.md` if the HITL gate fires) plus a structured artifact at `runs/synthesis-<ts>/artifacts/`. Synthesis findings flow through the same `hitl_review_threshold` gate as per-function runs.

#### Where missing-context findings surface (and how to use them)

The system flags context gaps in three places — same data, three audiences:

1. **In the rendered recipient markdown** ([docs/examples/smoke-test-output.md](docs/examples/smoke-test-output.md) shows the format):
   - **Run-level caveats** at the top — e.g., *"No domain context document loaded; thresholds are inferred."*
   - **Per-card CAVEATS** — caveats specific to a finding (e.g., *"FTPR threshold of 88% is assumed industry standard; confirm with business."*)
   - **Descriptive summary's "Open data gaps" table** — prioritized list.
2. **In each agent's structured artifact** (`runs/<run_id>/artifacts/NN-<agent>.json`) — every payload has a `caveats[]` array with severity, text, and source. Findings Validator's artifact has `required_caveats` per finding.
3. **Aggregated across runs** via `extract_context_gaps --aggregate` — five categories: `caveat`, `guardrail-pairing`, `data-gap`, `hypothesis-rationale`, `integrity-risk`.

**Workflow for the domain-context conversation:** run the pipeline contextless against sanitized work-shaped data → run `extract_context_gaps --aggregate` → walk into the business meeting with a categorized list of *"here's what the agents couldn't determine without domain knowledge."* That output **is** the requirements document for the domain context doc — convert the high-priority gaps into the metric definitions, guardrail pairings, and threshold guidance that go into `context/domains/<domain>.md`.

#### Submitting a variant when output validation fails

When a downstream user's run fails schema validation (a stage's artifact won't parse), the framework needs the raw LLM output and a sanitized version of the input that produced it to add a normalizer + regression test. Workflow:

1. **Capture the failed artifact.** It's already saved at `runs/<run_id>/artifacts/NN-<agent>.json` (or `replay-failed-payload.json` if the replay tool was used).
2. **Sanitize.** Replace any work-specific column names, business terms, customer/account IDs, or domain values with generic placeholders.
3. **Identify the variant.** Find the field where the LLM emitted a non-canonical shape (e.g., `detail` instead of `text`, a verbose string instead of a Literal value, a dict where a list was expected).
4. **Submit upstream.** Paste the sanitized variant JSON + which field is non-canonical. The framework maintainer adds a normalizer in [src/orchestrator/schemas.py](src/orchestrator/schemas.py) and a regression test in [tests/test_artifact_schemas.py](tests/test_artifact_schemas.py) pinning the variant input → canonical output. Variants don't regress; the corpus grows.

Existing variant tests at the bottom of `tests/test_artifact_schemas.py` are templates — copy one and substitute.

### Running tests

```bash
uv run pytest        # or: pytest
uv run ruff check .  # lint
uv run mypy src tests # type check
```

Tests cover: prompt assembly, artifact schema validation, pipeline composition, and data loading + injection defense.

### A note on initial testing — contextless by design

The first runs are intentionally **contextless** — no `context/domains/<domain>.md` file is loaded. The orchestrator handles this permissively per [failure-recovery.md §6a](orchestration/failure-recovery.md): the pipeline runs, and the final output carries a high-severity caveat noting that no domain context was loaded. This is the requirements-gathering phase: contextless runs surface the gaps (via `extract_context_gaps --aggregate`) that become the requirements document for the business meeting where the domain context is defined. The `context/domains/<domain>.md` file is written *after* that meeting, not before it.

## A note on what the system says when it has nothing to say

When the Findings Validator passes forward zero findings worth surfacing, the Communication Agent renders a descriptive summary: what was examined, what baselines were checked, what would have constituted a finding, and that none was found. This is a complete and valid output. It is not a failure mode and it is not a fallback. It is the system doing its job — respecting the recipient's attention by not crying wolf.

If you contribute to this repository, hold that line in every file you write.
