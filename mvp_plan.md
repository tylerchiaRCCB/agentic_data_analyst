# AI Data Analyst Tool — MVP Plan & Architecture Specification

## Core Framing (Read First)

**What this tool is:** A system that embeds senior data analyst level exploratory data analysis across all teams with validated data domains, applied at a scale and consistency humans cannot match.

**What this tool is not:** A magic insight machine that finds dramatic new findings every run.

The product is *rigor and intellectual honesty* applied repeatedly to data nobody has time to manually examine. Sometimes that produces actionable findings worth a stakeholder's attention. Sometimes it produces "nothing concerning this week, here is a descriptive summary." Both outputs are valuable. The system that knows the difference — that has the discipline to stay quiet when findings don't warrant action — is what makes the tool trustworthy and worth using.

This framing shapes every design decision below:

- The Findings Validator can produce zero high-confidence findings on a given run, and that is a successful run — not a failure.
- The Communication Agent must be able to render a "no actionable findings this period, here are the descriptive observations" output, not just action cards.
- The Opportunity Identifier doesn't always find opportunities; sometimes performance is genuinely good and the right answer is to say so.
- The Question Framer doesn't force the pipeline to produce findings — it composes the pipeline appropriate to the input, including pipelines that conclude "nothing here rises to action."

When Claude Code or any developer builds this system, this framing must carry through to prompt design. Agent and skill markdowns must reinforce — not undermine — the discipline to stay quiet when appropriate. An agent that feels obligated to produce a finding when no finding is warranted is a bug, not a feature.

---

## Purpose of This Document

This is the complete blueprint for building an AI-powered exploratory data analyst tool. It defines the architecture, agent and skill specifications, orchestration design, MVP scope, and team execution plan. Once complete and approved, this document becomes the specification that Claude Code (or any developer) uses to build the working system.

This is a design specification, not implementation. Markdown agent and skill files are written from this spec, not pre-generated. Domain context documents come from collaboration between the data science team and business domain owners.

---

## Part 1: Architecture Overview

### What the Tool Does

A single tool that supports two modes of operation:

**Proactive Monitoring (Scheduled).** Runs on a defined cadence (e.g., Monday mornings). Scans data for anomalies and opportunities worth investigating. For findings that pass validation, generates action cards delivered to specific stakeholders with recommended actions, owners, and follow-up expectations.

**Interactive Analysis (User-Initiated).** A user asks a question — simple lookup or complex investigation — and the tool composes the appropriate analytical pipeline. Simple queries return fast with light analysis; complex questions trigger deeper investigation. Same architecture, dynamically scaled to question complexity.

Both modes route through the same agent infrastructure. The Question Framer classifies the input and the orchestrator composes the appropriate pipeline.

### Core Design Principles

**Agent vs. Skill.** Agents are stage-level decision-makers that determine *what* analytical work happens. Skills are detailed methodology files that define *how* to perform specific techniques. Each API call assembles: agent markdown + relevant skills + universal skills + domain context document.

**Code Execution for Everything Quantitative.** Statistical claims must be computed via executed Python code, never reasoned about. This is the single most important defense against hallucinated numbers.

**Domain Context as Markdown.** Business meaning (metric definitions, relationships, quirks, guardrail pairings) lives in markdown files per data domain. Platform-agnostic, version-controlled in Azure DevOps, editable by business data owners. Snowflake Semantic Views or other technical implementations can be generated from these markdowns later if needed.

**Dynamic Pipeline Composition.** The orchestrator does not run a fixed sequence. The Question Framer outputs which agents and skills the pipeline needs, and the orchestrator executes only that path. Simple questions skip most agents.

**Typed Artifacts Between Agents.** Each agent produces a structured JSON artifact that the next agent validates and consumes. No ad-hoc text handoffs. Enables observability, replay, and unit testing.

**Code-Computed Validation as Quality Gate.** Findings Validator independently re-computes every claim before it reaches output. Findings that don't survive validation get downgraded or filtered.

### The 10 Agents

1. **Question Framer** — Entry-point strategic planner. Interprets the input (live question or scheduled prompt), classifies complexity, generates testable hypotheses, determines which downstream agents compose the pipeline. Produces a typed analytical brief.

2. **Data Retrieval Agent** — Owns data access. In MVP mode, loads uploaded Excel/CSV files and returns a structured dataset handle. In production, this evolves to call Cortex Analyst or pre-validated Snowflake views. Bears the security boundary for data access and includes prompt-injection defenses for free-text columns.

3. **Data Profiler** — Assesses data quality, completeness, freshness, grain, distributions, and bias risks. Also handles univariate exploration — distribution shape, frequency analysis, basic temporal characterization. Uses code execution to compute exact statistics.

4. **Relationship Analyzer** — Examines how variables relate. Correlation analysis, group comparison, cross-tabulation, conditional analysis, interaction detection. Decides which techniques to apply and calls relevant skills.

5. **Pattern Discoverer** — Finds structure not pre-defined. Clustering, outlier characterization (multivariate/structural), dimensionality reduction. Also generates hypotheses from observed patterns for further investigation.

6. **Time Series Analyzer** — Handles all temporal analysis. STL decomposition, change point detection, cohort analysis, lag/lead analysis, stationarity testing. Single consolidated agent (Trend Decomposer merged in).

7. **Root Cause Investigator** — Past-tense diagnostic. Investigates specific deviations or anomalies. Decomposition, hypothesis testing with computed statistics, evidence ranking, Simpson's Paradox checks. Produces explanations grounded in code-computed statistical evidence.

8. **Opportunity Identifier** — Forward-tense prescriptive. Takes root causes plus broader patterns to identify where action could improve outcomes. Performance gap analysis, benchmarking, sensitivity analysis, predictive model readiness assessment (is this a pattern that warrants a model, or just an insight to act on now). Connects findings to potential team interventions.

9. **Findings Validator** — Independent quality gate. Re-computes every claim, runs statistical revalidation, checks guardrail metric pairings. Assigns A-F confidence grades per finding. Two distinct skills under one agent: statistical revalidation and guardrail pairing check.

10. **Communication Agent** — Renders output for recipients. One agent, two skills: interactive narrative response (BLUF format for user questions) and proactive action card (alert format with owner/due/follow-up for scheduled findings). Format-specific templates selected by the Question Framer's output_mode field.

### Pipeline Composition Examples

The orchestrator runs different paths based on Question Framer output:

**Simple lookup** ("Top 5 DCs by sales volume last week"):
Question Framer → Data Retrieval → Data Profiler (minimal) → Communication Agent
*4 agents, fast, low cost*

**Descriptive comparison** ("How did weekly sales trend over the past 6 months?"):
Question Framer → Data Retrieval → Data Profiler → Time Series Analyzer → Communication Agent
*5 agents, moderate*

