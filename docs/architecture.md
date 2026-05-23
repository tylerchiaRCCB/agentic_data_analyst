# Agentic Data Analyst — Architecture

## One-paragraph positioning

This framework is the **analytical discipline layer** that sits between governed enterprise data (Snowflake + Cortex) and validated business decisions (Account Managers, functional leaders, executives). It is not a query tool, not a BI dashboard, not a notebook assistant — it is a multi-agent system that applies senior-data-analyst-level rigor (independent validation, A-F confidence grading, causation-vs-correlation gates, null-result-as-output discipline, cross-functional synthesis) to data nobody has time to manually examine. Microsoft Fabric Agents and Snowflake Cortex Agents do per-function analytics; this framework adds the validated cross-functional discipline on top.

---

## Layered architecture

```mermaid
flowchart TB
    subgraph audiences["BUSINESS AUDIENCES"]
        direction LR
        a1["Account Managers<br/>(per-territory daily decisions)"]
        a2["Functional Leaders<br/>(per-function weekly synthesis)"]
        a3["Executives / CEO<br/>(org-wide strategic view)"]
    end

    subgraph framework["THE FRAMEWORK · analytical discipline layer"]
        direction TB
        qf["Question Framer<br/>· classify request<br/>· generate hypotheses<br/>· compose pipeline"]
        dr["Data Retrieval Agent<br/>· slice request → governed data"]
        dp["Data Profiler<br/>· quality, distribution shape,<br/>  resistant-stats triggers"]
        analytical["Parallel Analytical Agents<br/>· Relationship Analyzer<br/>· Pattern Discoverer<br/>· Time Series Analyzer"]
        rc["Root Cause Investigator<br/>· counterfactual reasoning<br/>· confounding analysis"]
        oi["Opportunity Identifier<br/>· forward-tense actions"]
        fv["Findings Validator<br/>· INDEPENDENT re-computation<br/>· A-F grade · D/F filtered"]
        ca["Communication Agent<br/>· action cards · descriptive<br/>  summary · HITL gate"]
        sy["Synthesizer Agent<br/>· cross-functional connections<br/>· disciplined non-connections<br/>(STANDALONE; runs over N per-function runs)"]

        qf --> dr --> dp --> analytical --> rc --> oi --> fv --> ca
        ca -.-> sy
    end

    subgraph data["DATA LAYER · Snowflake + Cortex"]
        direction TB
        cag["Cortex Agents<br/>multi-step agentic SQL"]
        can["Cortex Analyst<br/>NL-to-SQL on semantic model"]
        sem["Semantic Model (YAML)<br/>tables · dimensions · measures<br/>· guardrail pairings · thresholds<br/>(owned by BI + business)"]
        sf["Snowflake Warehouse<br/>RBAC · lineage · scale"]

        cag --> can --> sem --> sf
    end

    subgraph sources["SOURCE SYSTEMS"]
        direction LR
        s1["SAP"]
        s2["Salesforce"]
        s3["Retail Link<br/>(Walmart)"]
        s4["MES / SCADA<br/>(production)"]
        s5["Trade Promo<br/>Management"]
        s6["..."]
    end

    subgraph llms["LLM PROVIDERS · A/B testable"]
        direction LR
        anth["Anthropic<br/>(PRIMARY: caching, code exec, Files API)"]
        oai["OpenAI<br/>(via LiteLLM; for A/B testing)"]
        goog["Google Gemini<br/>(via LiteLLM; for A/B testing)"]
    end

    framework -. governed data slices, generated SQL recorded in lineage .-> data
    data -. real data flows to framework's Data Retrieval Agent .-> framework
    framework <-. LLMClient abstraction .-> llms
    sources --> sf

    framework --> a1
    framework --> a2
    sy --> a3

    classDef primary fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
    classDef data fill:#e3f2fd,stroke:#1565c0,stroke-width:2px;
    classDef llm fill:#fff3e0,stroke:#e65100,stroke-width:2px;
    classDef audience fill:#fce4ec,stroke:#ad1457,stroke-width:2px;

    class qf,dr,dp,analytical,rc,oi,fv,ca,sy primary
    class cag,can,sem,sf data
    class anth,oai,goog llm
    class a1,a2,a3 audience
```

