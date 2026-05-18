# Artifact Schemas

JSON schemas for the typed artifacts each agent produces. Every inter-agent handoff in the orchestrator passes through one of these schemas.

> **Framing reminder.** Several schemas below contain arrays that are explicitly allowed to be empty — `findings_review`, `opportunity_areas`, `change_points`, etc. An empty array means "we looked, and there was nothing of significance." It is not the same as a missing field, and the orchestrator must not treat it as an error. Schemas that allow empty arrays are marked `(can be empty — empty is valid)`.

This document uses a TypeScript-style notation for readability. The orchestrator validates against the canonical JSON Schema definitions generated from this file (location TBD in `src/orchestrator/schemas/`).

---

## 1. Conventions

- `?` after a field name means optional. All other fields are required.
- `[]` denotes an array.
- `string` fields that carry recipient-facing prose must be free-text English; fields that carry identifiers use kebab-case or snake_case as noted.
- Every artifact MUST include the envelope fields described in §2.

### 1.1 Forbidden patterns

- No numeric claim is allowed in a free-text field without an accompanying `Statistic` reference in the same artifact. Reviewers and validators must be able to trace every number to a computation.
- No field may carry "approximately," "roughly," "around" hedging *in lieu of* a confidence interval. Use the `Statistic.confidence_interval` field instead.
- No field permits "TBD," "see above," or similar placeholders. If the value is unknown, the field is either optional (and omitted) or required (and the stage fails).
- **No raw data values inlined in artifacts.** Artifacts carry metadata, summary statistics, and references — never row dumps, sample data, or inline value lists. Data is referenced by filter expression (e.g., `region == "Southeast"`) and resolved via code execution against `dataset_handle`. Deliberate small samples surfaced by an analytical agent (e.g., the 12 outlier accounts) are allowed in named-finding fields but never bulk-inlined into general-purpose fields like `column_metadata` or `data_slice`. See [pipeline-definitions.md](pipeline-definitions.md) §10.

---

## 2. Envelope (all artifacts)

Every artifact wraps the agent-specific payload in this envelope:

```ts
type Artifact<T> = {
  schema_version: "1.0",
  agent: AgentName,
  run_id: string,                  // shared across all stages of a pipeline run
  stage_index: number,             // position in the executed pipeline
  produced_at: string,             // ISO 8601 timestamp
  duration_ms: number,
  token_usage: TokenUsage,
  status: "ok" | "degraded" | "failed",
  status_notes?: string,           // required if status != "ok"
  payload: T,                      // agent-specific schema below
};

type TokenUsage = {
  input_tokens: number,
  output_tokens: number,
  cache_read_tokens?: number,
  cache_write_tokens?: number,
  total_cost_usd: number,
};

type AgentName =
  | "question-framer"
  | "data-retrieval-agent"
  | "data-profiler"
  | "relationship-analyzer"
  | "pattern-discoverer"
  | "time-series-analyzer"
  | "root-cause-investigator"
  | "opportunity-identifier"
  | "findings-validator"
  | "communication-agent";
```

---

## 3. Common types

These types appear in multiple agent schemas.

### 3.1 Statistic — every numeric claim carries lineage

```ts
type Statistic = {
  id: string,                      // unique within the artifact (e.g., "stat-007")
  metric: string,                  // human-readable name, e.g., "median weekly volume"
  value: number,
  unit?: string,                   // "cases", "%", "USD", "count", etc.
  computation: string,             // method, e.g., "median(weekly_volume) over Q1 2026"
  sample_size: number,
  confidence_interval?: { lower: number, upper: number, level: number },  // 0–1
  p_value?: number,
  effect_size?: { kind: string, value: number },  // kind: "cohens_d", "cramers_v", etc.
  lineage: LineageRef,
};

type LineageRef = {
  source: string,                  // dataset handle from Data Retrieval Agent
  data_slice: string,              // filter expression in pandas/sql syntax, e.g., `region == "Southeast" and week >= "2026-01-01"`. NEVER inline data values or ID lists. See pipeline-definitions.md §10.
  code_ref: string,                // pointer to executed code (e.g., "run/<run_id>/exec/<exec_id>")
  notes?: string,
};
```