**Diagnostic investigation** ("Why did Southeast volume decline last week?"):
Question Framer → Data Retrieval → Data Profiler → Relationship Analyzer → Time Series Analyzer → Root Cause Investigator → Findings Validator → Communication Agent
*8 agents, full diagnostic*

**Opportunity identification** ("What are 5 opportunities to help bottom DCs improve?"):
Question Framer → Data Retrieval → Data Profiler → Pattern Discoverer → Relationship Analyzer → Root Cause Investigator → Opportunity Identifier → Findings Validator → Communication Agent
*9 agents, full pipeline*

**Proactive monitoring** (Scheduled weekly run):
Question Framer (interprets scheduled prompt) → Data Retrieval → Data Profiler → Pattern Discoverer (hypothesis generation) → relevant analysis agents based on patterns found → Root Cause Investigator (for each significant pattern) → Opportunity Identifier → Findings Validator → Communication Agent (action card format)
*Full pipeline, runs once with multiple findings investigated in parallel*

---

## Part 2: Folder Structure

This is the exact directory layout for the Azure DevOps repo.

```
ai-analyst/
│
├── README.md
├── .gitignore
│
├── agents/
│   ├── question-framer.md
│   ├── data-retrieval-agent.md
│   ├── data-profiler.md
│   ├── relationship-analyzer.md
│   ├── pattern-discoverer.md
│   ├── time-series-analyzer.md
│   ├── root-cause-investigator.md
│   ├── opportunity-identifier.md
│   ├── findings-validator.md
│   └── communication-agent.md
│
├── skills/
│   ├── universal/                          # Always loaded with every agent call
│   │   ├── analysis-design-spec.md
│   │   ├── statistical-rigor.md
│   │   ├── data-quality-standards.md
│   │   ├── ethical-analysis.md
│   │   ├── triangulation.md
│   │   ├── close-the-loop.md
│   │   ├── tracking-gaps.md
│   │   └── resistant-statistics.md
│   │
│   ├── analytical/                         # Loaded by specific agents on demand
│   │   ├── correlation-analysis.md
│   │   ├── group-comparison.md
│   │   ├── cross-tabulation.md
│   │   ├── conditional-analysis.md
│   │   ├── interaction-detection.md
│   │   ├── clustering-algorithms.md
│   │   ├── dimensionality-reduction.md
│   │   ├── outlier-typology.md
│   │   ├── stl-decomposition.md
│   │   ├── change-point-detection.md
│   │   ├── cohort-analysis.md
│   │   ├── lag-lead-analysis.md
│   │   ├── stationarity-tests.md
│   │   ├── hypothesis-testing.md
│   │   ├── effect-size-calculation.md
│   │   ├── simpsons-paradox-check.md
│   │   ├── confounding-analysis.md
│   │   ├── benchmarking-methods.md
│   │   ├── performance-gap-analysis.md
│   │   ├── sensitivity-analysis.md
│   │   ├── predictive-readiness-assessment.md
│   │   ├── hypothesis-generation-from-data.md
│   │   └── multiple-comparison-correction.md
│   │
│   ├── validation/                         # Loaded by Findings Validator
│   │   ├── statistical-revalidation.md
│   │   └── guardrail-pairing-check.md
│   │
│   ├── output/                             # Loaded by Communication Agent
│   │   ├── interactive-narrative-response.md
│   │   ├── proactive-action-card.md
│   │   ├── descriptive-summary-format.md
│   │   ├── insight-first-formatting.md
│   │   ├── confidence-language.md
│   │   ├── stakeholder-communication.md
│   │   ├── visualization-recommendations.md
│   │   └── follow-up-question-suggestions.md
│   │
│   └── domain-specific/                    # CPG-specific methodology
│       ├── cpg-derived-metrics.md
│       └── guardrail-metric-pairing.md
│
├── context/
│   ├── templates/
│   │   └── domain-context-template.md      # Template for new domains
│   ├── domains/
│   │   └── (populated per data source as added)
│   └── examples/
│       └── demo-data-context.md            # Context document for MVP demo data
│
├── orchestration/
│   ├── pipeline-definitions.md             # DAG composition rules and skip logic
│   ├── artifact-schemas.md                 # JSON schemas for inter-agent handoffs
│   └── failure-recovery.md                 # Retry, degradation, and error handling rules
│
├── data/
│   ├── generators/
│   │   └── generate_demo_data.py           # Creates dummy data with intentional anomalies
│   └── sample/
│       └── (generated demo files)
│
├── src/
│   ├── orchestrator/
│   │   ├── pipeline_executor.py            # Reads framer brief, composes and executes DAG
│   │   ├── prompt_assembler.py             # Loads agent + skills + context into system prompt
│   │   ├── memory_manager.py               # Session memory and conversation state
│   │   ├── budget_tracker.py               # Token/cost tracking and budget enforcement
│   │   └── lineage_tracker.py              # Audit trail for findings
│   ├── api/
│   │   └── claude_client.py                # Anthropic API wrapper with retries
│   ├── data_access/
│   │   ├── excel_loader.py                 # MVP: Load Excel/CSV files
│   │   ├── snowflake_loader.py             # Production: stub for Cortex/Snowflake (deferred)
│   │   └── injection_defense.py            # Prompt injection mitigations on free-text columns
│   ├── observability/
│   │   ├── tracer.py                       # Span tracking for each agent and skill call
│   │   └── run_logger.py                   # Persist run history for debugging and audit
│   ├── delivery/
│   │   ├── report_writer.py                # Format final outputs as markdown/HTML
│   │   └── live_demo_runner.py             # Progressive console output for live demos
│   └── main.py                             # Entry point with --scheduled and --demo flags
│
├── output/
│   └── (generated reports and action cards land here)
│
├── config/
│   ├── pipeline_config.yaml                # Which model per agent, retry counts, timeouts
│   ├── thresholds.yaml                     # Anomaly detection thresholds per metric
│   └── delivery_config.yaml                # Report recipients, format, channel
│
├── tests/
│   ├── test_prompt_assembly.py
│   ├── test_artifact_schemas.py
│   ├── test_pipeline_composition.py
│   └── test_data_loading.py
│
└── docs/
    ├── architecture.md                     # This document
    ├── adding-new-domain.md                # How to add a new data source
    ├── writing-agents.md                   # Guide for agent markdown authoring
    ├── writing-skills.md                   # Guide for skill markdown authoring
    └── demo-walkthrough.md                 # CEO demo script
```

---

## Part 3: Agent Specifications

Each agent specification follows the same structure: role, inputs, outputs, methodology, skills consumed, position in pipeline.

### 3.1 Question Framer