---

## Why this is the right architecture

### Three-layer separation of concerns

| Layer | Responsibility | What it OWNS | What it does NOT own |
|---|---|---|---|
| **Data layer** (Snowflake + Cortex) | Governed access to enterprise data | RBAC, lineage, semantic model, SQL generation, query execution | Analytical discipline; rigor; presentation |
| **Framework** (this repo) | Analytical discipline over the data slice | Validation, confidence grading, causation language, synthesis | Data access, governance, semantic meaning |
| **LLM providers** | Inference on prompts the framework constructs | The model itself | Anything else |

This separation is what makes the framework **portable across data layers**. The same framework runs over:
- A CSV on disk (today — demo data)
- A Snowflake query via direct SQL (transitional)
- Cortex Analyst with a governed semantic model (production)
- Cortex Agents for multi-step workflows (advanced production)

The framework doesn't know or care which one is feeding it. The Data Retrieval Agent is the seam.

### Provider-agnostic LLM access

The framework relies on Anthropic-specific features for production economics (prompt caching saves ~5-10× cost on this workload). But the agent logic is provider-agnostic via the `LLMClient` abstraction. To test which provider gives best results:

```yaml
# config/pipeline_config.yaml
model_per_agent:
  question-framer: claude-sonnet-4-6           # Anthropic, native
  data-profiler: claude-sonnet-4-6              # Anthropic, native
  findings-validator: openai/gpt-5              # OpenAI, via LiteLLM
  communication-agent: google/gemini-3-pro      # Gemini, via LiteLLM
```

The framework dispatches each agent's call to the right provider transparently. Caveat: non-Anthropic providers don't have prompt caching, so production economics favor Anthropic primary. The abstraction is for A/B testing and provider risk hedging, not for runtime provider switching.

---

## What this framework adds that Fabric Agents / Cortex Agents do NOT

| Capability | Microsoft Fabric Agents | Snowflake Cortex Agents | THIS FRAMEWORK |
|---|---|---|---|
| Natural-language query against governed warehouse | ✅ strong | ✅ best-in-class | ❌ (uses Cortex for this) |
| **Independent validator with non-bypassable filtering** | ❌ | ❌ | ✅ |
| **A-F confidence grading + required caveat propagation** | ❌ | ❌ | ✅ |
| **Causation-vs-correlation language gates** | ❌ | ❌ | ✅ |
| **Null-result-as-output discipline** ("nothing concerning this week") | ❌ | ❌ | ✅ |
| **Skill-based methodology versioning** | ❌ | ❌ | ✅ |
| **Cross-functional synthesis with rigor** | ❌ | ❌ | ✅ |
| **Multiple-comparison correction by default** | ❌ | ❌ | ✅ |
| **Simpson's Paradox mandatory check** | ❌ | ❌ | ✅ |
| **Power analysis on null findings** | ❌ | ❌ | ✅ |
| **Human-in-the-loop gate on high-stakes findings** | ❌ | ❌ | ✅ |
| **Tracking-gaps as a product feature** | ❌ | ❌ | ✅ |
| Enterprise UI / Power BI integration | ✅ best-in-class | ⚠️ growing | ❌ |
| Direct warehouse-scale compute | ✅ via Fabric | ✅ native | ❌ (uses Cortex) |

The pattern: **Fabric and Cortex Agents are the data and query layers; this framework is the discipline layer that turns retrieved data into validated, calibrated findings.** The combination is what an enterprise needs; neither alone is sufficient.

---

## The cross-functional synthesis pattern (Walmart In-Store Execution example)

The strongest demonstration of the framework's value: hierarchical synthesis from per-Account-Manager runs up through regional and org-wide views.