Any agent producing a numeric claim must emit it as a `Statistic`. Free-text fields that reference a `Statistic` do so by `id`.

### 3.2 Caveat

```ts
type Caveat = {
  text: string,
  severity: "low" | "medium" | "high",  // high = must be surfaced to recipient verbatim
  reason: string,                   // why this caveat applies (data quality, methodology limit, scope)
};
```

The Communication Agent must carry forward every `severity: "high"` caveat into the recipient-facing output.

### 3.3 Hypothesis

```ts
type Hypothesis = {
  id: string,
  statement: string,                // testable, falsifiable form
  prior_strength: "weak" | "moderate" | "strong",
  testable_via: string,             // skill or technique to test it
  rationale: string,
};
```

### 3.4 Finding

```ts
type Finding = {
  id: string,
  claim: string,                    // one-sentence headline
  evidence_statistic_ids: string[], // refs to Statistic.id values in same artifact
  caveats: Caveat[],                // empty array allowed
  producing_agent: AgentName,
  related_hypothesis_ids?: string[],
};
```

### 3.5 ConfidenceGrade

```ts
type ConfidenceGrade = "A" | "B" | "C" | "D" | "F";
```

Grades **D** and **F** must not reach recipient-facing output. The Communication Agent filters them. See `Findings Validator` (§4.9) for grading criteria.

---

## 4. Agent payload schemas

### 4.1 Question Framer

```ts
type QuestionFramerPayload = {
  input_mode: "interactive" | "proactive",
  complexity_level: "L1" | "L2" | "L3" | "L4",
  premises_verified: { premise: string, verified: boolean, note?: string }[],
  analytical_questions: string[],
  hypotheses: Hypothesis[],            // can be empty for L1 lookups
  data_requirements: {
    domain: string,                    // resolves to context/domains/<domain>.md
    entities: string[],
    time_window?: { start?: string, end?: string, granularity?: string },
    metrics: string[],
  },
  decision_context: string,
  success_criteria: string,
  pipeline_composition: PipelineStage[],
  output_mode: "narrative" | "action-card" | "descriptive-summary",
  investigation_mode: "diagnostic" | "prescriptive" | "both" | "none",
  token_budget: number,
};

type PipelineStage =
  | { agent: AgentName, skills: string[] }               // single stage
  | { parallel: { agent: AgentName, skills: string[] }[] };  // parallel group
```

Notes:
- `pipeline_composition` is consumed verbatim by the orchestrator. The Question Framer is the only place pipeline shape is decided.
- `hypotheses` may be empty for descriptive L1/L2 questions.
- `premises_verified` records the Framer's check on assumptions embedded in the question ("share is declining" must be tested, not accepted).

### 4.2 Data Retrieval Agent

```ts
type DataRetrievalPayload = {
  dataset_handle: string,            // opaque ID downstream agents use to reference the data
  data_source_type: "uploaded_file" | "snowflake_view" | "cortex_analyst",
  source_reference: string,          // file path, view name, or query reference
  schema: ColumnSpec[],
  row_count: number,
  column_metadata: {
    name: string,
    dtype: string,
    null_count: number,
    distinct_count: number,
    is_free_text: boolean,
  }[],
  free_text_columns_sanitized: string[],   // column names that had injection-defense sanitization applied
  load_warnings: Caveat[],
};

type ColumnSpec = {
  name: string,
  dtype: "string" | "integer" | "float" | "boolean" | "datetime" | "category",
  nullable: boolean,
};
```

