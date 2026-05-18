"""Pydantic models for artifact schemas — runtime validation of inter-agent handoffs.

Mirrors `orchestration/artifact-schemas.md` v1.0. Forbidden patterns from that doc are
enforced where practical (no raw row dumps, no inline data values); some are enforced
by convention rather than schema constraint.

Schema strictness: unknown fields are allowed (agents may extend); known fields must
match types. This is the balance the design doc specifies.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Enums and aliases
# ---------------------------------------------------------------------------

AgentName = Literal[
    "question-framer",
    "data-retrieval-agent",
    "data-profiler",
    "relationship-analyzer",
    "pattern-discoverer",
    "time-series-analyzer",
    "root-cause-investigator",
    "opportunity-identifier",
    "findings-validator",
    "communication-agent",
]

ConfidenceGrade = Literal["A", "B", "C", "D", "F"]
CaveatSeverity = Literal["low", "medium", "high"]
RunStatus = Literal["ok", "degraded", "failed"]
OutputMode = Literal["narrative", "action-card", "descriptive-summary"]
ComplexityLevel = Literal["L1", "L2", "L3", "L4"]
InputMode = Literal["interactive", "proactive"]
InvestigationMode = Literal["diagnostic", "prescriptive", "both", "none"]
ReadinessAssessment = Literal["READY", "READY_WITH_CAVEATS", "INSUFFICIENT"]
CausationFlag = Literal["established_causal", "strong_correlation", "associational"]


class StrictModel(BaseModel):
    """Base model: extra fields permitted (per schemas §5); known fields validated."""

    model_config = ConfigDict(extra="allow", validate_assignment=True)


# ---------------------------------------------------------------------------
# Common types (artifact-schemas.md §3)
# ---------------------------------------------------------------------------


class TokenUsage(StrictModel):
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    total_cost_usd: float = 0.0


class LineageRef(StrictModel):
    source: str
    data_slice: str = Field(
        description="Filter expression. NEVER inline data values or ID lists. "
        "See pipeline-definitions.md §10."
    )
    code_ref: str
    notes: str | None = None


class Statistic(StrictModel):
    id: str
    metric: str
    value: float
    unit: str | None = None
    computation: str
    sample_size: int
    confidence_interval: dict[str, float] | None = None  # {"lower", "upper", "level"}
    p_value: float | None = None
    effect_size: dict[str, Any] | None = None  # {"kind", "value"}
    lineage: LineageRef


class Caveat(StrictModel):
    text: str
    severity: CaveatSeverity
    reason: str


class Hypothesis(StrictModel):
    id: str
    statement: str
    prior_strength: Literal["weak", "moderate", "strong"]
    testable_via: str
    rationale: str


class Finding(StrictModel):
    id: str
    claim: str
    evidence_statistic_ids: list[str]
    caveats: list[Caveat] = Field(default_factory=list)
    producing_agent: AgentName
    related_hypothesis_ids: list[str] | None = None


# ---------------------------------------------------------------------------
# Pipeline composition (§4.1)
# ---------------------------------------------------------------------------


class PipelineStageSingle(StrictModel):
    agent: AgentName
    skills: list[str] = Field(default_factory=list)


class PipelineStageParallel(StrictModel):
    parallel: list[PipelineStageSingle]


PipelineStage = Annotated[PipelineStageSingle | PipelineStageParallel, Field()]


# ---------------------------------------------------------------------------
# Per-agent payloads
# ---------------------------------------------------------------------------


class QuestionFramerPayload(StrictModel):
    input_mode: InputMode
    complexity_level: ComplexityLevel
    premises_verified: list[dict[str, Any]] = Field(default_factory=list)
    analytical_questions: list[str]
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    data_requirements: dict[str, Any]
    decision_context: str
    success_criteria: str
    pipeline_composition: list[PipelineStage]
    output_mode: OutputMode
    investigation_mode: InvestigationMode
    token_budget: int


class ColumnMetadata(StrictModel):
    name: str
    dtype: str
    null_count: int
    distinct_count: int
    is_free_text: bool


class ColumnSpec(StrictModel):
    name: str
    dtype: Literal["string", "integer", "float", "boolean", "datetime", "category"]
    nullable: bool


class DataRetrievalPayload(StrictModel):
    dataset_handle: str
    data_source_type: Literal["uploaded_file", "snowflake_view", "cortex_analyst"]
    source_reference: str
    schema_columns: list[ColumnSpec] = Field(alias="schema")
    row_count: int
    column_metadata: list[ColumnMetadata]
    free_text_columns_sanitized: list[str] = Field(default_factory=list)
    load_warnings: list[Caveat] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class DataProfilerPayload(StrictModel):
    readiness_assessment: ReadinessAssessment
    completeness: dict[str, dict[str, float | int]]
    freshness: dict[str, Any]
    grain: dict[str, Any]
    distributions: dict[str, dict[str, Any]]
    baselines: list[dict[str, str]] = Field(default_factory=list)
    quality_issues: list[Caveat] = Field(default_factory=list)
    data_integrity_risks: list[dict[str, Any]] = Field(default_factory=list)
    mandatory_caveats: list[Caveat] = Field(default_factory=list)
    notable_observations: list[str] = Field(default_factory=list)
    statistics: list[Statistic] = Field(default_factory=list)


class RelationshipAnalyzerPayload(StrictModel):
    relationships_examined: list[dict[str, Any]] = Field(default_factory=list)
    significant_correlations: list[Finding] = Field(default_factory=list)
    group_differences: list[Finding] = Field(default_factory=list)
    interaction_effects: list[Finding] = Field(default_factory=list)
    multiple_comparison_correction: dict[str, Any]
    notable_findings: list[Finding] = Field(default_factory=list)
    statistics: list[Statistic] = Field(default_factory=list)
    caveats: list[Caveat] = Field(default_factory=list)


class PatternDiscovererPayload(StrictModel):
    techniques_applied: list[
        Literal["clustering", "dimensionality_reduction", "outlier_characterization"]
    ] = Field(default_factory=list)
    clusters_identified: dict[str, Any] | None = None
    structural_outliers: list[Finding] = Field(default_factory=list)
    dimensionality_findings: dict[str, Any] | None = None
    generated_hypotheses: list[Hypothesis] = Field(default_factory=list)
    caveats: list[Caveat] = Field(default_factory=list)
    statistics: list[Statistic] = Field(default_factory=list)


class TimeSeriesAnalyzerPayload(StrictModel):
    decomposition: dict[str, Any] | None = None
    change_points: list[dict[str, Any]] = Field(default_factory=list)
    cohort_findings: list[Finding] = Field(default_factory=list)
    lag_relationships: list[dict[str, Any]] = Field(default_factory=list)
    stationarity_assessment: dict[str, Any] | None = None
    caveats: list[Caveat] = Field(default_factory=list)
    statistics: list[Statistic] = Field(default_factory=list)


class RootCauseInvestigatorPayload(StrictModel):
    anomaly_under_investigation: dict[str, Any]
    primary_root_cause: dict[str, Any] | None = None
    decomposition: list[dict[str, Any]] = Field(default_factory=list)
    hypotheses_tested: list[dict[str, Any]] = Field(default_factory=list)
    primary_drivers: list[Finding] = Field(default_factory=list)
    rejected_hypotheses: list[Hypothesis] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    analytical_caveats: list[Caveat] = Field(default_factory=list)
    statistics: list[Statistic] = Field(default_factory=list)


class OpportunityIdentifierPayload(StrictModel):
    performance_gaps: list[dict[str, Any]] = Field(default_factory=list)
    opportunity_areas: list[Finding] = Field(default_factory=list)
    intervention_recommendations: list[dict[str, Any]] = Field(default_factory=list)
    predictive_readiness_assessment: dict[str, Any]
    sensitivity_analysis: list[dict[str, Any]] = Field(default_factory=list)
    caveats: list[Caveat] = Field(default_factory=list)
    statistics: list[Statistic] = Field(default_factory=list)


class ReviewedFinding(StrictModel):
    finding_id: str
    finding_claim: str
    grade: ConfidenceGrade
    justification: str
    layer_results: dict[str, str]
    required_caveats: list[Caveat] = Field(default_factory=list)
    recommended_actions_for_investigator: list[str] = Field(default_factory=list)


class FindingsValidatorPayload(StrictModel):
    overall_assessment: str
    findings_review: list[ReviewedFinding] = Field(default_factory=list)
    cross_cutting_issues: list[dict[str, Any]] = Field(default_factory=list)
    guardrail_check_results: list[dict[str, Any]] = Field(default_factory=list)
    revalidation_summary: dict[str, Any]


class ActionCard(StrictModel):
    alert: str
    confidence: ConfidenceGrade
    why_it_matters: str
    root_cause: str
    recommended_action: str
    owner_role: str
    due: str
    follow_up_trigger: str
    caveats: list[Caveat] = Field(default_factory=list)
    source_finding_id: str


class CommunicationAgentPayload(StrictModel):
    output_mode: OutputMode
    rendered_output_markdown: str
    action_cards: list[ActionCard] = Field(default_factory=list)
    descriptive_summary: dict[str, Any] | None = None
    carried_caveats: list[Caveat] = Field(default_factory=list)
    follow_up_suggestions: list[str] = Field(default_factory=list)
    visualization_recommendations: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Envelope (§2)
# ---------------------------------------------------------------------------

# Map agent name -> payload class for runtime parsing
PAYLOAD_BY_AGENT: dict[AgentName, type[BaseModel]] = {
    "question-framer": QuestionFramerPayload,
    "data-retrieval-agent": DataRetrievalPayload,
    "data-profiler": DataProfilerPayload,
    "relationship-analyzer": RelationshipAnalyzerPayload,
    "pattern-discoverer": PatternDiscovererPayload,
    "time-series-analyzer": TimeSeriesAnalyzerPayload,
    "root-cause-investigator": RootCauseInvestigatorPayload,
    "opportunity-identifier": OpportunityIdentifierPayload,
    "findings-validator": FindingsValidatorPayload,
    "communication-agent": CommunicationAgentPayload,
}


class Artifact(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    agent: AgentName
    run_id: str
    stage_index: int
    produced_at: datetime
    duration_ms: int
    token_usage: TokenUsage
    status: RunStatus = "ok"
    status_notes: str | None = None
    payload: dict[str, Any]  # validated against the agent-specific schema separately

    @field_validator("status_notes")
    @classmethod
    def _notes_required_on_non_ok(cls, v: str | None, info: Any) -> str | None:
        # Can't easily access `status` here in v2 without context — caller validates.
        return v


def validate_payload(agent: AgentName, raw_payload: dict[str, Any]) -> BaseModel:
    """Validate a raw payload against the schema for the given agent.

    Raises pydantic.ValidationError on failure. The caller wraps in retry logic
    per failure-recovery.md §2.
    """
    cls = PAYLOAD_BY_AGENT[agent]
    return cls.model_validate(raw_payload)
