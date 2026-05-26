# Walkthrough — Narrating the Framework to Technical Leaders

**Use this when:** you're walking a technical audience through the framework and don't want to fumble through folder navigation. Each step opens one specific file. The folder structure stays invisible unless someone asks.

**Audience:** technical leaders, BI partners, peer engineers, data scientists. Not for the CEO demo — see [architecture.md](architecture.md) for the executive framing.

---

## 30-second pitch (use in hallway conversations)

> *"It's a multi-agent system that applies senior-data-analyst-level rigor to data nobody has time to manually examine. Every numeric claim is independently re-computed before it can ship; every finding is graded A through F; uncertain findings get filtered or downgraded with required caveats. It sits on top of Cortex Analyst — Cortex does the governed SQL, this framework does the validation, the synthesis across functions, and the calibrated output. Fabric Agents and Cortex Agents stop at 'we ran the query.' This goes the next mile to 'we validated the answer.'"*

---

## The 20-minute walkthrough

### Step 1 · Framing (30 seconds)

**Open:** nothing yet — just talk.

**Say:**
> *"Two things to know before we look at any code. First, this is a discipline layer, not an insight machine. The product is rigor and intellectual honesty applied repeatedly — sometimes that produces an actionable finding, sometimes it produces 'nothing concerning this week, here is a descriptive summary.' Both are valid outputs. Second, the framework is data-agnostic — it doesn't know whether the data came from CSV or from Cortex. It sits above the data layer."*

---

### Step 2 · The architecture diagram (3 minutes)

**Open:** [docs/architecture.md](architecture.md) — on GitHub, the Mermaid diagrams render inline.

**Walk top-down:**
1. **Business audiences** (top of diagram) — three layers: Account Managers (per-territory daily), Functional Leaders (weekly synthesis), Executives (org-wide strategic).
2. **The framework** (middle) — 11 agents, ordered. Point at the parallel block (Relationship/Pattern/Time Series) and the Synthesizer (standalone).
3. **The data layer** (below) — Cortex Agents → Cortex Analyst → Semantic Model → Snowflake. This is the **production path**; today we use CSV for demo / scaffolding.
4. **LLM providers** (bottom) — Anthropic primary; OpenAI + Gemini swappable via LiteLLM for A/B testing.

**Say:**
> *"The architectural value: each layer swaps independently. Phase D1 swaps in Snowflake. Phase D2 adds Cortex Analyst. Phase D3 adds Cortex Agents. The framework above doesn't change. Same for providers — Anthropic primary, but if OpenAI proves better on some agent, it's a config change, not a code change."*

**If asked "why not just use Cortex Agents alone":** Open the *"What this framework adds that Fabric Agents / Cortex Agents do NOT"* table further down in the same file. Read the rows aloud — that's the moat.

---

### Step 3 · The 11 agents — what each does (5 minutes)

**Open:** the [agents/](../agents/) folder, just to show the file list. Don't click anything yet.

**Narrate the pipeline order:**
1. **question-framer** — classifies the request, generates testable hypotheses, decides which downstream agents to run
2. **data-retrieval-agent** — loads the dataset slice (CSV today; Cortex tomorrow)
3. **data-profiler** — assesses quality, distribution shape, freshness, grain
4. **relationship-analyzer / pattern-discoverer / time-series-analyzer** *(parallel)* — apply the appropriate statistical techniques
5. **root-cause-investigator** — explains why specific deviations occurred
6. **opportunity-identifier** — translates findings into forward-tense actions
7. **findings-validator** — *the centerpiece* — independently re-computes every claim, grades A-F, filters D and F
8. **communication-agent** — renders the recipient output (action cards or descriptive summary)
9. **synthesizer-agent** *(standalone)* — runs across multiple per-function runs for cross-functional insights

**Then open one agent — pick [agents/findings-validator.md](../agents/findings-validator.md)** to show the depth of definition.

**Say:**
> *"Each agent is a markdown file with role, position in the pipeline, the skills it loads, its inputs, its responsibilities in order, what it does NOT do, and anti-patterns. The validator is the most important one — it independently re-executes every upstream finding and grades it. If the re-computation can't reproduce the upstream value within 1%, the finding gets grade F and is filtered. There's no override flag. Recipients never see an unvalidated claim."*