**Invariants:**
- This artifact contains metadata only. No raw data values appear in any field. `column_metadata` reports counts and types per column, not example values from the data.
- Sample-row inspection is on demand via code execution against `dataset_handle`, never through this artifact.
- `load_warnings` may describe rows by count, criterion, or filter expression (e.g., *"12 duplicate rows at the declared grain"*) but does not inline the rows themselves.
- If the dataset row count exceeds the threshold configured in `pipeline_config.yaml` (MVP default 5M), the agent must either auto-sample with a high-severity caveat in `load_warnings` (sampling method recorded) or fail the stage. See [pipeline-definitions.md](pipeline-definitions.md) §10.

### 4.3 Data Profiler

```ts
type DataProfilerPayload = {
  readiness_assessment: "READY" | "READY_WITH_CAVEATS" | "INSUFFICIENT",
  completeness: {                    // per column
    [column: string]: { null_rate: number, complete_rows: number }
  },
  freshness: {
    most_recent_record: string,      // ISO 8601
    expected_cadence?: string,
    days_stale?: number,
  },
  grain: {
    declared: string,                // e.g., "one row per (account, sku, week)"
    verified: boolean,
    duplicates_at_grain: number,
  },
  distributions: {                   // per metric of interest
    [metric: string]: {
      statistic_id: string,          // refs Statistic in `statistics` below
      shape: "normal" | "right_skewed" | "left_skewed" | "bimodal" | "long_tail" | "other",
      use_resistant_statistics: boolean,
    }
  },
  baselines: { metric: string, statistic_id: string }[],   // can be empty
  quality_issues: Caveat[],
  data_integrity_risks: {
    risk: "simpsons_paradox" | "survivorship_bias" | "selection_bias" | "other",
    columns_involved: string[],
    explanation: string,
  }[],
  mandatory_caveats: Caveat[],       // must be propagated downstream
  notable_observations: string[],    // can be empty
  statistics: Statistic[],
};
```

If `readiness_assessment` is `INSUFFICIENT`, downstream analytical agents must not run — the Question Framer's pipeline degrades to Communication Agent producing a "data not ready" descriptive summary. See [failure-recovery.md](failure-recovery.md) §3.

### 4.4 Relationship Analyzer

```ts
type RelationshipAnalyzerPayload = {
  relationships_examined: {
    pair: [string, string],                          // [variable_a, variable_b]
    technique: string,                                // e.g., "pearson_correlation"
    technique_justification: string,
    statistic_id: string,
    significant: boolean,                             // after multiple-comparison correction
  }[],
  significant_correlations: Finding[],                // can be empty — empty is valid
  group_differences: Finding[],                       // can be empty
  interaction_effects: Finding[],                     // can be empty
  multiple_comparison_correction: {
    applied: boolean,
    method?: "benjamini_hochberg" | "bonferroni" | "none",
    rationale: string,
  },
  notable_findings: Finding[],                        // can be empty
  statistics: Statistic[],
  caveats: Caveat[],
};
```

### 4.5 Pattern Discoverer

```ts
type PatternDiscovererPayload = {
  techniques_applied: ("clustering" | "dimensionality_reduction" | "outlier_characterization")[],
  clusters_identified: {
    method: string,
    n_clusters: number,
    validation_statistic_id: string,
    cluster_summaries: { cluster_id: string, size: number, characterization: string }[],
  } | null,                                           // null is valid — no clustering applied or no structure found
  structural_outliers: Finding[],                     // can be empty
  dimensionality_findings: {
    method: string,
    components_retained: number,
    variance_explained: number,
    component_interpretations: string[],
  } | null,                                           // null is valid
  generated_hypotheses: Hypothesis[],                 // can be empty
  caveats: Caveat[],
  statistics: Statistic[],
};
```

### 4.6 Time Series Analyzer

