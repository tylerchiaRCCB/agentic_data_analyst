# Quick Reference — The 8 Files That Matter

**For:** the project lead (you). When you need to find something fast or open the right file in a meeting without scrolling through the folder tree.

This is intentionally narrow — *only the 8 files that come up repeatedly*. The repo has 100+ markdowns and 60+ Python files; most of them are infrastructure you don't need to open unless something breaks.

---

## The 8 essential files

### 1. [docs/architecture.md](architecture.md) — the diagram
**Open when:** anyone asks "what is this" or "how does it fit with our existing stack."
**Why:** Mermaid diagrams render inline on GitHub. Three of them: layered architecture, multi-provider dispatch, hierarchical synthesis. Plus the capability comparison table vs. Fabric/Cortex.
**Highlight section:** "Why this is the right architecture" → three-layer separation table.

### 2. [docs/walkthrough.md](walkthrough.md) — your presenter script
**Open when:** you're about to walk someone through the framework live.
**Why:** linear 7-step tour with file paths, talking points, and answers to common questions. Removes the folder-navigation problem.
**Highlight section:** "30-second pitch" at the top for hallway encounters.

### 3. [agents/findings-validator.md](../agents/findings-validator.md) — the rigor centerpiece
**Open when:** someone asks how the validation works, why this is more rigorous than Cortex Agents, or what makes the system trustworthy.
**Why:** this is the agent that does independent re-computation. The non-bypassable A-F grading. The whole trust model lives here.
**Highlight:** "Responsibilities in order" — layers 1 through 4 of the validation.

### 4. [skills/universal/statistical-rigor.md](../skills/universal/statistical-rigor.md) — the discipline centerpiece
**Open when:** someone asks how rigorous the statistics actually are, or what stops the LLM from hallucinating numbers.
**Why:** the compute-before-reasoning rule lives here. Effect-size + CI requirements. Multiple-comparison correction defaults. Causation language gate.
**Highlight:** Section 2 "Report the full statistical picture" — now structurally enforced, not aspirational.

### 5. [output/20260520T223548Z-89dba6ec-replay-v2-exec.md](../output/20260520T223548Z-89dba6ec-replay-v2-exec.md) — a real execution output
**Open when:** someone asks "what does the output look like" or "show me an example."
**Why:** this is the canonical exec-ready output from May 20. TL;DR, action cards, descriptive summary, inline Mermaid charts, audit-trail `<details>`. The thing a recipient gets.
**Highlight:** TL;DR at the top + one action card + the "what would have constituted a finding" section in the summary.

### 6. [context/semantic_models/walmart_in_store_execution.example.yaml](../context/semantic_models/walmart_in_store_execution.example.yaml) — the Cortex semantic model
**Open when:** someone asks how this connects to Cortex / Snowflake.
**Why:** this is the YAML BI + business will author per domain. Defines tables, measures, guardrail pairings, thresholds, stakeholder map. The governed layer Cortex Analyst operates against.
**Highlight:** the `guardrail_metric_pairings` and `thresholds` sections — domain knowledge baked into the contract.

### 7. [config/pipeline_config.yaml](../config/pipeline_config.yaml) — the operational dials
**Open when:** someone asks about model selection, cost cap, HITL threshold, or "what can we tune without code changes."
**Why:** model per agent, cost ceiling, retry behavior, HITL review threshold, soft-warning thresholds — all config, not code.
**Highlight:** `model_per_agent` (provider-prefixed model IDs supported) + `max_cost_usd` + `hitl_review_threshold`.

### 8. [README.md](../README.md) — for someone running the tool
**Open when:** an engineer asks "how do I install / run this" — not for explaining the framework conceptually.
**Why:** install instructions, dry-run command, real-run command, tests command. This is the operational onboarding doc.
**Highlight:** "Quickstart" → "First real run" → "Tools".

---

## Files NOT to open in meetings (until specifically asked)

