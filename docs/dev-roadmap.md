# Dev Roadmap — Future Enhancements

A running list of enhancements identified during development that haven't been
prioritized yet. Each item: what it is, why it matters, rough effort, and the
trigger that should pull it into scope.

Items are grouped by theme. Within each theme, ordered by likely impact.

---

## Interactive / chat experience

### Streaming Communication Agent output
The current pipeline returns the full markdown at the end of the comms-agent
call. For chat UX, the user should see tokens as they're generated.
- **Why it matters:** Sub-2-minute perceived response time even on multi-minute
  generations. UX feels alive vs. dead-pause-then-dump.
- **Effort:** ~0.5 day. The Anthropic SDK supports streaming via
  `client.beta.messages.stream(...)`. Add a streaming variant to `ClaudeClient`
  and a callback parameter to the executor.
- **Trigger:** When chat UI development starts (Phase 2).

### Quick-lookup fast path
Bypass the full pipeline for trivial questions (*"what were sales at Account 47
last week"*). Route directly to a single Cortex Analyst call or a Sonnet+code-
execution call with no framer/profiler/validator overhead.
- **Why it matters:** L1 lookups should return in 5–30 seconds, not 2–5 minutes.
- **Effort:** ~1 day. Adds a complexity-router agent at the very front (Haiku call,
  ~3–5 seconds) that classifies the question and either invokes the full pipeline
  or hits a lightweight path.
- **Trigger:** Chat UI in scope.

### Query-type router (front-of-pipeline)
Even before the Question Framer, a fast classifier decides: "is this a
lookup, a question, an investigation, or a follow-up to a prior conversation?"
- **Why it matters:** The Framer is expensive (~$0.50–1, ~3 min). Trivial
  questions shouldn't pay that cost.
- **Effort:** ~0.5 day. Small Haiku call with a focused prompt.
- **Trigger:** Chat UI in scope.

### Session memory across multi-turn conversations
Currently `MemoryManager` is a stub. Real chat conversations need to remember
prior turns, established facts, follow-up context.
- **Why it matters:** A follow-up *"what about region B?"* should not require
  re-stating the metric, period, and entity scope.
- **Effort:** ~1–2 days. Probably Cosmos DB or Redis in production; in-process
  dict for development.
- **Trigger:** Phase 2 chat UI.

### Follow-up question suggestions in output
The `follow-up-question-suggestions.md` skill is in the spec but deferred. For
chat, the Communication Agent should suggest 2–3 follow-ups per answer.
- **Why it matters:** Drives engagement and explores adjacent insights.
- **Effort:** ~0.5 day. Skill file + Communication Agent wiring.
- **Trigger:** Chat UI in scope.

### Interactive narrative output mode
The `interactive-narrative-response.md` skill is also deferred. For chat,
recipients want prose answers with embedded data, not action cards.
- **Why it matters:** Action cards are for proactive monitoring; chat needs
  narrative.
- **Effort:** ~1 day. New skill + Communication Agent output-mode dispatch.
- **Trigger:** Chat UI in scope.

---

## Multi-recipient delivery

### Parallel-group execution in the pipeline executor
The Question Framer can emit parallel groups (e.g., Pattern Discoverer +
Relationship Analyzer + Time Series Analyzer all consume the Profiler).
The schema supports it; the executor serializes for MVP.
- **Why it matters:** Saves 30–40% wall-clock time on full proactive runs.
  Critical for chat UX where parallelism reduces perceived latency.
- **Effort:** ~1 day. Use `asyncio` or `concurrent.futures` with a per-call
  concurrency limit from `pipeline_config.yaml`.
- **Trigger:** Multi-recipient or chat work begins; or when run duration
  becomes a complaint.

### Communication Agent fan-out across recipients
For multi-recipient delivery (e.g., 20 TMs each receiving outlet-scoped
findings from a single analytical pass), the Communication Agent should run
N times — once per recipient — with the same findings but filtered scope.
- **Why it matters:** Pattern C in the cost discussion: one analytical pass,
  N renderings. Massive cost win vs. running the full pipeline per recipient.
- **Effort:** ~1 day. Add `recipient_list` to the framer brief; orchestrator
  loops the comms call with different recipient context per iteration.
- **Trigger:** When the team wants to deploy beyond a single recipient.

### Stakeholder map with named-recipient routing
The `stakeholder-communication.md` skill handles tier calibration (IC vs.
Manager vs. Executive). What's missing is the *named-recipient routing*:
which TM's email/Slack does which finding go to.
- **Why it matters:** "Account manager for A003" needs to be a named person,
  not a role placeholder.
- **Effort:** ~0.5 day. Add `stakeholder_map` section to the domain context
  template; orchestrator looks up recipient from the entity → owner mapping.
- **Trigger:** Real delivery (email/Teams) goes live.

### Delivery channel integrations (email, Teams, Slack)
Markdown files on disk are MVP. Real production sends each action card / report
to the recipient's preferred channel.
- **Why it matters:** Recipients won't go fish through a shared folder.
- **Effort:** Per channel: ~1–2 days for email; ~2–3 days for Teams (Power
  Automate or Graph API); ~1 day for Slack.
- **Trigger:** Production rollout.

---

## Performance & reliability

### SDK timeout reliability for long tool-use streams
Run #11's communication-agent stayed silent for 5+ hours despite a 15-min
`timeout` parameter. The SDK's timeout doesn't reliably fire on long streaming
tool-use loops when the connection is broken at OS level.
- **Why it matters:** Silent hangs burn budget and block pipelines.
- **Effort:** ~0.5 day. Wrap each `client.beta.messages.create(...)` call in
  a `concurrent.futures.Future` with a hard timeout, OR set explicit
  `httpx.Timeout(connect=..., read=..., write=..., pool=...)` on the SDK's
  underlying httpx client.
- **Trigger:** As soon as we hit another silent wedge.

### Schema variant catalog
We've built normalizers for ~12 schemas. The pattern is: each new agent variant
surfaces a small field-name mismatch that we coerce in a `@model_validator`.
This will continue as the team refines agents and skills.
- **Why it matters:** Each new variant is a 5-line fix, but they accumulate.
  Worth a small living document so reviewers can see the patterns.
- **Effort:** ~1 hour to write the catalog; ongoing maintenance.
- **Trigger:** When a reviewer asks *"what variants does the schema accept?"*

### Per-agent token budget tuning
Currently `max_tokens_per_call: 16384` globally in `pipeline_config.yaml`.
Some agents (Communication Agent on busy runs) need more; many use a
fraction.
- **Why it matters:** Tighter budgets reduce cost-per-run; looser budgets
  prevent the "no JSON payload" truncation issues.
- **Effort:** ~0.5 day. Per-agent `max_tokens` map in the config.
- **Trigger:** Week 1 telemetry shows the right per-agent numbers.

### Model assignment tuning (Sonnet vs. Opus vs. Haiku)
Spec Part 12 puts Opus on Validator / Root Cause / Opportunity. The lighter
agents (Data Retrieval, Communication Agent) could likely run on Haiku with
no quality loss.
- **Why it matters:** Each agent assigned to Haiku saves 5x its cost. Likely
  20–30% total run cost reduction.
- **Effort:** ~0.5 day, plus a few real runs to compare quality.
- **Trigger:** Week 1 testing telemetry; cost budget pressure.

### Extended prompt cache TTL
Default cache TTL is 5 minutes. For scheduled runs that fire weekly, the cache
is always cold. Anthropic offers 1-hour TTL via `extended-cache-ttl-2025-04-11`
beta header.
- **Why it matters:** Doesn't help cold-start cost (no prior cache to read);
  does help iteration during development and chained ad-hoc runs.
- **Effort:** ~5 minutes. Add the beta to the call.
- **Trigger:** When dev/iteration costs are a focus.

### Pre-warm cache before scheduled runs
For Monday-morning scheduled runs, fire a small no-op call ~30s before the real
pipeline to populate the prompt cache.
- **Why it matters:** Reduces first-stage latency by ~10–20%. Cosmetic for
  scheduled runs but matters for "demo on demand" runs.
- **Effort:** ~0.5 day.
- **Trigger:** When live demos become routine.

---

## Production migration

### Azure AI Foundry integration
Replace direct Anthropic API calls with Azure AI Foundry (Claude via Azure
tenancy).
- **Why it matters:** Required before any real company data flows through.
  Compliance + audit + per-user budgets.
- **Effort:** ~2–3 days. SDK swap, auth wiring (Entra ID), config updates.
- **Trigger:** Pre-production, after CEO demo.

### Cortex Analyst data path
Replace `excel_loader.py` (uploaded CSVs) with Cortex Analyst calls into
Snowflake. Raw rows never leave the warehouse.
- **Why it matters:** Production data-residency story. Required for real
  company data per the data-flow doc in `pipeline-definitions.md` §10.
- **Effort:** ~3–5 days. New loader, SQL/semantic-layer wiring, agent prompt
  updates to use SQL instead of file paths.
- **Trigger:** Production rollout.

### Schema discovery automation
Currently domain context documents are manually authored. Production should
auto-detect new tables, new columns, schema changes.
- **Why it matters:** Domain hygiene at scale.
- **Effort:** ~3–5 days. Periodic Snowflake `INFORMATION_SCHEMA` queries,
  diff against current context docs, alert on drift.
- **Trigger:** Phase 2 production maturity.

### Streamlit UI for domain owners
Business stakeholders edit domain context documents via a UI, not by editing
markdown files in git.
- **Why it matters:** Removes the engineer-as-gatekeeper bottleneck for domain
  context maintenance.
- **Effort:** ~5–7 days. Streamlit app that reads/writes the context markdown
  per validated schema.
- **Trigger:** Multi-domain rollout.

---

## Observability & cost management

### Per-user / per-domain budget enforcement
Today the Budget Tracker is telemetry-only. Production needs hard caps with
graceful truncation when the cap is reached.
- **Why it matters:** Prevents runaway-loop bugs from spending unbounded
  money.
- **Effort:** ~1 day. Add budget-exceeded handling to `_call_and_validate`;
  enforce per-run cap as configured.
- **Trigger:** Production deployment.

### Run cost dashboard
Aggregate `runs/*/run.log` data into a dashboard: cost per run, per agent,
per domain, per recipient, over time.
- **Why it matters:** Spend visibility for finance and capacity planning.
- **Effort:** ~2–3 days. Simple SQLite or Postgres backing + Grafana, or a
  Streamlit dashboard.
- **Trigger:** Production rollout.

### Recipient feedback capture loop
Action cards include space for recipients to indicate whether the
recommendation was acted on, whether it was useful, whether the system was
wrong. Feed back into the system for quality monitoring.
- **Why it matters:** Closes the rigor-vs-action loop. Detects systemic
  false-alarm patterns.
- **Effort:** ~3–5 days. Depends on delivery channel; needs a small webapp
  or form integration.
- **Trigger:** Post-CEO-demo Phase 2.

### OpenTelemetry observability
Replace file-based logging (current) with OpenTelemetry traces shipped to a
centralized logging platform.
- **Why it matters:** Per spec Part 7 production approach. Required for
  multi-instance deployment.
- **Effort:** ~2 days.
- **Trigger:** Production rollout.

---

## Demo and presentation

### Live demo runner with progressive console output
The spec's Part 8 shows a desired demo console output. We have the logs
already (run.log + stdout), but not yet the polished progressive console
output with emojis and section breaks.
- **Why it matters:** CEO demo presentation quality. The visible execution
  is the "wow" moment.
- **Effort:** ~2–3 hours. Wraps `pipeline_executor` events into a polished
  Rich/typer-based console output.
- **Trigger:** Before CEO demo. Currently deferred until after the data
  context document lands.

### Markdown → PDF / HTML wrapper tool
Today recipients open .md files. A tiny `src/tools/render.py` that wraps
`pandoc` + a basic CSS theme would produce branded PDFs and HTML.
- **Why it matters:** Polished sharing for non-technical recipients.
- **Effort:** ~0.5 day. Pandoc is already cross-platform; CSS is ~50 lines.
- **Trigger:** Before CEO demo or when sharing externally.

---

## Analytical capabilities (deferred from MVP)

These are skills from the spec's Part 4 catalog that aren't in the MVP scope.
Each is a markdown file plus minor agent prompt wiring.

- **`multiple-comparison-correction.md`** — formal correction skill. MVP uses
  inline guidance in `statistical-rigor.md`. Effort: ~1 day. Trigger: when
  reviewers want a focused review target.
- **`interaction-detection.md`** — when X→Y depends on Z. MVP surfaces
  suspected interactions as hypotheses for downstream investigation.
  Effort: ~1 day. Trigger: Phase 2.
- **`confounding-analysis.md`** — formal confounder controls. MVP uses
  partial correlation and stratified analysis. Effort: ~1 day. Trigger:
  Phase 2.
- **`dimensionality-reduction.md`** — PCA / UMAP guidance. Effort: ~1 day.
  Trigger: when Pattern Discoverer needs this technique.
- **`lag-lead-analysis.md`** — cross-correlation, leading indicators.
  Effort: ~1 day. Trigger: when time-series analysis needs lead/lag
  detection.
- **`stationarity-tests.md`** — ADF/KPSS formal tests. Effort: ~0.5 day.
  Trigger: Phase 2 time-series maturity.
- **`sensitivity-analysis.md`** — formal sensitivity-to-driver analysis.
  Effort: ~1 day. Trigger: when Opportunity Identifier needs this.
- **`conditional-analysis.md`** — stratified Y behavior conditional on X.
  Effort: ~1 day. Trigger: Phase 2.
- **`causal-inference-DAG.md`** — formal causal inference. Heavyweight.
  Effort: ~2–3 days. Trigger: when basic statistical RCA isn't enough.

---

## Quality & test coverage

### Integration test against the real API
The 28 unit tests cover schema, prompt assembly, and data loading locally.
There's no test that hits the real Anthropic API end-to-end.
- **Why it matters:** Each schema change today is verified by running a real
  smoke test (expensive). A cheap integration test could catch regressions
  earlier.
- **Effort:** ~1 day. Use Anthropic's mock-mode or VCR-style record/replay.
- **Trigger:** When schema changes happen often or when CI is added.

### Replay tool generalization
`src/tools/replay_comms.py` lets us re-run just the Communication Agent
against existing artifacts. The same pattern would help for any failed
stage — partial pipeline replay.
- **Why it matters:** Cuts iteration cost dramatically when one stage fails.
- **Effort:** ~1 day. Generalize the replay tool to accept any stage name.
- **Trigger:** Next time we have a partial-pipeline-failure scenario.

### Stress test on larger data
Smoke test is 100 rows. Real production runs might be 100K–10M rows. We
haven't verified the data-handling pieces (loader, sandbox upload, agent
code execution) at scale.
- **Why it matters:** Pre-production validation of the spec's "context
  discipline" claims.