```ts
type TimeSeriesAnalyzerPayload = {
  decomposition: {
    method: "stl" | "classical" | "x13" | "other",
    period_detected: string,                          // e.g., "weekly", "monthly"
    trend_statistic_id: string,
    seasonal_strength_statistic_id: string,
    residual_anomaly_statistic_ids: string[],
  } | null,                                           // null is valid — not always applicable
  change_points: {
    timestamp: string,
    metric: string,
    statistic_id: string,
    method: "cusum" | "pelt" | "other",
    confidence: "low" | "medium" | "high",
  }[],                                                // can be empty — empty is valid
  cohort_findings: Finding[],                         // can be empty
  lag_relationships: {
    leading_variable: string,
    lagging_variable: string,
    optimal_lag: number,
    statistic_id: string,
  }[],                                                // can be empty
  stationarity_assessment: {
    method: "adf" | "kpss" | "both",
    stationary: boolean,
    statistic_ids: string[],
  } | null,
  caveats: Caveat[],
  statistics: Statistic[],
};
```

### 4.7 Root Cause Investigator

```ts
type RootCauseInvestigatorPayload = {
  anomaly_under_investigation: {
    description: string,
    statistic_id: string,              // refs the anomaly's quantification
  },
  primary_root_cause: {
    explanation: string,
    confidence: "low" | "medium" | "high",
    supporting_statistic_ids: string[],
    causation_vs_correlation: "established_causal" | "strong_correlation" | "associational",
  } | null,                            // null when no hypothesis survived testing — valid outcome
  decomposition: {
    component: string,
    contribution_pct: number,
    statistic_id: string,
  }[],
  hypotheses_tested: {
    hypothesis_id: string,
    outcome: "supported" | "rejected" | "inconclusive",
    test_statistic_id: string,
    notes: string,
  }[],
  primary_drivers: Finding[],          // can be empty if no driver survived testing
  rejected_hypotheses: Hypothesis[],   // surfaced explicitly per spec — failed hypotheses are not hidden
  open_questions: string[],
  analytical_caveats: Caveat[],
  statistics: Statistic[],
};
```

The `primary_root_cause: null` case is required and valid. When the data supports no confident causal claim, the investigator must say so rather than promote the strongest correlation to a "cause."

### 4.8 Opportunity Identifier

```ts
type OpportunityIdentifierPayload = {
  performance_gaps: {
    entity: string,                    // account, region, SKU, etc.
    metric: string,
    actual_statistic_id: string,
    benchmark_statistic_id: string,
    gap_size_statistic_id: string,
  }[],                                 // can be empty
  opportunity_areas: Finding[],        // can be empty — empty is valid
  intervention_recommendations: {
    opportunity_finding_id: string,
    action: string,                    // specific and executable
    estimated_impact_statistic_id?: string,
    owner_role: string,                // role, not named person at this stage
    follow_up_trigger: string,         // specific condition for follow-up
  }[],
  predictive_readiness_assessment: {
    candidates: {
      pattern_description: string,
      warrants_model: boolean,
      rationale: string,
      sample_size_adequate: boolean,
      feature_availability: "adequate" | "partial" | "insufficient",
    }[],                               // can be empty
  },
  sensitivity_analysis: {
    driver: string,
    outcome: string,
    sensitivity_statistic_id: string,
  }[],                                 // can be empty
  caveats: Caveat[],
  statistics: Statistic[],
};
```

### 4.9 Findings Validator

```ts
type FindingsValidatorPayload = {
  overall_assessment: string,
  findings_review: ReviewedFinding[],     // can be empty — empty is valid (no upstream findings to review)
  cross_cutting_issues: {
    issue: string,
    severity: "low" | "medium" | "high",
    affected_finding_ids: string[],
  }[],                                    // can be empty
  guardrail_check_results: {
    primary_metric: string,
    paired_metric: string,
    primary_direction: "up" | "down" | "flat",
    paired_direction: "up" | "down" | "flat",
    statistic_ids: string[],
    flag: "no_concern" | "trade_off_present" | "missing_data",
  }[],
  revalidation_summary: {
    findings_recomputed: number,
    discrepancies_found: number,
    discrepancy_details?: {
      finding_id: string,
      investigator_value: number,
      validator_value: number,
      explanation: string,
    }[],
  },
};

type ReviewedFinding = {
  finding_id: string,                     // refs the upstream Finding.id
  finding_claim: string,                  // restated for self-contained reading
  grade: ConfidenceGrade,
  justification: string,
  layer_results: {
    statistical_rigor: "pass" | "fail" | "partial",
    independent_recomputation: "match" | "mismatch" | "unable_to_compute",
    guardrail_check: "pass" | "trade_off" | "n/a",
    domain_plausibility: "plausible" | "implausible" | "n/a",
  },
  required_caveats: Caveat[],             // must be propagated to recipient
  recommended_actions_for_investigator: string[],   // if grade < A
};
```