**If asked "what stops the validator from hallucinating its re-computation":** *"It executes code in a sandbox; the results are real. It can fail (we have a degraded path for that), but it can't fabricate. That's why we use code execution — compute, don't reason."*

---

### Step 4 · The skill library (3 minutes)

**Open:** [skills/universal/](../skills/universal/) — show 9 markdown files.

**Say:**
> *"Skills are the methodology — how each agent does its job. There are about 33 of them across four categories: universal (loaded with every agent — discipline that applies everywhere), analytical (techniques), validation (the validator's playbook), output (how the communication agent renders). Each API call assembles agent + relevant skills + universal skills + domain context."*

**Open one skill in depth:** [skills/universal/statistical-rigor.md](../skills/universal/statistical-rigor.md).

**Highlight:**
- Section 1: "Compute, don't reason" — every numeric claim must come from code execution
- Section 2: "Full statistical picture" — sample size + effect size + CI + p-value required, structurally enforced
- Section 4: Multiple-comparison correction as default (BH-FDR q=0.10)
- Section 5: Causation-vs-correlation language gate

**Say:**
> *"This is the kind of discipline a senior data scientist would insist on but most LLM-data tools punt on. It's not aspirational; it's structurally enforced — group-comparison statistics without effect size literally won't validate."*

---

### Step 5 · The actual output (5 minutes — the most important step)

**Open:** [output/20260520T223548Z-89dba6ec-replay-v2-exec.md](../output/20260520T223548Z-89dba6ec-replay-v2-exec.md)

This is a real execution output from May 20 — exec-ready, multi-section, with calibrated language.

**Walk top to bottom:**
1. **TL;DR** — three bullets, each with confidence grade — what an executive reads in 15 seconds
2. **Run-level caveats** — high-severity callouts, including "no domain context loaded" (because this was a contextless run)
3. **Action cards** — each with ALERT / CONFIDENCE / WHY THIS MATTERS / ROOT CAUSE / RECOMMENDED ACTION / OWNER / DUE / FOLLOW-UP TRIGGER / CAVEATS / SOURCE
4. **Mermaid charts inline** — rendered natively on GitHub / Obsidian
5. **Weekly summary section** — covers stable areas not in the cards; "what would have constituted a finding" — calibrates the all-clear
6. **Methodology footer in `<details>`** — statistical methodology hidden by default; expandable for analysts

**Say:**
> *"This is what a recipient sees. The cards aren't templated boilerplate — every field is calibrated to the validator's grade. Grade A reads directly; Grade C reads as preliminary. Causal language is gated by an explicit flag the investigator sets. The summary is a first-class output: when nothing rises to action, the system says so and shows what it was looking for."*

**If asked about cost/latency:** *"A full run is ~$10-15 on Anthropic and 15-30 minutes wall-time. The Synthesizer adds another ~$5 per cross-functional pass."*

---

### Step 6 · Live dry-run for impact (1 minute)

**Run in terminal:**
```bash
uv run python -m src.main --question "smoke test" --data data/sample/smoke-test.csv --dry-run
```

This takes ~30 seconds and is free (zero API calls). It assembles the prompts for all 11 agents, validates schemas, writes a report. Output goes to `output/dry-run-<id>.md`.

**Say:**
> *"What you're seeing is the framework loading the universal skills, the per-agent definitions, the analytical skills per stage, and assembling the system prompts. The 'plumbing verification' line confirms every agent's schema dispatch works. In a real run, this would precede actual API calls."*

---

### Step 7 · The Cortex + multi-LLM story (3 minutes)

**Back to:** [docs/architecture.md](architecture.md) — scroll to the *Production deployment phases* table.

**Walk the phases:**
- **MVP demo (now):** CSV on disk; Anthropic primary
- **Phase D1:** Direct Snowflake connector (scaffolded; activates when credentials arrive in a few weeks)
- **Phase D2:** Cortex Analyst + semantic model (scaffolded; BI + business own the semantic model)
- **Phase D3:** Cortex Agents for multi-step workflows
- **Phase 2:** Delivery layer, production observability

**Then show:** [context/semantic_models/walmart_in_store_execution.example.yaml](../context/semantic_models/walmart_in_store_execution.example.yaml)

