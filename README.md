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

```bash
export ANTHROPIC_API_KEY=sk-ant-...
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

### Running tests

```bash
uv run pytest        # or: pytest
uv run ruff check .  # lint
uv run mypy src tests # type check
```

Tests cover: prompt assembly, artifact schema validation, pipeline composition, and data loading + injection defense.

### A note on initial testing — contextless by design

The first runs are intentionally **contextless** — no `context/domains/<domain>.md` file is loaded. The orchestrator handles this permissively per [failure-recovery.md §6a](orchestration/failure-recovery.md): the pipeline runs, and the final output carries a high-severity caveat noting that no domain context was loaded. This lets the team observe how the agents handle raw sources before the domain context documents land (late next week / the following week).

## A note on what the system says when it has nothing to say

When the Findings Validator passes forward zero findings worth surfacing, the Communication Agent renders a descriptive summary: what was examined, what baselines were checked, what would have constituted a finding, and that none was found. This is a complete and valid output. It is not a failure mode and it is not a fallback. It is the system doing its job — respecting the recipient's attention by not crying wolf.

If you contribute to this repository, hold that line in every file you write.