**Role:** Entry-point strategic planner. Interprets the input, classifies complexity, generates testable hypotheses for proactive mode, and determines pipeline composition.

**Inputs:**
- For interactive mode: user's natural language question + session memory (prior context)
- For proactive mode: scheduled prompt configuration + monitoring scope

**Outputs (typed JSON):**
```json
{
  "input_mode": "interactive | proactive",
  "complexity_level": "L1 | L2 | L3 | L4",
  "analytical_questions": [...],
  "hypotheses": [...],
  "data_requirements": {...},
  "decision_context": "...",
  "success_criteria": "...",
  "pipeline_composition": [
    {"agent": "data-retrieval", "skills": [...]},
    {"agent": "data-profiler", "skills": [...]},
    ...
  ],
  "output_mode": "narrative | action-card",
  "investigation_mode": "diagnostic | prescriptive | both",
  "token_budget": <int>
}
```

**Methodology highlights:**
- Verifies premises in the question (don't assume "share is declining" — test it)
- Decomposes compound questions
- Generates 3-5 testable hypotheses per analytical question
- Classifies complexity to drive pipeline composition
- Sets token budget based on complexity

**Skills consumed:** analysis-design-spec, hypothesis-generation-from-data

**Position:** Always first.

### 3.2 Data Retrieval Agent

**Role:** Owns all data access. Loads data, validates schema, applies prompt injection defenses, produces typed dataset handle for downstream agents.

**Inputs:**
- Data reference (file path for MVP, or query specification for production)
- Data requirements from Question Framer's brief

**Outputs (typed JSON):**
```json
{
  "dataset_handle": "...",
  "schema": {...},
  "row_count": <int>,
  "column_metadata": [...],
  "free_text_columns_sanitized": [...],
  "data_source_type": "uploaded_file | snowflake_view | cortex_analyst"
}
```

**Methodology highlights:**
- MVP: Loads Excel/CSV, infers schema, sanitizes free-text columns
- Production (deferred): Routes to Cortex Analyst or pre-validated Snowflake views
- Always read-only — no write/update/delete capability
- Free-text columns flagged and content treated as data, never as instructions

**Skills consumed:** None directly (uses universal skills for data quality standards)

**Position:** Second, immediately after Question Framer.

### 3.3 Data Profiler

**Role:** Quality assessment and univariate exploration. Foundation for trustworthy analysis.

**Inputs:**
- Dataset handle from Data Retrieval Agent
- Specific dimensions of interest from Question Framer's brief

**Outputs (typed JSON):**
```json
{
  "readiness_assessment": "READY | READY_WITH_CAVEATS | INSUFFICIENT",
  "completeness": {...},
  "freshness": {...},
  "grain": {...},
  "distributions": {...},
  "baselines": {...},
  "quality_issues": [...],
  "data_integrity_risks": [...],
  "mandatory_caveats": [...],
  "notable_observations": [...]
}
```

**Methodology highlights:**
- Computes exact null rates, distributions, outliers via code execution
- Establishes baselines for downstream comparison
- Flags Simpson's Paradox risk, survivorship bias, selection bias
- Identifies univariate outliers as data quality concerns
- Distinguishes data quality issues from genuine business anomalies

**Skills consumed:** data-quality-standards, statistical-rigor, resistant-statistics, outlier-typology, cpg-derived-metrics, tracking-gaps

**Position:** Third. Required for any analytical pipeline.

### 3.4 Relationship Analyzer

**Role:** Examines how variables relate to each other.

**Inputs:**
- Profiler output
- Variables of interest from Question Framer's brief

**Outputs (typed JSON):**
```json
{
  "relationships_examined": [...],
  "significant_correlations": [...],
  "group_differences": [...],
  "interaction_effects": [...],
  "notable_findings": [...]
}
```

**Methodology highlights:**
- Decides which pairs and groups of variables to examine
- Selects appropriate technique per relationship (Pearson vs. Spearman, t-test vs. Mann-Whitney, etc.)
- All statistical tests computed via code execution
- Applies multiple-comparison correction for many tests

**Skills consumed:** correlation-analysis, group-comparison, cross-tabulation, conditional-analysis, interaction-detection, hypothesis-testing, effect-size-calculation, multiple-comparison-correction

**Position:** Variable. Called when question involves variable relationships.

### 3.5 Pattern Discoverer

**Role:** Finds structure that isn't pre-defined. Generates hypotheses from observed patterns.

**Inputs:**
- Profiler output
- Optional: question-specific focus areas

**Outputs (typed JSON):**
```json
{
  "clusters_identified": [...],
  "structural_outliers": [...],
  "dimensionality_findings": {...},
  "generated_hypotheses": [...]
}
```

**Methodology highlights:**
- Decides whether clustering, dimensionality reduction, or outlier characterization are appropriate
- Generates hypotheses from observed patterns for further investigation
- For proactive monitoring, this is where the system generates "things worth investigating" without a specific user question

**Skills consumed:** clustering-algorithms, dimensionality-reduction, outlier-typology, hypothesis-generation-from-data

**Position:** Variable. Always called for proactive monitoring; called for interactive questions about discovery or segmentation.

### 3.6 Time Series Analyzer

**Role:** All temporal analysis consolidated. Trend, seasonality, change points, cohorts, lags.

**Inputs:**
- Profiler output confirming temporal data is present
- Time period of interest from Question Framer's brief

**Outputs (typed JSON):**
```json
{
  "decomposition": {...},
  "change_points": [...],
  "cohort_findings": [...],
  "lag_relationships": [...],
  "stationarity_assessment": "..."
}
```

**Methodology highlights:**
- Decides which temporal techniques are appropriate
- STL decomposition for trend/seasonality separation
- Change point detection for level shifts
- Cohort analysis for longitudinal patterns

**Skills consumed:** stl-decomposition, change-point-detection, cohort-analysis, lag-lead-analysis, stationarity-tests

**Position:** Variable. Called when question involves time dynamics.

### 3.7 Root Cause Investigator

**Role:** Past-tense diagnostic. Explains why specific deviations or patterns occurred.

**Inputs:**
- Findings from upstream analytical agents (Profiler, Relationship Analyzer, Pattern Discoverer, Time Series Analyzer)
- Anomaly or pattern to investigate

**Outputs (typed JSON):**
```json
{
  "primary_root_cause": {...},
  "decomposition": {...},
  "hypotheses_tested": [...],
  "primary_drivers": [...],
  "rejected_hypotheses": [...],
  "open_questions": [...],
  "analytical_caveats": [...]
}
```

**Methodology highlights:**
- Decomposes observed outcome into component drivers
- Tests each hypothesis with computed statistics
- Ranks explanations by evidence strength
- Reports rejected hypotheses alongside confirmed ones
- Distinguishes correlation from causation explicitly

**Skills consumed:** hypothesis-testing, effect-size-calculation, simpsons-paradox-check, confounding-analysis, statistical-rigor

**Position:** Variable. Called for diagnostic questions and for investigating significant patterns found by upstream agents.

### 3.8 Opportunity Identifier

**Role:** Forward-tense prescriptive. Takes root causes plus broader patterns to identify where action could improve outcomes. Connects findings to potential team interventions.

**Inputs:**
- Root cause findings
- Pattern findings
- Performance baselines from Profiler

**Outputs (typed JSON):**
```json
{
  "performance_gaps": [...],
  "opportunity_areas": [...],
  "intervention_recommendations": [...],
  "predictive_readiness_assessment": {...},
  "sensitivity_analysis": {...}
}
```

**Methodology highlights:**
- Performance gap analysis vs. internal benchmarks
- Identifies where execution changes could improve outcomes
- Assesses whether patterns warrant predictive modeling vs. immediate action
- Acts as funnel to data science team for ML-worthy opportunities

**Skills consumed:** benchmarking-methods, performance-gap-analysis, sensitivity-analysis, predictive-readiness-assessment, guardrail-metric-pairing

**Position:** Variable. Called for prescriptive questions and as final analytical agent in proactive monitoring.

### 3.9 Findings Validator

**Role:** Independent quality gate. Re-computes claims, checks guardrails, assigns confidence grades.

**Inputs:**
- All findings from upstream analytical agents
- Original data (for independent recomputation)
- Domain context (for guardrail pairings)

**Outputs (typed JSON):**
```json
{
  "overall_assessment": "...",
  "findings_review": [
    {
      "finding": "...",
      "grade": "A | B | C | D | F",
      "justification": "...",
      "layer_results": {...},
      "required_caveats": [...],
      "recommended_actions_for_investigator": [...]
    }
  ],
  "cross_cutting_issues": [...],
  "guardrail_check_results": [...]
}
```

**Methodology highlights:**
- Independently re-computes every claim (does not take investigator's numbers at face value)
- Validates statistical rigor (appropriate tests, sample sizes, significance, effect sizes)
- Checks guardrail metric pairings (e.g., volume up → check margin)
- Assigns A-F confidence grades per finding
- Findings graded D or F do not appear as conclusions

**Skills consumed:** statistical-revalidation, guardrail-pairing-check, hypothesis-testing, simpsons-paradox-check

**Position:** Always second-to-last, before Communication Agent.

### 3.10 Communication Agent

**Role:** Renders output for recipients. One agent, multiple output modes.

**Inputs:**
- Validated findings from Findings Validator (which may be zero findings — that is a valid state, not a failure)
- Output mode from Question Framer (action-card for MVP; narrative deferred to Phase 2)
- Recipient role information (for stakeholder adaptation)

**Outputs:**
- Markdown-formatted action card(s) when findings warrant action
- Descriptive summary when no findings rise to action level — concise overview of stable performance with key metrics, comparison to baselines, and explicit statement that no anomalies or opportunities required attention this period
- Combination of both when some areas have findings and others are stable

**Methodology highlights:**
- Selects appropriate output template based on what the Validator passed forward
- **Critical: when Validator produces zero findings worth surfacing, the Communication Agent renders a descriptive summary, not a fabricated finding.** "Nothing concerning this week, here is your summary" is a complete and valid output.
- Carries forward all mandatory caveats from validator
- Translates statistical language into business confidence language
- Adapts depth and framing to recipient role
- Suggests visualization types where appropriate
- For action cards: includes follow-up triggers and owner accountability
- For descriptive summaries: notes what was examined, what baselines were checked, what would have constituted a finding, and that none was found

**Skills consumed:** proactive-action-card, descriptive-summary-format, insight-first-formatting, confidence-language, stakeholder-communication, visualization-recommendations

**Position:** Always last.

---

## Part 4: Skill Specifications

Skills are grouped into five categories. Each skill is a focused methodology file consumed by one or more agents.

### 4.1 Universal Skills (Always Loaded)

These load with every agent call. Keep each under 500 tokens of instructions.

- **analysis-design-spec.md** — Every analysis answers five questions before proceeding: what is the question, what decision does it inform, what data is needed, what does success look like, what are the limitations.
- **statistical-rigor.md** — All quantitative claims backed by computed evidence. Specifies when to use which test, requires p-values + CIs + effect sizes + sample sizes, requires multiple-comparison correction when running many tests, distinguishes correlation from causation explicitly.
- **data-quality-standards.md** — Measure don't assume completeness, freshness, grain, distribution. Establish baselines. Distinguish data quality issues from business anomalies.
- **ethical-analysis.md** — Evidence supports specificity of attribution. Confounding factors addressed before causal claims. Base rates considered. Counterfactuals stated. Disparate impact checked.
- **triangulation.md** — Findings verified from multiple time windows, aggregation levels, metrics, comparison baselines, and population cuts before being presented as conclusions.
- **close-the-loop.md** — Every recommendation has specific action, owner, success criterion, follow-up trigger. No vague language ("monitor," "investigate further").
- **tracking-gaps.md** — When required data doesn't exist, produce specific instrumentation request rather than working around the gap.
- **resistant-statistics.md** — For skewed distributions (common in CPG: volume, basket size), use median/MAD instead of mean/SD. Hampel filters for outlier-robust analysis.

### 4.2 Analytical Skills (Loaded On Demand)

Loaded by specific agents based on what techniques the analysis requires.

**Relationship analysis:**
- **correlation-analysis.md** — Pearson vs. Spearman selection, interpretation thresholds, partial correlation when controlling for confounders.
- **group-comparison.md** — t-tests, Mann-Whitney U, ANOVA selection rules, equal-variance assumptions.
- **cross-tabulation.md** — Chi-squared, Fisher's exact, residual analysis.
- **conditional-analysis.md** — How variable Y behaves conditional on X. Stratified analysis.
- **interaction-detection.md** — When relationship X→Y depends on Z. Two-way interactions, when to suspect them.

**Pattern discovery:**
- **clustering-algorithms.md** — k-means, hierarchical, DBSCAN selection. Distance metric selection. Cluster validation (silhouette, gap statistic).
- **dimensionality-reduction.md** — PCA, factor analysis. When each is appropriate. Interpreting components.
- **outlier-typology.md** — Univariate vs. multivariate vs. temporal outliers. Which agent owns which type.

**Time series:**
- **stl-decomposition.md** — Seasonal-trend-residual decomposition. Period detection. Multiplicative vs. additive.
- **change-point-detection.md** — Algorithms (CUSUM, PELT), parameter selection, validation.
- **cohort-analysis.md** — Longitudinal analysis of entity groups. Cohort definition rules.
- **lag-lead-analysis.md** — Cross-correlation, lead-lag relationships, identifying leading indicators.
- **stationarity-tests.md** — ADF, KPSS tests. When stationarity matters for analysis.

**Investigation:**
- **hypothesis-testing.md** — Selecting appropriate test, computing significance, reporting standards.
- **effect-size-calculation.md** — Cohen's d, relative differences, practical vs. statistical significance.
- **simpsons-paradox-check.md** — Computing aggregate vs. segment-level metrics, detecting reversal.
- **confounding-analysis.md** — Identifying potential confounders, controlling for them computationally.
- **multiple-comparison-correction.md** — When to apply (many tests), which method (Benjamini-Hochberg FDR for EDA, Bonferroni for confirmatory).

**Opportunity:**
- **benchmarking-methods.md** — Internal vs. external benchmarks, peer group selection, normalization.
- **performance-gap-analysis.md** — Actual vs. potential calculation, gap decomposition.
- **sensitivity-analysis.md** — Which variables drive outcomes most, what-if scenarios.
- **predictive-readiness-assessment.md** — Assessing whether a pattern warrants a model. Sample size needs, feature availability, business value of prediction vs. detection.

**Cross-cutting:**
- **hypothesis-generation-from-data.md** — Generating testable hypotheses from observed patterns. Used by Pattern Discoverer (after pattern detection) and Question Framer (for generic scheduled prompts).

### 4.3 Validation Skills (Loaded by Findings Validator)

- **statistical-revalidation.md** — Independent recomputation methodology. Compare to investigator's numbers, flag discrepancies. Layer 1-4 validation logic.
- **guardrail-pairing-check.md** — Domain-defined pairings (volume↔margin, conversion↔traffic, distribution↔fill rate). Check guardrail movement alongside primary metric. Flag trade-offs.

### 4.4 Output Skills (Loaded by Communication Agent)

- **interactive-narrative-response.md** — BLUF format. Headline finding + 2-4 supporting points + follow-up suggestions.
- **proactive-action-card.md** — Alert format. ALERT/CONFIDENCE/WHY IT MATTERS/ROOT CAUSE/RECOMMENDED ACTION/OWNER/DUE/FOLLOW-UP/CAVEATS.
- **descriptive-summary-format.md** — Output format for runs where no findings rose to action level. Concise overview of what was examined, what baselines were checked, the metrics observed, and explicit statement that nothing required attention this period. Required so the system has a defined "all clear" output rather than producing fabricated findings to fill space.
- **insight-first-formatting.md** — Pyramid structure. Most important information first. Scannable. 60-second readable.
- **confidence-language.md** — Match language to evidence strength. A→direct statement, B→state with caveat, C→preliminary framing. Statistical translations.
- **stakeholder-communication.md** — Adapt depth and framing to recipient role (IC, manager, director, executive).
- **visualization-recommendations.md** — Suggest chart types based on data shape and analytical purpose. Tool doesn't render but recommendations guide downstream users.
- **follow-up-question-suggestions.md** — For interactive mode, suggest 2-3 follow-up questions that build on the finding.

### 4.5 Domain-Specific Skills

- **cpg-derived-metrics.md** — CPG-specific derivations: velocity (sales/ACV-weighted distribution), days-of-supply, promotional lift, cannibalization indices, distribution coverage metrics.
- **guardrail-metric-pairing.md** — General rules for guardrail pairing logic. Specific pairings (which metric pairs with which) live in domain context documents, not here.

---

## Part 5: Domain Context Document Structure

Each connected data domain has a markdown context document. Sections:

1. **Domain overview** — What this data covers, who uses it, what decisions it informs.
2. **Data sources** — Tables, views, or files with grain and refresh cadence.
3. **Key metrics** — Per metric: definition, calculation, unit, typical range, inclusions/exclusions, alternative definitions to disambiguate.
4. **Dimensions** — Per dimension: description, valid values, hierarchies, special values.
5. **Business rules** — Always-apply filters, exclusion criteria, time boundaries.
6. **Known quirks** — Tribal knowledge: broken periods, definition changes, migration artifacts.
7. **Guardrail metric pairings** — Per primary metric, which counter-metric to check (e.g., volume↔margin, distribution↔fill rate).
8. **Anomaly detection thresholds** — What constitutes "normal" vs. "worth investigating" for key metrics.
9. **Investigation hypothesis library** — Common patterns and the hypotheses worth testing for each.
10. **Stakeholder map** — Who receives findings at what level of detail.
11. **Cross-domain connections** — How this domain intersects with others.
12. **Open data gaps** — What data would make this domain's analysis more powerful that isn't yet available.

Owner: Data Science team in partnership with business domain owner. Reviewed quarterly. Lives in `context/domains/`.

---

## Part 6: Orchestration Design

### Pipeline Composition

The Question Framer outputs a pipeline composition. The orchestrator reads it and executes the specified agents in the specified order with the specified skills loaded.

Composition follows a DAG with skip rules:

```python
# Pseudo-code for orchestrator logic
def execute_pipeline(framer_brief):
    pipeline = framer_brief['pipeline_composition']
    artifacts = {}
    
    for stage in pipeline:
        agent_name = stage['agent']
        skills = stage['skills']
        
        # Assemble prompt
        system_prompt = assemble_prompt(
            agent_md=load(f"agents/{agent_name}.md"),
            universal_skills=load_all("skills/universal/"),
            analytical_skills=[load(f"skills/analytical/{s}.md") for s in skills],
            domain_context=load_relevant_context(framer_brief),
        )
        
        # Build user message with prior artifacts
        user_message = construct_user_message(artifacts, stage)
        
        # Call API with budget check
        if budget_remaining() < estimated_cost(stage):
            return graceful_truncation(artifacts)
        
        result = claude_api_call(system_prompt, user_message)
        
        # Validate artifact schema
        artifact = parse_and_validate(result, expected_schema=stage['output_schema'])
        artifacts[agent_name] = artifact
        
        # Trace and log
        log_span(agent_name, system_prompt, user_message, artifact, cost, latency)
    
    return artifacts
```

### Inter-Agent Artifact Schemas

Each agent produces a JSON artifact with a defined schema. Schemas live in `orchestration/artifact-schemas.md`. The orchestrator validates each artifact against its schema before passing to the next stage. Validation failure triggers retry or graceful degradation.

### Session Memory (Interactive Mode)

For multi-turn conversations:
- Per-session conversation summary compressed and passed to Question Framer.
- "Established facts" working memory passed to all agents so they don't re-derive stable findings.
- Memory entries timestamped with data freshness — stale entries expire on data refresh.
- All memory operations logged for observability.

### Token Budget Management

- Question Framer sets pipeline budget based on complexity classification.
- Budget tracker monitors cumulative spend during pipeline execution.
- Hard cap triggers graceful truncation — Communication Agent renders partial result with explicit "analysis stopped at depth N" note.
- Per-run cost telemetry surfaces in observability dashboard.

### Observability

Three levels of telemetry:
- **Traces** — full pipeline run from input to output.
- **Spans** — each agent call, each skill load, each code execution, each memory operation.
- **Sessions** — multi-turn conversation context.

Every computed statistic carries metadata linking it to the exact code that produced it, the data slice it ran on, and the result. This is the audit trail.

### Failure Recovery

Failure modes and responses:
- **Code execution error** — retry once with exponential backoff. If still fails, log and continue with skill marked as failed.
- **Schema validation failure on artifact** — retry the agent call with a clarifying instruction. If still fails, degrade gracefully (Communication Agent notes the gap).
- **Single agent fails entirely** — skip-and-flag rather than hard-fail. Pipeline continues with available findings. Final output includes "partial results" notice.
- **Findings Validator fails** — do not silently render unvalidated findings. Render with explicit "validation could not be performed" caveat.
- **Memory retrieval returns wrong-entity result** — observability flags it; orchestrator's role is to surface, not silently use bad data.

### Prompt Injection Defense

For free-text columns in data:
- Data Retrieval Agent sanitizes content: strips system-prompt-mimicking patterns, escapes formatting characters.
- All downstream agents treat data values as data, never as instructions.
- Code execution environment is sandboxed with no outbound network access.
- No agent has write/update/delete capability against any data source.

### Lineage Tracking

Every rendered finding traces to:
- Source data (file or table reference)
- Query or load operation
- Transformation steps
- Statistics computed
- Code that computed them
- Agent that produced the claim

Stored as `lineage.json` artifact per pipeline run.

---

## Part 7: Production Concerns Coverage

| Concern | MVP Approach | Production Approach |
|---|---|---|
| Data access | Excel/CSV file upload | Cortex Analyst or pre-validated Snowflake views; semantic layer binding |
| Session memory | In-memory for active session | Persistent store (Redis or similar) |
| Token budgeting | Per-run hard caps in config | Per-user budgets, monthly limits, alerts |
| Observability | File-based span logging | OpenTelemetry to logging platform |
| Human-in-loop | Confidence-grade-triggered checkpoints, action card structure includes feedback fields | Recipient feedback captured and fed back into system; learning loop |
| Failure recovery | Retry + skip-and-flag + graceful degradation | Plus alerting and automatic incident logging |
| Lineage | `lineage.json` per run | Persistent lineage store; queryable audit log |
| Schema discovery | Manual domain context document creation | Periodic schema-diff with steward notifications |
| Prompt injection | Free-text sanitization, sandboxed code execution, read-only data access | Plus dedicated red-team testing |

---

## Part 8: MVP Scope

### What the MVP Demonstrates

**The core thesis: the future of how we embed data scientist level EDA across all teams with validated data domains.** This is not a tool that promises to find new dramatic insights every week. It is a tool with the rigor and intellectual honesty of a senior data analyst, applied at a scale and consistency humans cannot match. Sometimes that produces actionable findings. Sometimes it produces "nothing concerning, here's the descriptive summary." Both are valuable. The system that knows the difference is what we are building.

The CEO presentation needs to show:

1. **The system embeds analyst-level rigor in a repeatable, scalable form.** Computed statistical evidence, validated findings, appropriate caveats, confidence grades. This is what a senior analyst would produce — not what an LLM "thinks" the answer is.

2. **The system knows when to speak and when to stay quiet.** When data is unremarkable, it says so directly with a descriptive summary. When findings rise to action, it produces specific actionable recommendations. The discipline to distinguish the two is the product.

3. **The system surfaces what would otherwise stay hidden.** Insights buried in data nobody has time to comb through. Analyst time is the constraint, not analytical capability. The tool extends senior analyst rigor across domains and accounts that would never receive that attention otherwise.

4. **Actions are specific and executable when they appear.** "Call Account X about their Tuesday delivery — here's why" not "investigate further." The recipient knows exactly what to do.

5. **The system knows what it doesn't know.** Findings the validator can't confidently support get downgraded or filtered. The system is honest about uncertainty.

6. **Path to production is clear.** Same pipeline, real data through Snowflake/Cortex, automated weekly delivery. The MVP proves the analytical engine; production adds infrastructure, not capability.

**What the demo is not selling:** a tool that produces dramatic findings every week. That framing creates the wrong expectation and sets up a trap — if a future run is mundane, the tool looks broken. The framing is the opposite: a tool that produces *rigorous* output every week, and trusts the discipline of saying "nothing rose to action" when that's the right answer.

### MVP Mode Coverage

**Proactive Monitoring (the demo).** Runs against demo dataset with intentional anomalies generated from a real source structure. Produces action cards. The full pipeline executes the analytical engine and surfaces findings worth attention.

**Ad-hoc Execution of the Proactive Flow.** During the demo, Coby's boss can trigger an unscheduled run of the same proactive pipeline to demonstrate it's not pre-baked output. This is the only "interactive" element in MVP — it's the same pipeline, manually triggered.

Interactive Q&A mode (user types questions, system routes by complexity) is **deferred to a future phase**. Building two output modes (narrative + action card) and complexity routing adds significant scope for capability that isn't required for the demo. The MVP focuses on proving the analytical engine via proactive monitoring.

### MVP Inclusions

**Built in v1 by Claude Code:**
- All 10 agents with markdown definitions
- All 8 universal skills
- ~15 priority analytical skills covering demo scenarios:
  - correlation-analysis, group-comparison, cross-tabulation
  - clustering-algorithms, outlier-typology
  - stl-decomposition, change-point-detection, cohort-analysis
  - hypothesis-testing, effect-size-calculation, simpsons-paradox-check
  - benchmarking-methods, performance-gap-analysis, predictive-readiness-assessment
  - hypothesis-generation-from-data
- Both validation skills
- Proactive action card output skill (interactive narrative skill deferred)
- Insight-first formatting, confidence language, stakeholder communication, visualization recommendations skills
- CPG derived metrics skill
- One demo domain context document
- Orchestration engine with DAG composition, artifact validation, basic memory, observability, token telemetry
- Data generator that takes a source dataset and injects intentional anomalies
- Excel/CSV data loading with injection defenses
- Live demo mode with progressive console output

**Deferred to Phase 2:**
- Interactive Q&A mode (narrative output, complexity routing)
- Snowflake integration (Cortex Analyst path)
- Token budget enforcement (only telemetry in MVP)
- Real domain context documents beyond demo
- Causal inference DAG skill (basic statistical RCA in MVP)
- Distribution drift checks
- Schema discovery automation
- Persistent memory across sessions
- Recipient feedback capture loop
- Streamlit tool for domain owners
- Teams or Slack delivery channels (markdown report for MVP)

### Demo Scenarios

The data generator produces a demo dataset with intentional patterns covering the full range of analytical outcomes. Critically, this includes patterns that should NOT produce action cards — demonstrating the system's discipline in staying quiet when findings don't warrant action.

1. **Simple anomaly with clear cause** — Single account instock drop, root cause is order frequency change. Demonstrates the standard pipeline producing a high-confidence action card.

2. **Multi-factor anomaly** — Volume decline driven by combination of factors. Demonstrates analytical depth and decomposition with multiple contributing causes properly attributed.

3. **Data quality false alarm** — Apparent anomaly caused by a data refresh artifact, not real business event. Demonstrates the profiler correctly filtering noise so it doesn't reach the recipient.

4. **Cross-metric finding** — Volume up but margin down due to promotional mix. Demonstrates guardrail checking — a "good" finding gets paired with its counter-metric and the trade-off surfaces in the action card.

5. **Low-confidence finding** — Pattern that initially looks significant but validator downgrades. Demonstrates intellectual honesty — the system catches what doesn't survive scrutiny.

6. **Stable performance area** — A region, product line, or account segment where everything is operating within normal bounds. The system produces a descriptive summary noting stable performance rather than manufacturing a finding. **This scenario is the demo's most important demonstration of discipline.** It shows the tool respects the recipient's time by not crying wolf when nothing is wrong.

7. **Opportunity with predictive flag** — Performance gap where the pattern warrants a predictive model rather than immediate action. Demonstrates funnel to data science team — the system recognizes when an issue is bigger than a single action card and routes it appropriately.

### Live Demo Flow

The CEO presentation runs the full proactive monitoring pipeline in real-time. Coby's boss triggers an ad-hoc run to show it's not pre-baked:

```
[Console output shown live]

🔍 Reading scheduled prompt: "Weekly anomaly scan for CPG distribution data"
📊 Loading data: cpg_demo_data.csv (847 records, 12 columns)

🧠 Question Framer: Generating hypotheses from data patterns...
   → 6 candidate areas identified for investigation
   → Pipeline composition: full proactive monitoring

📋 Data Profiler: Assessing data quality...
   → Data ready with caveats: 2.1% null rate on volume field
   → Distribution analysis complete

🔬 Pattern Discoverer: Scanning for structure...
   → 3 candidate patterns identified for investigation

📈 Time Series Analyzer: Examining temporal dynamics...
   → 1 change point detected in Account 47's order frequency

🔍 Root Cause Investigator: Investigating findings...
   → Primary cause identified for Account 47 instock drop
   → Multi-factor analysis complete for regional pattern

🎯 Opportunity Identifier: Surfacing actions...
   → 3 immediate actions identified
   → 1 opportunity flagged for predictive modeling

✅ Findings Validator: Validating findings...
   → 3 findings graded A
   → 1 finding graded B with caveat
   → 1 finding graded D, filtered from output

📝 Communication Agent: Generating action cards...

═══════════════════════════════════════════════════════════
ACTION CARD #1
ALERT: Instock for [Product X] at [Account 47] dropped to 72%...
[Full action card displayed]
═══════════════════════════════════════════════════════════

[Additional action cards follow]

═══════════════════════════════════════════════════════════
WEEKLY SUMMARY
3 action cards generated for distribution
1 opportunity flagged for data science team review
2 patterns observed but did not rise to action level
═══════════════════════════════════════════════════════════

Total runtime: 2 min 47 sec
Total tokens consumed: [X] (estimated cost: $[Y])
```

The visible execution makes clear the system isn't a canned response — it's working through the problem methodically with traceable analytical steps. The cost telemetry at the end starts the conversation about production economics.

**The strongest moment in the demo is showing the system handle a stable performance area.** When the pipeline runs against the region or segment where nothing is wrong, the system produces a brief descriptive summary instead of inventing a finding. That demonstration — that the tool will not cry wolf and will not waste recipient attention — is what differentiates this from the AI tools the CEO has likely seen pitched before. Sequence the demo so this moment is featured, not buried.

---

## Part 9: Build and Review Approach

### Weekend Build (Coby + Claude Code)

Build the complete v1 structure in a fresh Claude Code session pointed at a new Azure DevOps repo. Feed Claude Code this document as the spec. Claude Code produces:

- Full folder structure
- All 10 agent markdown files
- All universal skills (8)
- All priority analytical skills (~15 for MVP demo scenarios)
- Both validation skills
- The proactive action card output skill (interactive narrative deferred — see scope adjustment below)
- CPG derived metrics skill and guardrail metric pairing skill
- Demo domain context document
- Orchestration engine (Python) with DAG composition, artifact validation, basic memory, observability, token telemetry (no budgeting enforcement yet)
- Data generator script that takes a source dataset and injects intentional anomalies across the demo scenarios
- Live demo runner with progressive console output

The build produces v1 of the complete system — functional but unrefined. Quality comes from the review-and-iterate phase.

### Team Review Phase (Next 2 Weeks)

The DS team's role is analytical rigor review, not initial authorship. Each team member takes ownership of reviewing and refining specific files:

**Analyst 1 reviews:**
- All 8 universal skills (analysis-design-spec, statistical-rigor, data-quality-standards, ethical-analysis, triangulation, close-the-loop, tracking-gaps, resistant-statistics)
- Both validation skills (statistical-revalidation, guardrail-pairing-check)
- Findings Validator agent
- CPG derived metrics skill

Focus: Is the analytical methodology rigorous? Are statistical standards applied correctly? Does the validator catch the right things?

**Analyst 2 reviews:**
- All analytical skills (correlation, clustering, time series, hypothesis testing, etc.)
- Pattern Discoverer, Relationship Analyzer, Time Series Analyzer, Root Cause Investigator agents
- Action card output skill

Focus: Are the analytical techniques described correctly? Are the methodology decisions sound? Does the action card format produce executable, specific recommendations?

**ML Engineering Manager reviews:**
- Orchestration code
- Artifact schemas
- Question Framer and Data Retrieval Agent
- Failure recovery logic

Focus: Is the application architecture sound? Are the agent boundaries respected in code? Does the pipeline degrade gracefully?

**Coby:**
- Demo domain context document and dummy data scenarios
- Opportunity Identifier agent (since it's the funnel to the DS team)
- Communication Agent (since it's the user-facing output)
- End-to-end testing and demo prep

### Review Mechanics

- Each reviewer makes edits via pull requests in Azure DevOps
- Coby merges after reviewing changes
- Weekly all-team sync to discuss patterns observed across reviews
- Test each agent's output against demo data after each round of edits to verify changes improve rather than degrade quality

The goal isn't perfection by demo day. The goal is good-enough v1 that demonstrates the analytical capability with clear paths for refinement based on observed behavior.

---

## Part 10: 3-Week Timeline

### Weekend (May 17-18): v1 Build

**Saturday:**
- Coby creates fresh Azure DevOps repo
- Coby starts Claude Code session pointed at the repo with this document as spec
- Claude Code generates full folder structure, all agent and skill markdowns, orchestration code, data generator, demo runner
- Coby reviews initial output for major gaps and reruns Claude Code as needed
- Generate demo dataset with intentional anomalies

**Sunday:**
- End-to-end smoke test against demo data
- Verify the pipeline runs without errors and produces output
- Document any major issues for team review
- Push v1 to repo and notify team to begin review Monday

**Deliverables:**
- [ ] Repo with full structure and all v1 files
- [ ] Working orchestration engine
- [ ] Demo data and generator script
- [ ] At least one successful end-to-end pipeline run
- [ ] Output: a first action card report against demo data

### Week 1: Team Review Begins (May 19 - May 23)

- Team members start reviewing assigned files
- Coby iterates on demo dataset and scenarios based on first pipeline outputs
- Daily quick check-ins to surface major issues
- First pass of pull request edits merged

**Deliverables:**
- [ ] First round of team edits incorporated
- [ ] Demo scenarios producing expected output types (anomalies detected, validator catching weak findings, action cards generating)
- [ ] Token consumption telemetry captured across runs (initial cost data)

### Week 2: Iteration (May 26 - May 30)

- Second round of team edits based on observed pipeline behavior
- Refinement of agent prompts where outputs are weak
- Coby refines Opportunity Identifier and Communication Agent based on demo flow
- Begin demo presentation prep

**Deliverables:**
- [ ] All v1 files reviewed by assigned team member
- [ ] Pipeline output quality at presentation level for primary demo scenarios
- [ ] Demo flow and talking points drafted

### Week 3: Polish and Demo (June 2 - June 6)

- Final refinements based on dry-run feedback
- Pre-record backup video of complete pipeline run in case of API issues during live demo
- Prepare cost data and analytical depth examples for CEO conversation

**Deliverables:**
- [ ] Demo-ready pipeline producing trustworthy action cards
- [ ] Backup recording in case of live failure
- [ ] CEO presentation materials with business case framing
- [ ] Captured token cost data to inform production planning

---

## Part 11: Path to Production

The MVP proves the architecture. Production deployment adds infrastructure, security, and scale.

| Component | MVP | Production |
|---|---|---|
| API access | Sandbox Anthropic key | Azure AI Foundry (Claude through Azure) |
| Data source | Excel/CSV upload | Snowflake via Cortex Analyst or validated views |
| Deployment | Local Python script | Azure-hosted backend (Web App or Container App) |
| Trigger | Manual or local cron | Azure Functions or Databricks scheduled job |
| Output delivery | Markdown report | Email, Teams message, webapp dashboard |
| Domain coverage | One demo domain | Multiple domains as data marts and context docs mature |
| Authentication | None | Microsoft Entra ID SSO |
| Security | Local file access | Service account with read-only Snowflake access; row-level security respected |
| Memory | In-process | Persistent (Cosmos DB or Redis) |
| Observability | File logs | OpenTelemetry to centralized logging |
| Cost tracking | Per-run | Per-user, per-domain, with budgets and alerts |
| Feedback loop | Action card structure only | Recipient feedback captured and fed back into system |
| Context maintenance | Manual markdown edits | Streamlit interface for domain owners |

Everything in the MVP (agent markdowns, skills, orchestration logic, artifact schemas, domain context structure) transfers directly. Production adds infrastructure, not analytical capability.

---

## Part 12: Open Questions and Decisions

These items need attention during implementation. Resolved decisions are noted; remaining items need attention during Week 1.

### Resolved

- **Interactive Q&A mode deferred.** MVP focuses on proactive monitoring only. Ad-hoc execution of the same proactive pipeline serves as the only "interactive" demo element. Question Framer's complexity routing logic and Communication Agent's narrative skill are simplified or deferred accordingly.

- **Token budgeting deferred.** Build telemetry to capture token consumption per run. No budget enforcement until real cost data informs realistic limits.

- **Data generator approach.** Build a script that takes a source dataset (clean structure with realistic dimensions) and injects intentional anomalies across the demo scenarios. This lets Coby control which scenarios surface and lets the team test the system against varied data shapes.

### Remaining

1. **API model selection per agent.** Opus for Root Cause Investigator, Findings Validator, Opportunity Identifier (high reasoning depth needed). Sonnet for Question Framer, Data Retrieval, Data Profiler, Communication Agent (lighter work). Confirm during Week 1 testing — may adjust based on output quality and cost.

2. **Demo data domain confirmation.** CPG sales and instock is the assumed default. Confirm during Week 1 that this is the right primary domain or whether a different domain better demonstrates the system's value.

3. **Demo recipient roles.** Action cards adapt to recipient role. Define 2-3 recipient personas (e.g., account manager, district manager, regional VP) and tailor action cards accordingly. The CEO sees the spread to understand who gets what.

4. **Live demo failure handling.** Pre-record a complete pipeline run as backup before the CEO meeting. Live API calls for a 3-week-old system in front of executives is high-risk. The recording is insurance; ideally not needed.

5. **Phase 2 priority.** After MVP, what's the most valuable addition: Snowflake integration, additional domains, recipient feedback loop, or interactive UI? Decide based on CEO and stakeholder reaction.

---

## Closing Note

This document is the blueprint. It is sufficient for:
- Your team to write the agent and skill markdowns with clear scope
- Claude Code to build the orchestration engine and supporting infrastructure
- You to demo the system in 3 weeks with confidence

The architecture is grounded in current best practice from production multi-agent systems (Anthropic, Microsoft Fabric, ThoughtSpot Spotter, AnswerRocket) and addresses the failure modes documented in recent multi-agent literature.

The system is designed to grow. The MVP proves the analytical engine with one domain on uploaded data. Each subsequent phase adds capability without changing the foundation: more domains by adding context documents, production data access by swapping the Data Retrieval Agent's implementation, more delivery channels by extending the Communication Agent's output skills, more analytical capabilities by adding skills (not agents).

The agents and skills as drafted are universal and domain-agnostic. Domain specificity lives in the context documents. This is the foundational design decision that lets the same system serve sales analytics, supply chain monitoring, finance reporting, and any future domain without redesign.