- **Effort:** ~1 day. Generate a 500K-row CSV; run a full pipeline; verify
  output and cost.
- **Trigger:** Before any production rollout.

### Test that the skills' framing claims hold in practice
Every skill has a "Tie to framing" section claiming the discipline. We
have anecdotal evidence the system works (smoke-test run output), but no
systematic test that pipelines produce honest "nothing to report" outputs
when given uninteresting data.
- **Why it matters:** The framing is the product. Regression here is a
  product-quality failure.
- **Effort:** ~2 days. Generate a smoke dataset with *no* anomalies; verify
  the system produces a clean descriptive summary with zero action cards.
- **Trigger:** Pre-CEO-demo final validation.

---

## Items captured along the way but not yet categorized

- **Hardening domain-context-missing into a hard gate.** Currently permissive
  with a high-severity caveat (per `failure-recovery.md` §6a). Production
  should hard-fail if no context is loaded.
- **Bumping the dataset row threshold past 5M** if the Anthropic sandbox can
  handle it; currently we auto-sample at 5M.
- **Per-stage timeout overrides.** Different stages have different reasonable
  runtimes. The 15-min global default is a compromise.
- **Lineage UI** — `lineage.json` is queryable but not viewable. A tiny
  Streamlit lineage browser would help debugging.
- **Demo data generator with scenarios.** Pending business input on what
  intentional anomalies to inject across the 7 scenarios from the spec's
  Part 8. Currently the smoke-test generator has one mild pattern (A003/SKU003
  instock dip) but isn't the full demo dataset.

---

## How this file is used

When a future session surfaces an enhancement that isn't ready to prioritize,
add it here with the same shape (what / why / effort / trigger). When
something gets prioritized, move it into the active task list and link the
PR back to this file.