| File | Why not |
|---|---|
| `mvp_plan.md` | 1100+ lines of spec — too long for a meeting; reference document |
| `src/orchestrator/pipeline_executor.py` | Implementation; only relevant for code review |
| `src/orchestrator/schemas.py` | Implementation; 1100+ lines |
| Any test file in `tests/` | Only relevant if someone asks about test coverage |
| `orchestration/failure-recovery.md` | Detailed spec; rarely needed live |
| `mvp_plan.md` | (reiterated — really don't open this in meetings) |
| Anything in `runs/<run_id>/artifacts/` | Audit trail; only open if someone wants to see the raw data flow |

---

## Commands worth memorizing

| Purpose | Command | Cost | Time |
|---|---|---|---|
| Run all tests | `uv run pytest -q` | $0 | 2 seconds |
| Dry-run (plumbing check) | `uv run python -m src.main --question "..." --data <csv> --dry-run` | $0 | 30 sec |
| Real run | `uv run python -m src.main --question "..." --data <csv>` | $10-15 | 15-30 min |
| Replay just the comm-agent | `uv run python -m src.tools.replay_comms --run-id <id>` | ~$0.30 | 30 sec |
| Synthesize across runs | `uv run python -m src.tools.synthesize_runs --run-ids r1,r2,r3` | ~$5-10 | 1-3 min |
| Extract context gaps | `uv run python -m src.tools.extract_context_gaps --aggregate` | $0 | instant |
| Generate the smoke-test CSV | `uv run python -m data.generators.generate_smoke_test` | $0 | 5 sec |

---

## Where outputs go (so you know what to look at)

| Output | Path | Created by |
|---|---|---|
| Recipient markdown (normal run) | `output/<run_id>.md` | the run, via Communication Agent |
| Recipient markdown (HITL gated) | `output/<run_id>-pending-review.md` | the HITL gate when threshold fires |
| Review prompt (companion to above) | `output/<run_id>-review-prompt.md` | the HITL gate |
| Dry-run report | `output/dry-run-<id>.md` | dry-run mode |
| Replay output | `output/<run_id>-replay.md` | replay tool |
| Synthesis output | `output/synthesis-<ts>.md` | synthesize_runs tool |
| Per-stage artifacts | `runs/<run_id>/artifacts/NN-<agent>.json` | every run |
| Structured logs | `runs/<run_id>/run.jsonl` | every run |
| Span trace | `runs/<run_id>/spans.jsonl` | every run |
| Lineage manifest | `runs/<run_id>/lineage.json` | every run |
| Hard-failure report | `runs/<run_id>/<run_id>-failure.md` | only on critical agent failure |

**Each run is fully isolated.** Run IDs are timestamp + UUID, so nothing collides across runs. You can have hundreds of runs side-by-side in `output/` and `runs/` without conflict.

---

## If you forget what something does

- **Agent definitions:** `agents/<name>.md` — opening one tells you that agent's full role, inputs, responsibilities, anti-patterns
- **Skill definitions:** `skills/<category>/<name>.md` — opening one tells you the methodology
- **Architecture decisions:** `docs/architecture.md`
- **Why we built it this way:** `mvp_plan.md` (long; use grep)
- **How an old run actually went:** `runs/<run_id>/artifacts/` — every stage's payload, JSON, indented
- **Errors / failures:** `runs/<run_id>/run.jsonl` filtered to `level=ERROR`

---

## Critical mental model

You're presenting **a discipline layer**, not a data tool, not a query tool, not a BI dashboard. The three things that make it valuable are:

1. **Independent validation** — the validator re-executes claims; D and F never ship
2. **Calibrated language** — A/B/C grades drive register; causation gate enforced mechanically
3. **Null-result-as-output** — "nothing concerning this week" is a valid, valuable output

If you anchor every conversation to those three, you stay on the differentiator. Everything else — Cortex integration, multi-provider, parallel execution, HITL gate — is supporting infrastructure that lets those three work in production.