Grading criteria (the Findings Validator agent file specifies the methodology; the schema enforces the labels):

| Grade | Meaning |
|---|---|
| A | Independently recomputed, statistically rigorous, guardrails clean, plausible. Recipient-ready. |
| B | As above with one caveat that must accompany the finding. Recipient-ready with caveat. |
| C | Preliminary signal; recipient sees it framed as such, or it is downgraded to descriptive summary. |
| D | Does not survive scrutiny. Filtered from recipient output; logged for audit. |
| F | Wrong, refuted by recomputation, or methodologically invalid. Filtered and logged with explanation. |

### 4.10 Communication Agent

```ts
type CommunicationAgentPayload = {
  output_mode: "narrative" | "action-card" | "descriptive-summary",
  rendered_output_markdown: string,         // the recipient-facing artifact
  action_cards: ActionCard[],               // can be empty — empty is valid
  descriptive_summary?: {
    period: string,
    areas_examined: string[],
    baselines_checked: string[],
    metrics_observed: { metric: string, statistic_id: string, status: "stable" | "elevated" | "depressed" }[],
    findings_that_would_have_warranted_action: string,   // what would have crossed the threshold
    conclusion: string,                                  // "nothing required attention this period," etc.
  },
  carried_caveats: Caveat[],                // every severity-high caveat from upstream
  follow_up_suggestions: string[],          // empty for proactive mode in MVP
  visualization_recommendations: {
    finding_id?: string,
    chart_type: string,
    rationale: string,
  }[],
};

type ActionCard = {
  alert: string,                            // headline
  confidence: ConfidenceGrade,
  why_it_matters: string,
  root_cause: string,                       // refs the diagnostic finding
  recommended_action: string,               // specific, executable — no "monitor" or "investigate further"
  owner_role: string,
  due: string,                              // ISO 8601 or relative ("within 5 business days")
  follow_up_trigger: string,
  caveats: Caveat[],                        // all severity-high caveats relevant to this card
  source_finding_id: string,
};
```

**Critical invariants:**
1. If `findings_review` from the Validator is empty (or contains only grade-D/F findings), `action_cards` MUST be empty and `descriptive_summary` MUST be populated.
2. The Communication Agent never invents a finding to fill `action_cards`. The schema permits empty, and the discipline requires it.
3. Every `Caveat` with `severity: "high"` from any upstream artifact must appear in either `action_cards[].caveats` or `carried_caveats`. Lost caveats are a validation failure.

---

## 5. Validation rules (orchestrator behavior)

The orchestrator validates each artifact against its schema before passing to the next stage. Validation failures are categorized:

- **Schema-shape failure** — missing required field, wrong type, malformed JSON. → retry per [failure-recovery.md](failure-recovery.md) §2.
- **Cross-field consistency failure** — e.g., `evidence_statistic_ids` references an id not present in the artifact's `statistics` array; or `action_cards` is non-empty when `findings_review` is empty. → retry once, then degrade.
- **Lineage gap** — a `Statistic` is missing `lineage.code_ref`. → retry once with a clarifying instruction.

Validation is strict but not pedantic: unknown fields are allowed (so agents can extend without breaking the orchestrator), but known fields must match the schema exactly.

---

## 6. Schema versioning

This document is schema version `1.0`. Breaking changes increment the major version; additive changes increment the minor. The `schema_version` field in every artifact is used by the orchestrator to select the correct validator at runtime.

The MVP runs entirely on `1.0`. Production migration policy is deferred to Phase 2.