```mermaid
flowchart LR
    subgraph per_am["Per-Account-Manager runs"]
        am1["AM Sarah's Walmart accounts<br/>(grade B finding: SKU-7 instock 19↓)"]
        am2["AM Marcus's Walmart accounts<br/>(grade C: noise)"]
        am3["AM Jen's Walmart accounts<br/>(grade B: SKU-7 instock 12↓)"]
        amN["... 47 other AMs"]
    end

    subgraph regional["Regional synthesis"]
        ne["NE region synthesizer<br/>(connects: 'SKU-7 instock issue in 8 of 12 NE AMs')"]
    end

    subgraph orgwide["Org-wide synthesis"]
        org["Org-wide synthesizer<br/>(connects: 'SKU-7 instock isolated to NE;<br/>non-connection: not happening in SE or W')"]
    end

    am1 --> ne
    am2 --> ne
    am3 --> ne
    amN -.-> ne

    ne --> org

    am1 -.delivered to.-> sarah["Sarah · daily decisions"]
    ne -.delivered to.-> rlead["NE Regional Lead"]
    org -.delivered to.-> exec["VP Walmart / CEO"]

    classDef per fill:#e3f2fd,stroke:#1565c0;
    classDef syn fill:#e8f5e9,stroke:#2e7d32;
    classDef rec fill:#fce4ec,stroke:#ad1457;

    class am1,am2,am3,amN per
    class ne,org syn
    class sarah,rlead,exec rec
```

Each layer's audience gets the report calibrated to their decision scope. Account Managers get daily AM-level signals; regional leads get the cross-AM pattern picture; executives get the org-wide synthesis. The same data flows through; the framework calibrates audience-by-audience.

**The Synthesizer's discipline keeps this honest:** it only connects findings that already exist in the source runs (no inventing), caps connection grades at the weakest constituent finding's grade, applies confounding analysis on every connection, and surfaces non-connections explicitly. A leader reading the org-wide synthesis can trust that the patterns named are real and the patterns NOT named have been actively looked for.

---

## File-system layout

```
agents/              · 11 agent definitions (markdown)
skills/
  universal/         · always loaded with every agent call (8 skills)
  analytical/        · loaded on demand by analytical agents
  validation/        · loaded by Findings Validator
  output/            · loaded by Communication Agent
  domain-specific/   · CPG-specific methodology
context/
  domains/           · domain context documents (deployment authored, post-business-meeting)
  examples/          · template + reference examples
  semantic_models/   · Cortex Analyst semantic models (BI authored, governed)
src/
  orchestrator/      · pipeline executor, prompt assembler, budget tracker, lineage,
                       HITL gate, schemas (Pydantic), normalizers
  api/               · LLMClient abstraction · ClaudeClient (Anthropic native) ·
                       LiteLLMClient (OpenAI, Gemini, Azure, Bedrock)
  data_access/       · SnowflakeClient · CortexAnalystClient · CortexAgentClient ·
                       Excel/CSV loader · injection defenses
  observability/     · structured JSON logger · tracer · lineage tracker
  delivery/          · (Phase 2) scheduled jobs, Slack/email
  tools/             · replay_comms · synthesize_runs · extract_context_gaps
config/              · pipeline_config.yaml · cost pricing · HITL threshold · etc.
tests/               · 90+ tests including mock-SDK integration tests
docs/                · this file, plus per-skill and per-agent docs
output/              · rendered reports (one per run · HITL-gated when configured)
runs/                · per-run artifacts, JSONL logs, span traces, lineage
```

---

## Production deployment phases

| Phase | Data path | LLM | Status |
|---|---|---|---|
| **MVP demo** (June 2-6 2026) | CSV on disk; demo data hand-curated | Anthropic primary | Current |
| **Phase D1: Direct Snowflake connector** | `SnowflakeClient.execute_query` for known-safe queries | Anthropic | Scaffolded, raises NotImplemented until creds |
| **Phase D2: Cortex Analyst + semantic model** | `CortexAnalystClient.ask` against governed YAML semantic model | Anthropic primary; provider A/B testable | Scaffolded; semantic model authored by BI + business |
| **Phase D3: Cortex Agents** | `CortexAgentClient.run_workflow` for multi-step | Anthropic primary | Scaffolded |
| **Phase 2: Delivery + observability** | Scheduled jobs, Slack/email, LangSmith / Phoenix observability | Anthropic primary | Deferred |

The clean separation between framework and data layer means each phase upgrades a clearly-bounded piece without touching the others. Phase D2 doesn't change agent logic; Phase D3 doesn't change validation; Phase 2 doesn't change discipline. That bounded modifiability is the architectural moat.