**Say:**
> *"This is the YAML the BI team and business stakeholders will author per domain. It defines tables, measures, guardrail metric pairings, business thresholds, known data quirks. Once authored and reviewed, Cortex Analyst uses this as the governed semantic layer. We don't write SQL — Cortex generates it from the analytical question against this model. That's the value of Cortex; we sit on top of it."*

---

## If someone asks X — quick answers

| Question | Quick answer |
|---|---|
| *"How is this different from Microsoft Fabric Agents?"* | Fabric does the data + query layer. This adds the validation, confidence grading, causation gating, and cross-functional synthesis on top. We use Cortex as the data layer for our deployment. |
| *"What's the cost per run?"* | ~$10-15 on Anthropic (prompt caching is a 5-10× savings vs. OpenAI). Hard cap configurable; default $25/run. |
| *"How long does a run take?"* | 15-30 min wall-time. Parallel analytical agents save ~6-8 min. |
| *"Can you swap LLMs?"* | Yes — provider-agnostic abstraction. Config-driven per-agent provider selection. Anthropic primary for production economics. |
| *"How do you validate the validator?"* | Validator does independent re-computation via code execution — it runs fresh code on the data, doesn't reason. HITL gate available for high-stakes findings (grade A) for additional human oversight. Second-validator LLM cross-check deferred to Phase 2. |
| *"What about data security?"* | Free-text columns sanitized for prompt injection at load. Code execution happens in Anthropic's sandbox. Production: governed data access via Snowflake RBAC + Cortex semantic model. |
| *"Can it handle multiple data sources?"* | Today: one wide dataset per run (ETL upstream). With Cortex Agents (Phase D3): native multi-source via temporal-range joins. Cross-functional findings happen via the Synthesizer running over per-function runs. |
| *"How do you handle prompt injection in free text?"* | `src/data_access/injection_defense.py` detects and redacts injection patterns at load time. Free-text columns are treated as data, never as instructions. |
| *"What if a stage fails?"* | Failure-recovery spec implemented: schema-failure → retry once; non-critical agent failure → skip-and-flag with caveat; critical agent failure → hard-fail with operator report. Cost-cap exceeded → abort cleanly. |
| *"How do you prevent hallucinated statistics?"* | Two layers: (1) the "compute-before-reasoning" rule in universal skills says every numeric claim must come from code execution; (2) the Findings Validator independently re-executes everything. A statistic without `lineage.code_ref` won't validate. |
| *"Where's the code for the orchestrator?"* | `src/orchestrator/pipeline_executor.py` — ~600 LOC. Parallel groups handled via `_execute_stage_group`. Failure-recovery branches at lines around 178-220. |
| *"How does Anthropic prompt caching save 5-10× cost?"* | Universal skills (~50K tokens) load with every agent call. Anthropic charges 10% of normal input rate for cache reads. With 10 agents per run, 9 of them hit cache → ~90% savings on that block. Other providers don't have this. |
| *"How would I run this against real data tomorrow?"* | Today, replace `data/sample/smoke-test.csv` with your CSV. Future: configure Snowflake credentials (AKV pattern), set the semantic model name, point at Cortex Analyst. Framework code doesn't change. |
| *"What's the testing situation?"* | 94 tests; mock-SDK integration tests for orchestrator (retry, hard-fail, budget-cap, parallel); regression tests for schema normalizers. `uv run pytest` runs in ~2 seconds. |

---

## Anti-patterns when presenting

- **Don't open the folder tree and start narrating directories.** You'll get lost. Open specific files via the walkthrough.
- **Don't try to explain all 11 agents in detail.** Show one in depth (validator), reference the others by name.
- **Don't lead with the LLM provider abstraction or the testing infrastructure.** Those are technical-engineer questions; they're answers to questions, not opening lines.
- **Don't apologize for what's not built.** The data layer is scaffolded, not built — that's a deployment phase, not a gap. Frame as roadmap, not as gap.
- **Don't get drawn into a feature-by-feature comparison with Fabric / Cortex on capabilities they're better at.** Stay on the discipline-layer differentiator.

---

## Closing line

> *"Bottom line: this framework is the analytical discipline that turns governed data into validated business decisions. We're 9 days from a CEO demo of one functional area (Walmart In-Store Execution) running end-to-end with calibrated output. Production deployment with Cortex follows shortly after, with the semantic model authored by BI + business in parallel. The work going forward is mostly on the data and integration layer, not the framework — that part is solid."*
