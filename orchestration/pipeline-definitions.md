# Pipeline Definitions

Composition rules, skip logic, and parallelism model for the agentic data analyst orchestration engine.

> **Framing reminder.** The orchestrator never decides what conclusions a pipeline reaches. It composes agents, enforces contracts, and surfaces honest output — including the "no findings rose to action" output. Skip rules and degradation behaviors below all preserve that discipline. See [framing-rigor-not-insights](../mvp_plan.md#core-framing-read-first).

---

## 1. The DAG model

The pipeline is a directed acyclic graph. Nodes are agents. Edges are typed artifact dependencies — an edge from `A → B` means agent `B` consumes the JSON artifact produced by agent `A` (see [artifact-schemas.md](artifact-schemas.md)).

The graph is **composed at runtime** by the Question Framer. The orchestrator does not run a fixed sequence; it reads `pipeline_composition` from the framer's brief and executes the specified stages in the specified order with the specified skills loaded.

### Position invariants

Some agents have fixed positions in any pipeline they appear in:

| Agent | Position constraint |
|---|---|
| Question Framer | **Always first.** Produces the brief that drives composition. |
| Data Retrieval Agent | **Always second when data is needed.** Bears the data-access security boundary. No other agent loads data directly. |
| Data Profiler | **Always third when any analytical work follows.** Required for any pipeline that makes analytical claims. Quality assessment is the foundation. |
| Findings Validator | **Always second-to-last when present.** Validation must run on the full set of analytical claims, immediately before output. |
| Communication Agent | **Always last.** Sole renderer of recipient-facing output. |

The middle layer — Relationship Analyzer, Pattern Discoverer, Time Series Analyzer, Root Cause Investigator, Opportunity Identifier — is variable. The Question Framer composes from these based on the question's analytical shape.

### Edges and shared inputs

Every middle-layer agent depends on the Data Profiler artifact at minimum. Diagnostic and prescriptive agents (Root Cause Investigator, Opportunity Identifier) additionally depend on whichever analytical agents ran upstream. Concretely:

- `Relationship Analyzer ← Data Profiler`
- `Pattern Discoverer ← Data Profiler`
- `Time Series Analyzer ← Data Profiler`
- `Root Cause Investigator ← Data Profiler + {whichever of Relationship Analyzer, Pattern Discoverer, Time Series Analyzer ran}`
- `Opportunity Identifier ← Data Profiler + Root Cause Investigator (if ran) + Pattern Discoverer (if ran)`
- `Findings Validator ← all upstream analytical agents + Data Retrieval (original data, for independent recomputation)`
- `Communication Agent ← Findings Validator (or all upstream artifacts if Validator was skipped — see §3)`

These are dependency edges, not execution order. Execution order is the linear sequence in `pipeline_composition`. Parallelism within the sequence is described in §5.

---

## 2. Canonical pipeline compositions

These are the reference compositions per complexity level. The Question Framer should compose toward one of these shapes unless a question genuinely demands deviation; novel compositions are allowed but should be the exception, not the default.

### L1 — Simple lookup
*Example: "Top 5 DCs by sales volume last week."*

```
Question Framer → Data Retrieval → Data Profiler (minimal) → Communication Agent
```

- 4 agents.
- No analytical claims requiring validation — the Communication Agent renders a direct factual summary.
- Findings Validator **skipped**: there are no derived findings to validate, only retrieved values. (See §3 for the skip rule.)
- Output mode: `narrative` (deferred in MVP; for MVP, L1 questions are out of scope — proactive monitoring is the demo).

### L2 — Descriptive comparison
*Example: "How did weekly sales trend over the past 6 months?"*

```
Question Framer → Data Retrieval → Data Profiler → Time Series Analyzer → Communication Agent
```

- 5 agents.
- The Time Series Analyzer produces descriptive characterizations (decomposition, change points) but no causal or prescriptive claims.
- Findings Validator **may be skipped** if no claims rise above descriptive characterization. The Communication Agent renders a descriptive summary directly. If the analytical agent surfaces a candidate anomaly worth validating, the Question Framer should compose L3 instead.

### L3 — Diagnostic investigation
*Example: "Why did Southeast volume decline last week?"*

```
Question Framer → Data Retrieval → Data Profiler → Relationship Analyzer → Time Series Analyzer →
  Root Cause Investigator → Findings Validator → Communication Agent
```

- 8 agents.
- Findings Validator **required.** Diagnostic claims are causal-adjacent and must be independently recomputed.

### L4 — Opportunity identification
*Example: "What are 5 opportunities to help bottom-quartile DCs improve?"*

```
Question Framer → Data Retrieval → Data Profiler → Pattern Discoverer → Relationship Analyzer →
  Root Cause Investigator → Opportunity Identifier → Findings Validator → Communication Agent
```

- 9 agents.
- Full diagnostic + prescriptive pipeline.

### Proactive monitoring (the MVP demo)

```
Question Framer (interprets scheduled prompt + generates hypotheses) →
  Data Retrieval → Data Profiler → Pattern Discoverer →
  [parallel: Relationship Analyzer, Time Series Analyzer] →
  [parallel-per-pattern: Root Cause Investigator] →
  Opportunity Identifier → Findings Validator → Communication Agent (action-card mode)
```

- Full pipeline.
- Pattern Discoverer generates candidate areas for investigation; downstream agents fan out (see §5).
- The Communication Agent renders one or more action cards **and/or** a descriptive summary. **A run that produces zero action cards is a valid run**, not a failure — see §6.

---

## 3. Skip rules

The Question Framer is allowed to skip middle-layer agents whose work the question does not require. Skip eligibility:

| Agent | Skippable? | Rule |
|---|---|---|
| Question Framer | No | Always runs. |
| Data Retrieval | Only if no data is needed (no current case in MVP). | — |
| Data Profiler | No when any analytical agent follows. | Always runs in any pipeline that makes a quantitative claim. |
| Relationship Analyzer | Yes | Skip if the question does not involve how variables relate. |
| Pattern Discoverer | Yes | Skip unless the question involves discovery/segmentation, or in proactive mode where it is required. |
| Time Series Analyzer | Yes | Skip if data has no temporal dimension or question is non-temporal. |
| Root Cause Investigator | Yes | Skip if the pipeline is purely descriptive or purely discovery-oriented (no "why" question to answer). |
| Opportunity Identifier | Yes | Skip if the question is diagnostic-only or descriptive-only. |
| Findings Validator | Yes, but narrowly. | Skip **only** when the Communication Agent will render purely retrieved values or purely descriptive characterizations (no derived claims). Any pipeline including Root Cause Investigator or Opportunity Identifier **must** include Findings Validator. When in doubt, include it. |
| Communication Agent | No | Always runs. Renders descriptive summary if there is nothing else to render. |

The Question Framer encodes its decisions in the `pipeline_composition` array. The orchestrator does not re-derive skip choices.

### When the Validator is skipped — and how the output should read

The Validator is skipped only when the pipeline makes **no derived analytical claims** — i.e., it returns retrieved or directly-summarized values. The recipient's experience in that case should not feel like consuming a degraded result; it should feel like getting a plain factual answer.

Two distinct cases must be kept apart:

| Case | What the Communication Agent renders |
|---|---|
| **L1 lookup, Validator intentionally skipped** *("Top 5 DCs by sales volume last week")* | The factual result, with a **source line** rather than a validation caveat: *"Source: weekly sales extract, run 2026-05-17. Values retrieved and summarized; no derived analytical claims made."* Do **not** prefix or footer the output with "unvalidated" — there was nothing to validate. The output reads as a clean lookup. |
| **L2 descriptive characterization, Validator intentionally skipped** *("How did weekly sales trend over the past 6 months?")* | The descriptive output, with a **methodology footer** rather than an alarming caveat: *"This is a descriptive characterization; figures sourced from direct computation. Independent claim re-validation not performed."* Tone is informative, not warning. |
| **Validator was required by the pipeline but failed at runtime** | The strong caveat applies — see [failure-recovery.md](failure-recovery.md) §6.1. All claims are capped at grade C and the output explicitly states that independent validation could not be performed. This is the alarming case; it should read differently. |

The first two are normal operating modes. The third is a degradation. They must not look the same in the recipient-facing output.

There is still no path to a **high-confidence analytical claim** without the Validator. Lookups and descriptive characterizations are not analytical claims; they are factual reporting.

---

## 4. Prompt assembly per stage

Every agent call assembles its system prompt from four sources, concatenated in this order:

1. **Universal skills** — all files in `skills/universal/`, always loaded. These set the rigor floor.
2. **Agent definition** — `agents/<agent-name>.md`.
3. **Per-stage skills** — the `skills` array on the `pipeline_composition` entry. The orchestrator resolves these against `skills/analytical/`, `skills/validation/`, `skills/output/`, and `skills/domain-specific/`.
4. **Domain context** — the relevant document from `context/domains/` (or `context/examples/` in MVP), resolved from `framer_brief.data_requirements.domain`.

The orchestrator is responsible for loading and concatenating; agents do not load files themselves.

- **Missing skill file** — the orchestrator fails the stage rather than silently dropping it. See [failure-recovery.md](failure-recovery.md) §4.
- **Missing domain context file** — MVP behavior is permissive: the orchestrator proceeds with universal + analytical skills only and adds a high-severity caveat to the run that propagates into the recipient-facing output. There is a hardening TODO to convert this into a configurable hard gate before production. See [failure-recovery.md](failure-recovery.md) §6a.

The user-message portion of each call carries the upstream artifacts the agent depends on, JSON-serialized, plus any stage-specific instructions from the Question Framer. Crucially, the user message contains **computed summaries** from upstream agents — never raw rows from the dataset. See §10 for the context-discipline rules that govern this.

---

## 5. Parallelism

Two forms of parallelism are supported.

### 5.1 Sibling analytical agents

When the Question Framer composes multiple middle-layer agents that share the same dependencies (e.g., Relationship Analyzer and Time Series Analyzer both depend only on the Profiler), the orchestrator may execute them in parallel. The `pipeline_composition` array supports a nested-array form for parallel groups:

```json
"pipeline_composition": [
  {"agent": "data-retrieval", "skills": []},
  {"agent": "data-profiler", "skills": [...]},
  [
    {"agent": "relationship-analyzer", "skills": [...]},
    {"agent": "time-series-analyzer", "skills": [...]}
  ],
  {"agent": "root-cause-investigator", "skills": [...]},
  ...
]
```

Parallel-group entries must share dependencies upstream. The orchestrator joins them before passing artifacts to the next stage.

### 5.2 Fan-out within an agent

In proactive monitoring, the Root Cause Investigator may run once per candidate pattern surfaced by the Pattern Discoverer. The orchestrator handles this as a fan-out: same agent, parallel invocations, each with a different focal pattern in its user message. The orchestrator joins the resulting artifacts into a list under `root_cause_investigator` in the artifact bag.

The Findings Validator then validates each diagnostic claim individually, but runs as a single invocation receiving the joined list (so it can also check cross-cutting issues).

### 5.3 Parallelism limits

- Max parallel concurrency is set in `config/pipeline_config.yaml`. Default for MVP: 3.
- Code execution sessions are not shared across parallel agent calls — each gets its own sandbox.
- Token budget telemetry sums across parallel calls (no double-counting).

---

## 6. The empty-findings path

A pipeline producing zero high-confidence findings is a valid pipeline. The orchestrator must not retry, escalate, or alter composition to "find something."

Specifically:

- If the Pattern Discoverer surfaces no candidates worth investigating, the pipeline skips Root Cause Investigator and goes directly from Pattern Discoverer → Opportunity Identifier (which may also conclude no opportunities) → Findings Validator → Communication Agent.
- If the Findings Validator passes forward zero findings, the Communication Agent renders a **descriptive summary** documenting what was examined, what baselines were checked, and that nothing rose to action this period.
- The Communication Agent's descriptive-summary output is a first-class output. It is not a fallback, not a default, and not a degraded mode.
- The orchestrator's run-status field is `success` in this case, not `empty` or `degraded`.

Any future addition to skip logic that would change this behavior is a regression. Reviewers: flag it.

---

## 7. Output mode selection

The Question Framer's `output_mode` field drives the Communication Agent's behavior:

| `output_mode` | Communication Agent behavior | MVP scope |
|---|---|---|
| `action-card` | Renders one action card per validated finding worth surfacing. Renders a descriptive summary section at the end if any examined area produced no findings. | **In scope.** |
| `narrative` | BLUF-format prose response with supporting points and follow-up suggestions. | **Deferred to Phase 2.** |
| `descriptive-summary` | Renders a descriptive summary only — used when the Question Framer knows in advance the output will be descriptive (e.g., L2 trend reports). | **In scope.** |

For MVP, the Question Framer should always emit `action-card` for proactive monitoring runs. The Communication Agent decides per-finding whether to render a card or fold the area into the summary section based on Validator grades.

---

## 8. Token budget

The Question Framer sets `token_budget` in the brief based on complexity classification:

| Complexity | Default budget (tokens) | Notes |
|---|---|---|
| L1 | 50,000 | Lookup. |
| L2 | 150,000 | Descriptive. |
| L3 | 400,000 | Diagnostic. |
| L4 | 800,000 | Prescriptive / opportunity. |
| Proactive monitoring | 1,200,000 | Full pipeline with fan-out. |

The Budget Tracker monitors cumulative spend across all stages and parallel calls. MVP behavior: **telemetry only — no enforcement.** Production behavior: hard cap triggers graceful truncation (see [failure-recovery.md](failure-recovery.md) §5).

Per-agent model selection lives in `config/pipeline_config.yaml`. Default per the spec's Part 12 §1:
- Opus: Root Cause Investigator, Findings Validator, Opportunity Identifier
- Sonnet: Question Framer, Data Retrieval, Data Profiler, Communication Agent
- Middle analytical agents (Relationship, Pattern, Time Series): start on Sonnet, escalate to Opus per-stage if Week 1 testing shows quality gaps.

---

## 9. Lineage propagation

Every analytical claim must carry lineage metadata from the agent that produced it through to the Communication Agent. The orchestrator does not synthesize lineage — agents emit it, and the orchestrator preserves and aggregates it. See [artifact-schemas.md](artifact-schemas.md) §`Statistic`.

At pipeline completion, the orchestrator writes `lineage.json` containing every computed statistic that reached the final output, traceable to its source data, transformation, code, and producing agent.

---

## 10. Context discipline (raw data stays in the sandbox)

The single most important architectural rule for keeping context windows tractable is: **the LLM never sees the raw dataset.** Agents see schemas, column metadata, computed statistics, and small summary outputs. The dataset itself — whether it is 1,000 rows or 5 million — lives in the code execution sandbox and is referenced by `dataset_handle`, never by inline values.

This rule is what makes "1M rows" not blow up context. Token cost per agent call is dominated by skills + agent definition + domain context (collectively constant), plus upstream artifact summaries (small and bounded). Adding rows to the dataset adds zero tokens to the prompt; it adds work to the sandbox.

### What goes into an agent's context

- System prompt: universal skills + agent definition + on-demand skills + domain context (constant — does not scale with dataset).
- User message: upstream artifacts (computed summaries) + stage instructions.
- Tool definitions: code execution (and any agent-specific tools).

### What does NOT go into an agent's context

- Raw rows or row dumps from the dataset.
- Wide column samples included "for convenience."
- Inline lists of IDs, values, or records that the agent could otherwise reference by filter.
- Returned dataframes from code execution larger than a small summary table.

### Rules the orchestrator and agents enforce

1. **Data Retrieval Agent's artifact contains metadata, not values.** The schema captures columns, dtypes, null counts, distinct counts, and the row count — but no example values from the data itself. Sample-row inspection is available on demand via code execution against `dataset_handle`, not through the artifact. See [artifact-schemas.md](artifact-schemas.md) §4.2.

2. **Code execution returns summaries, not row dumps.** Agents request `df.groupby(...).agg(...)`, `df.describe()`, scalar values, and small (≤ ~50 rows) tables of *computed results*. Returning `df.head(1000)` or `print(df)` for a wide dataset is a violation. Agent skills (especially universal and analytical) instruct agents to request summaries.

3. **`Statistic.lineage.data_slice` is a filter expression, not inline data.** Acceptable: `region == "Southeast" and week >= "2026-01-01"`. Forbidden: a 12,000-element list of account IDs inlined into the field.

4. **Code execution output is bounded.** Each time an agent runs code in the sandbox, the orchestrator inspects the size of what would be returned to the agent's context window *before* passing it back to the model. If the output is under the configured cap (MVP default: 4,000 tokens), it returns verbatim. If it exceeds the cap, the orchestrator substitutes a short notice — *"Output exceeded the per-call cap. Truncated. Re-run with a summary, smaller sample, or aggregated query."* — and the model sees the notice instead of the bloated output. The agent then re-runs with a tighter query (e.g., `df.describe()` instead of `print(df)`, or `df.groupby('region')['volume'].median()` instead of returning the full grouped frame).

   **Why this matters:** a single `print(df)` on a 10,000-row, 50-column dataframe can produce 100K+ tokens of structured text. Without the cap, that output floods the context window for the rest of the agent call and — worse — encourages the model to reason about specific raw row values, defeating the "compute, don't reason" principle from [statistical-rigor.md](../skills/universal/statistical-rigor.md) §1. The cap is the **runtime safeguard** that backs up the prompt-level instructions in the skills.

   The 4,000-token default accommodates a generous summary table (~50 rows × 10 columns, or a long describe-style output) without permitting accidental row dumps. The cap is configurable per agent in `pipeline_config.yaml` — an agent with a legitimate need for larger summary tables can raise it; an agent that should be especially disciplined can lower it.

5. **Specific-record inspection is allowed when small and deliberate.** When the Root Cause Investigator wants to see the 12 accounts with the steepest declines, code execution returns those 12 rows and they enter the agent's context — fine. The rule is against incidental row dumps, not deliberate small samples.

### Sandbox persistence (MVP vs. production)

The spec does not mandate a single sandbox model. Two paths:

- **MVP** — fresh code execution session per agent call. The agent re-loads the demo file from disk. Demo dataset is small (~hundreds to low thousands of rows per the spec's 847-record demo), so reload cost is negligible.
- **Production scaling path** — two strategies, either or both:
  - *Persistent sandbox per pipeline run,* keyed by `dataset_handle`. The first agent loads the file; subsequent agents reuse the prepared session.
  - *Server-side computation via Cortex Analyst or pre-validated Snowflake views.* The agent emits SQL; the warehouse returns aggregates. Raw rows never leave the warehouse and the sandbox layer thins or disappears.

The MVP sandbox model is intentionally simple. The discipline rules above (1–5) are the load-bearing constraints; the persistence model can change without changing those rules.

### Data flow and trust boundary (MVP and production)

The context-discipline rules above govern what enters the *LLM context window*. This subsection covers the broader question: where does the **data itself** physically live and travel, who controls each hop, and what does the trust boundary look like in MVP vs. production. This is the conversation that needs to be ready for security review before any real company data flows through the system.

#### MVP — local + Anthropic-hosted code execution, synthetic data only

```
[Operator's machine]                [Anthropic-hosted infrastructure]
  ├─ demo CSV/Excel file            ├─ Code execution sandbox
  │  (synthetic, intentional        │  (per-call, ephemeral)
  │   anomalies — no real           ├─ Claude model API
  │   company data)                 └─ (no persistent storage of
  ├─ orchestrator (Python script)      uploaded data beyond the run)
  ├─ output reports
  └─ run logs / lineage.json
       │
       └─ API requests over HTTPS to Anthropic
            ├─ system prompts (universal skills + agent + domain context)
            ├─ user messages (computed summaries from upstream artifacts)
            ├─ tool calls (code execution requests)
            └─ uploaded dataset files (for code execution)
```

**What crosses the trust boundary (operator → Anthropic) in MVP:**
- The demo dataset file (synthetic by design — no real company data).
- Agent prompts containing schemas, metadata, and computed summary statistics.
- Code that agents write for execution against the dataset.

**What does NOT cross the trust boundary in MVP:**
- Any production company data (because the demo uses synthetic data).
- The final rendered reports (these are produced locally).
- Run logs and the `lineage.json` audit trail (these stay on the operator's machine).

**Why this is acceptable for MVP:** the demo dataset is generated synthetically with intentional anomalies (see `data/generators/generate_demo_data.py`). No real customer, vendor, employee, or transaction data is ever uploaded.

**What this is NOT acceptable for:** running the MVP pipeline against real company data. Anthropic's hosted code execution sandbox is appropriate for synthetic-data MVP work but is not the right boundary for production company data without contractual and tenancy controls — which is the production path.

#### Production — Azure AI Foundry + Snowflake / Cortex Analyst, real data

The spec's Part 7 ("Production Concerns Coverage") and Part 11 ("Path to Production") describe two production-grade changes that close the trust boundary properly. They are complementary, not alternatives:

**Path A — Azure AI Foundry replaces the Anthropic API direct call.**
- Claude models are served through your Azure tenancy via Azure AI Foundry.
- API traffic and any code execution run inside Microsoft's compliance perimeter under your enterprise agreement.
- Authentication uses Microsoft Entra ID SSO; per-user/per-domain budgets are enforceable.
- This addresses where the model runs and who has access — but does not by itself eliminate the question of where the data sits during execution.

**Path B — Cortex Analyst pushes computation into Snowflake.**
- The Data Retrieval Agent's MVP behavior (load a CSV into the sandbox) is replaced by an agent that emits SQL queries against pre-validated Snowflake views or hands questions to Cortex Analyst.
- Queries execute *inside Snowflake* under your existing row-level security and service-account controls.
- Snowflake returns aggregated query results — small summary tables — to the orchestration layer. Raw rows never leave the warehouse.
- The LLM only ever sees: the schema and column metadata, the queries it asked for, and the aggregated results.

**Combined, the production data flow looks like:**

```
[Azure-hosted backend]                [Snowflake / Cortex Analyst]
  ├─ orchestrator (Azure Web App      ├─ pre-validated views
  │  or Container App)                ├─ Cortex Analyst semantic layer
  ├─ Azure AI Foundry → Claude         ├─ row-level security
  ├─ scheduled trigger (Functions     ├─ service-account read-only access
  │  or Databricks)                   └─ raw rows STAY HERE
  ├─ output delivery (Email / Teams)
  ├─ persistent memory (Cosmos DB)
  └─ OpenTelemetry logs
       │
       └─ Queries (SQL or Cortex natural-language) to Snowflake
            ├─ Returns: aggregated result tables only
            └─ Never sees: row-level data
```

**What crosses the trust boundary in production:**
- *Within your Azure tenancy:* prompts, computed summaries, query results, rendered reports.
- *To Snowflake (your data warehouse):* queries authored by agents under read-only service-account credentials.
- *To Microsoft (Azure):* normal tenancy-scoped infrastructure usage; falls under your existing enterprise agreement.
- *To Anthropic in production:* nothing direct — model access is brokered through Azure AI Foundry.

**What does NOT cross any external boundary:**
- Raw row-level data. It stays in Snowflake under existing controls.
- Customer-/employee-/transaction-level records of any kind.
- Anything that would not normally be exposed through Snowflake's existing row-level security.

#### Trust-boundary invariants the architecture preserves across both paths

These hold in MVP and production:

1. **The agent system is read-only with respect to data.** No agent has write/update/delete capability against any data source. See Part 6 of the spec.
2. **Free-text columns are sanitized before any agent reads them.** See `src/data_access/injection_defense.py` and §10 rule #1 above for the prompt-injection defense.
3. **No agent loads data outside the Data Retrieval Agent.** Every data access is bounded to that single agent, which holds the security boundary.
4. **Code execution returns summaries, not row dumps.** §10 rules #2–#4 enforce this both via instructions and via the runtime cap.
5. **Lineage tracks every claim.** Every numeric claim ties back to the executed code, the data slice, and the producing agent — auditable end-to-end.

#### Operator checklist before running MVP against anything other than synthetic data

If at any point someone proposes pointing the MVP at a real-company-data file *before* the production migration is complete, the right answer is "no, that requires the production path." If a smaller-scoped real-data trial is needed for confidence-building, the choices are:

- Move to the Azure AI Foundry tenancy first, even before the Cortex path is built.
- Use a redacted / aggregated extract that is itself synthetic-equivalent.
- Treat the trial as a security exception, with explicit approval, scope, and revocation date.

The architecture does not need to change for any of these — the data-access layer does. That's by design: the MVP proves the analytical engine, and the production migration adds infrastructure without altering capability.

---

### Practical capacity (MVP)

For Anthropic-hosted code execution with the discipline above:

| Dataset size (rows × ~50 cols) | MVP sandbox feasibility | Notes |
|---|---|---|
| ≤ 100K | Comfortable | Demo and small production datasets. |
| 100K – 5M | Workable in polars | Reload cost noticeable; persistent sandbox beneficial. |
| 5M – 50M | Marginal | Persistent sandbox required; consider polars + parquet over CSV. |
| > 50M | Not viable in MVP | Push computation to Snowflake (Cortex path). |

The Data Retrieval Agent enforces a row-count threshold configured in `pipeline_config.yaml` (MVP default: 5M rows). Datasets exceeding the threshold are either auto-sampled with a high-severity caveat (sampling method recorded in the artifact) or rejected in favor of the Snowflake path.

---

## 11. What this document does not cover

- **Agent-internal logic.** How each agent decides which skills to invoke internally is in `agents/<agent-name>.md`, not here.
- **Skill methodology.** How a specific statistical test is performed is in the relevant skill file.
- **Failure handling.** Retry, degradation, and graceful-truncation rules are in [failure-recovery.md](failure-recovery.md).
- **Artifact field-level definitions.** JSON schemas live in [artifact-schemas.md](artifact-schemas.md).

This document defines composition: what runs, in what order, with what dependencies, under what skip rules.
