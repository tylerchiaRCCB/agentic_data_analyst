"""Pydantic models for artifact schemas — runtime validation of inter-agent handoffs.

Mirrors `orchestration/artifact-schemas.md` v1.0. Forbidden patterns from that doc are
enforced where practical (no raw row dumps, no inline data values); some are enforced
by convention rather than schema constraint.

Schema strictness: unknown fields are allowed (agents may extend); known fields must
match types. This is the balance the design doc specifies.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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

_CANONICAL_AGENTS: set[str] = {
    "question-framer", "data-retrieval-agent", "data-profiler",
    "relationship-analyzer", "pattern-discoverer", "time-series-analyzer",
    "root-cause-investigator", "opportunity-identifier",
    "findings-validator", "communication-agent",
}


def _canonicalize_dtype(dt: Any) -> str:
    """Map common pandas/numpy/python dtype strings to canonical ColumnSpec values.

    Canonical values: string | integer | float | boolean | datetime | category.
    """
    if not isinstance(dt, str):
        return "string"
    lower = dt.lower().strip()
    if lower in {"string", "integer", "float", "boolean", "datetime", "category"}:
        return lower
    # Pandas / numpy variants
    if lower in {"object", "str", "string_", "unicode", "u"} or lower.startswith(("str", "u")):
        return "string"
    if lower in {"int", "int8", "int16", "int32", "int64", "uint8", "uint16", "uint32", "uint64", "int_", "i", "uint"} or lower.startswith(("int", "uint", "i8", "i4", "i2", "i1")):
        return "integer"
    if lower in {"float16", "float32", "float64", "float_", "f", "double"} or lower.startswith(("float", "f4", "f8")):
        return "float"
    if lower in {"bool", "bool_", "boolean", "b"}:
        return "boolean"
    if lower.startswith(("datetime", "date", "timestamp", "m8", "<m8", ">m8", "datetime64")):
        return "datetime"
    if lower in {"category", "categorical"}:
        return "category"
    return "string"  # safe default


def normalize_agent_name(name: str) -> str:
    """Map common variants the model produces (e.g., trailing -agent on bare names,
    underscores instead of hyphens) to the canonical agent name. Returns the
    original name unchanged if no canonical match is found.
    """
    if name in _CANONICAL_AGENTS:
        return name
    candidates = [
        name,
        name.replace("_", "-").lower(),
        name.removesuffix("-agent") if name.endswith("-agent") else f"{name}-agent",
        name.replace("_", "-").lower().removesuffix("-agent"),
        f"{name.replace('_', '-').lower()}-agent",
    ]
    for c in candidates:
        if c in _CANONICAL_AGENTS:
            return c
    return name  # let Pydantic surface the issue if still invalid

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
    reason: str = ""

    @model_validator(mode="before")
    @classmethod
    def _normalize_caveat(cls, data: Any) -> Any:
        """Accept common variant field names agents produce in practice.

        Observed in real runs:
        - `text` aliased as `description`, `caveat`, `message`
        - `reason` aliased as `category`, `scope`, `resolution`, `cause`
        Defaults `reason` to "" if no variant supplied.
        """
        if not isinstance(data, dict):
            return data
        d = dict(data)

        if "text" not in d:
            for alt in ("description", "caveat", "message"):
                if alt in d:
                    d["text"] = d.pop(alt)
                    break

        if "reason" not in d:
            for alt in ("category", "scope", "resolution", "cause"):
                if alt in d:
                    d["reason"] = d.pop(alt)
                    break
            else:
                d["reason"] = ""

        # Coerce common severity variants to canonical low/medium/high
        sev = d.get("severity")
        if isinstance(sev, str) and sev not in {"low", "medium", "high"}:
            lower = sev.lower()
            if lower in {"critical", "urgent", "blocker", "severe", "blocking"}:
                d["severity"] = "high"
            elif lower in {"warning", "warn", "moderate"}:
                d["severity"] = "medium"
            elif lower in {"info", "informational", "minor", "trivial", "note"}:
                d["severity"] = "low"
            else:
                d["severity"] = "medium"

        return d


class Hypothesis(StrictModel):
    id: str
    statement: str
    prior_strength: Literal["weak", "moderate", "strong"] = "moderate"
    testable_via: str = ""
    rationale: str = ""

    @model_validator(mode="before")
    @classmethod
    def _normalize_hypothesis(cls, data: Any) -> Any:
        """Accept common variant field names and fill defaults for missing fields.

        Real outputs use: title/hypothesis/H/description for statement;
        prior/confidence/strength for prior_strength; method/test/approach
        for testable_via; reasoning/justification for rationale.
        """
        if not isinstance(data, dict):
            return data
        d = dict(data)

        # id from variants
        if "id" not in d:
            for alt in ("hypothesis_id", "h_id"):
                if alt in d:
                    d["id"] = str(d.pop(alt))
                    break
            else:
                d["id"] = "auto-" + str(abs(hash(json.dumps(d, sort_keys=True, default=str))))[:10]

        # statement from variants
        if "statement" not in d:
            for alt in ("title", "hypothesis", "description", "headline", "claim"):
                if alt in d:
                    d["statement"] = str(d.pop(alt))
                    break
            else:
                d["statement"] = "(no statement provided)"

        # prior_strength — coerce variants to canonical Literal
        ps = d.get("prior_strength")
        if ps is None:
            for alt in ("prior", "confidence", "strength", "prior_confidence"):
                if alt in d:
                    ps = d.pop(alt)
                    break
        if isinstance(ps, str):
            lower = ps.lower()
            if "strong" in lower or "high" in lower:
                d["prior_strength"] = "strong"
            elif "weak" in lower or "low" in lower:
                d["prior_strength"] = "weak"
            else:
                d["prior_strength"] = "moderate"
        elif ps is None:
            d["prior_strength"] = "moderate"

        # testable_via
        if "testable_via" not in d:
            for alt in ("method", "test", "approach", "test_method", "via"):
                if alt in d:
                    d["testable_via"] = str(d.pop(alt))
                    break
            else:
                d["testable_via"] = ""

        # rationale
        if "rationale" not in d:
            for alt in ("reasoning", "justification", "rationale_text", "explanation"):
                if alt in d:
                    d["rationale"] = str(d.pop(alt))
                    break
            else:
                d["rationale"] = ""

        return d


class Finding(StrictModel):
    id: str
    claim: str
    evidence_statistic_ids: list[str] = Field(default_factory=list)
    caveats: list[Caveat] = Field(default_factory=list)
    producing_agent: AgentName | None = None
    related_hypothesis_ids: list[str] | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_finding(cls, data: Any) -> Any:
        """Accept variant field names agents use in practice:
        - `id` aliased as outlier_id, finding_id, cluster_id, anomaly_id, pattern_id
        - `claim` aliased as description, statement, headline, finding, summary
        - `evidence_statistic_ids` aliased as statistic_ids, evidence_ids, supporting_statistics
        """
        if not isinstance(data, dict):
            return data
        d = dict(data)

        if "id" not in d:
            for alt in ("outlier_id", "finding_id", "cluster_id", "anomaly_id", "pattern_id"):
                if alt in d:
                    d["id"] = str(d.pop(alt))
                    break
            else:
                # Last-resort fallback — synthesize an id so the finding can survive
                d["id"] = "auto-" + str(abs(hash(json.dumps(d, sort_keys=True, default=str))))[:10]

        if "claim" not in d:
            for alt in ("description", "statement", "headline", "finding", "summary"):
                if alt in d:
                    d["claim"] = str(d.pop(alt))
                    break
            else:
                d["claim"] = "(no claim text provided)"

        if "evidence_statistic_ids" not in d:
            for alt in ("statistic_ids", "evidence_ids", "supporting_statistics"):
                if alt in d:
                    val = d.pop(alt)
                    d["evidence_statistic_ids"] = val if isinstance(val, list) else [str(val)]
                    break

        return d


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
    decision_context: str = ""
    success_criteria: str = ""
    pipeline_composition: list[PipelineStage]
    output_mode: OutputMode
    investigation_mode: InvestigationMode
    token_budget: int = 0
    # Optional richer form the model often produces — kept verbatim for downstream access
    success_definition: dict[str, Any] | None = None
    # Optional top-level run caveats the framer can surface (e.g., missing context)
    caveats: list[Any] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize_framer_input(cls, data: Any) -> Any:
        """Coerce the model's natural output shapes into the canonical schema.

        Real-world framer responses sometimes use richer or differently-named fields
        than the canonical schema; this normalizer makes the orchestrator robust to
        common variations without forcing the model into rigid formatting.
        """
        if not isinstance(data, dict):
            return data
        d = dict(data)

        # success_definition (rich object) vs. success_criteria (string)
        if "success_criteria" not in d and "success_definition" in d:
            sd = d["success_definition"]
            if isinstance(sd, dict):
                parts = [f"{k}: {v}" for k, v in sd.items()]
                d["success_criteria"] = "\n".join(parts)
            elif sd is not None:
                d["success_criteria"] = str(sd)

        # token_budget: accept int, dict {total, per_stage}, or numeric string.
        # Non-numeric values (e.g. "L4-default") gracefully default to 0.
        def _to_int(x: Any) -> int:
            try:
                return int(x)
            except (ValueError, TypeError):
                return 0

        tb = d.get("token_budget")
        if isinstance(tb, dict):
            total = tb.get("total")
            if isinstance(total, (int, float)):
                d["token_budget"] = int(total)
            elif total is None or isinstance(total, str):
                # No numeric total — sum per_stage if present, else 0
                per_stage = tb.get("per_stage") or {}
                summed = sum(v for v in per_stage.values() if isinstance(v, (int, float)))
                d["token_budget"] = int(summed)
            else:
                d["token_budget"] = 0
        elif isinstance(tb, str):
            d["token_budget"] = _to_int(tb)
        elif tb is None:
            d["token_budget"] = 0

        # pipeline_composition: coerce bare strings -> single stages, bare lists -> parallel groups
        # Also normalize any non-canonical agent names (e.g., "data-profiler-agent" -> "data-profiler").
        pc = d.get("pipeline_composition")
        if isinstance(pc, list):
            normalized: list[Any] = []
            for stage in pc:
                if isinstance(stage, str):
                    normalized.append({"agent": normalize_agent_name(stage), "skills": []})
                elif isinstance(stage, list):
                    parallel_stages = []
                    for sub in stage:
                        if isinstance(sub, str):
                            parallel_stages.append({"agent": normalize_agent_name(sub), "skills": []})
                        elif isinstance(sub, dict):
                            if "agent" in sub and isinstance(sub["agent"], str):
                                sub = {**sub, "agent": normalize_agent_name(sub["agent"])}
                            sub.setdefault("skills", [])
                            parallel_stages.append(sub)
                        else:
                            parallel_stages.append(sub)
                    normalized.append({"parallel": parallel_stages})
                elif isinstance(stage, dict):
                    # Already structured; ensure `skills` exists and normalize the agent name
                    if "agent" in stage and isinstance(stage["agent"], str):
                        stage = {**stage, "agent": normalize_agent_name(stage["agent"])}
                    if "agent" in stage and "skills" not in stage:
                        stage = {**stage, "skills": []}
                    normalized.append(stage)
                else:
                    # Already a Pydantic object or other typed value — pass through
                    normalized.append(stage)
            d["pipeline_composition"] = normalized

        # input_mode: coerce variants to canonical 'interactive' or 'proactive'
        im = d.get("input_mode")
        if isinstance(im, str) and im not in {"interactive", "proactive"}:
            lower = im.lower()
            if "schedul" in lower or "proactive" in lower or "monitor" in lower or "cron" in lower:
                d["input_mode"] = "proactive"
            else:
                d["input_mode"] = "interactive"

        # investigation_mode: coerce variants
        invm = d.get("investigation_mode")
        if isinstance(invm, str) and invm not in {"diagnostic", "prescriptive", "both", "none"}:
            lower = invm.lower()
            if "diagnostic" in lower and "prescriptive" in lower:
                d["investigation_mode"] = "both"
            elif "diagnostic" in lower or "diagnos" in lower:
                d["investigation_mode"] = "diagnostic"
            elif "prescriptive" in lower or "opportun" in lower:
                d["investigation_mode"] = "prescriptive"
            else:
                d["investigation_mode"] = "none"

        # output_mode: coerce model-invented hybrids to one of the three canonical modes.
        # Anything mentioning "action" maps to action-card (which already supports
        # mixed cards + descriptive-summary output). Anything mentioning "narrative"
        # maps to narrative. Otherwise default to descriptive-summary.
        om = d.get("output_mode")
        if isinstance(om, str) and om not in {"narrative", "action-card", "descriptive-summary"}:
            lower = om.lower()
            if "action" in lower or "card" in lower:
                d["output_mode"] = "action-card"
            elif "narrative" in lower:
                d["output_mode"] = "narrative"
            else:
                d["output_mode"] = "descriptive-summary"

        return d


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

    @model_validator(mode="before")
    @classmethod
    def _normalize_data_retrieval(cls, data: Any) -> Any:
        """Coerce common shapes agents emit:

        - `schema: ["account_id", "region", ...]` → list of ColumnSpec with defaults
          (dtype="string", nullable=True). Real type info usually lives in
          `column_metadata`; the schema field gets used as a shorthand.
        - `column_metadata: [{name, dtype, null_count, distinct_count, ...}]` —
          ensure `is_free_text` defaults to False if omitted.
        """
        if not isinstance(data, dict):
            return data
        d = dict(data)

        # Normalize schema: bare strings → ColumnSpec dicts; pandas dtypes → canonical
        sch = d.get("schema") or d.get("schema_columns")
        if isinstance(sch, list):
            normalized = []
            for item in sch:
                if isinstance(item, str):
                    normalized.append({"name": item, "dtype": "string", "nullable": True})
                elif isinstance(item, dict):
                    item = {**item}
                    item.setdefault("dtype", "string")
                    item.setdefault("nullable", True)
                    # Coerce common pandas/numpy/python dtype strings to canonical Literal values
                    item["dtype"] = _canonicalize_dtype(item.get("dtype", "string"))
                    normalized.append(item)
                else:
                    normalized.append(item)
            d["schema"] = normalized
            d.pop("schema_columns", None)

        # Normalize column_metadata: ensure is_free_text defaults to False; canonicalize dtype
        cm = d.get("column_metadata")
        if isinstance(cm, list):
            normalized_cm = []
            for item in cm:
                if isinstance(item, dict):
                    item = {**item}
                    item.setdefault("is_free_text", False)
                    item.setdefault("null_count", 0)
                    item.setdefault("distinct_count", 0)
                    # ColumnMetadata.dtype is a free-form str (not Literal), so canonicalization
                    # is not strictly required here — but doing it keeps downstream consistent.
                    item["dtype"] = _canonicalize_dtype(item.get("dtype", "string"))
                    normalized_cm.append(item)
                else:
                    normalized_cm.append(item)
            d["column_metadata"] = normalized_cm

        # Normalize distributions: list-of-objects with `metric` key -> dict keyed by metric
        dists = d.get("distributions")
        if isinstance(dists, list):
            as_dict: dict[str, Any] = {}
            for item in dists:
                if isinstance(item, dict):
                    key = item.get("metric") or item.get("column") or item.get("name")
                    if key:
                        as_dict[str(key)] = {k: v for k, v in item.items() if k not in {"metric", "column", "name"}}
            if as_dict:
                d["distributions"] = as_dict

        # Same for completeness: occasionally arrives as a list
        comp = d.get("completeness")
        if isinstance(comp, list):
            as_dict = {}
            for item in comp:
                if isinstance(item, dict):
                    key = item.get("column") or item.get("metric") or item.get("name")
                    if key:
                        as_dict[str(key)] = {k: v for k, v in item.items() if k not in {"metric", "column", "name"}}
            if as_dict:
                d["completeness"] = as_dict

        return d


class DataProfilerPayload(StrictModel):
    readiness_assessment: ReadinessAssessment
    # Inner value types are deliberately Any — agents may include None for
    # "no value to report" (e.g., null concentration when there are no nulls)
    # or richer structures (e.g., a "concentration" object listing where nulls cluster).
    completeness: dict[str, dict[str, Any]]
    freshness: dict[str, Any]
    grain: dict[str, Any]
    distributions: dict[str, dict[str, Any]]
    # baselines: agents commonly include numeric statistic refs, not just strings.
    baselines: list[dict[str, Any]] = Field(default_factory=list)
    quality_issues: list[Caveat] = Field(default_factory=list)
    data_integrity_risks: list[dict[str, Any]] = Field(default_factory=list)
    mandatory_caveats: list[Caveat] = Field(default_factory=list)
    notable_observations: list[str] = Field(default_factory=list)
    statistics: list[Statistic] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize_profiler(cls, data: Any) -> Any:
        """Coerce list-of-objects shapes back to dicts keyed by column/metric name.

        Agents commonly return completeness and distributions as a list of dicts
        rather than the canonical dict keyed by name. Each item has `column` /
        `metric` / `name` as its key — extract it and rebuild the canonical dict.
        """
        if not isinstance(data, dict):
            return data
        d = dict(data)

        for field in ("completeness", "distributions"):
            val = d.get(field)
            if isinstance(val, list):
                as_dict: dict[str, Any] = {}
                for item in val:
                    if isinstance(item, dict):
                        key = item.get("column") or item.get("metric") or item.get("name")
                        if key:
                            as_dict[str(key)] = {
                                k: v for k, v in item.items()
                                if k not in {"metric", "column", "name"}
                            }
                if as_dict:
                    d[field] = as_dict

        return d


class RelationshipAnalyzerPayload(StrictModel):
    relationships_examined: list[dict[str, Any]] = Field(default_factory=list)
    significant_correlations: list[Finding] = Field(default_factory=list)
    group_differences: list[Finding] = Field(default_factory=list)
    interaction_effects: list[Finding] = Field(default_factory=list)
    multiple_comparison_correction: dict[str, Any] = Field(default_factory=dict)
    notable_findings: list[Finding] = Field(default_factory=list)
    statistics: list[Statistic] = Field(default_factory=list)
    caveats: list[Caveat] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize_relationship_analyzer(cls, data: Any) -> Any:
        """If multiple_comparison_correction came as a descriptive string, wrap it."""
        if not isinstance(data, dict):
            return data
        d = dict(data)
        mcc = d.get("multiple_comparison_correction")
        if isinstance(mcc, str):
            lower = mcc.lower()
            method = "benjamini_hochberg" if "benjamini" in lower or "bh" in lower or "fdr" in lower else (
                "bonferroni" if "bonferroni" in lower else "unspecified"
            )
            d["multiple_comparison_correction"] = {
                "applied": True,
                "method": method,
                "rationale": mcc,
            }
        return d


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

    @model_validator(mode="before")
    @classmethod
    def _normalize_pattern_discoverer(cls, data: Any) -> Any:
        """Map verbose technique descriptions and method-summary dicts to canonical forms."""
        if not isinstance(data, dict):
            return data
        d = dict(data)

        # techniques_applied: verbose descriptions → canonical Literal values
        techs = d.get("techniques_applied")
        if isinstance(techs, list):
            normalized: list[str] = []
            for t in techs:
                if not isinstance(t, str):
                    continue
                lower = t.lower()
                if "cluster" in lower or "kmeans" in lower or "k-means" in lower or "dbscan" in lower or "hierarchical" in lower:
                    canonical = "clustering"
                elif "dimensionality" in lower or "pca" in lower or "umap" in lower or "tsne" in lower or "t-sne" in lower:
                    canonical = "dimensionality_reduction"
                elif "outlier" in lower or "isolation" in lower or "mahalanobis" in lower or "anomaly" in lower:
                    canonical = "outlier_characterization"
                else:
                    continue
                if canonical not in normalized:
                    normalized.append(canonical)
            d["techniques_applied"] = normalized

        # structural_outliers: if agent returned a method-summary dict instead of a list,
        # extract the embedded list of findings (or default to empty).
        so = d.get("structural_outliers")
        if isinstance(so, dict):
            extracted = None
            for key in ("outliers", "findings", "detected_outliers", "items", "results", "structural_outliers"):
                if key in so and isinstance(so[key], list):
                    extracted = so[key]
                    break
            d["structural_outliers"] = extracted if extracted is not None else []

        # Same defensive pattern for generated_hypotheses, in case it appears wrapped
        gh = d.get("generated_hypotheses")
        if isinstance(gh, dict):
            extracted = None
            for key in ("hypotheses", "items", "results", "generated_hypotheses"):
                if key in gh and isinstance(gh[key], list):
                    extracted = gh[key]
                    break
            d["generated_hypotheses"] = extracted if extracted is not None else []

        return d


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
    revalidation_summary: dict[str, Any] = Field(default_factory=dict)
    # Optional richer form the model often produces alongside the string assessment
    assessment_details: dict[str, Any] | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_validator(cls, data: Any) -> Any:
        """The validator often produces a rich object for overall_assessment
        (with findings_by_grade, summary, etc). Coerce to string while preserving
        the rich form in `assessment_details`."""
        if not isinstance(data, dict):
            return data
        d = dict(data)
        oa = d.get("overall_assessment")
        if isinstance(oa, dict):
            d["assessment_details"] = oa
            # Prefer an explicit "summary" or "assessment" field if present
            summary = oa.get("summary") or oa.get("assessment") or oa.get("overall")
            if summary:
                d["overall_assessment"] = str(summary)
            else:
                # Stringify the dict
                d["overall_assessment"] = json.dumps(oa, default=str)
        return d


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
    source_finding_id: str = ""

    @model_validator(mode="before")
    @classmethod
    def _normalize_action_card(cls, data: Any) -> Any:
        """Accept variant field names + coerce string caveats to Caveat objects."""
        if not isinstance(data, dict):
            return data
        d = dict(data)

        # owner_role <- owner
        if "owner_role" not in d and "owner" in d:
            d["owner_role"] = str(d.pop("owner"))

        # source_finding_id <- source / finding_id / first finding in finding_ids
        if "source_finding_id" not in d:
            for alt in ("source", "finding_id", "source_finding"):
                if alt in d:
                    d["source_finding_id"] = str(d.pop(alt))
                    break
            else:
                # finding_ids: list of upstream finding refs — take the first as the source
                fids = d.get("finding_ids")
                if isinstance(fids, list) and fids:
                    d["source_finding_id"] = str(fids[0])

        # confidence <- grade / validator_grade
        if "confidence" not in d:
            for alt in ("grade", "validator_grade"):
                if alt in d:
                    d["confidence"] = d[alt]  # leave original in place too — Literal will validate
                    break

        # why_it_matters <- why_this_matters / business_impact / impact_summary
        if "why_it_matters" not in d:
            for alt in ("why_this_matters", "business_impact", "impact_summary"):
                if alt in d:
                    d["why_it_matters"] = str(d.pop(alt))
                    break

        # alert <- headline / title / summary (the one-line attention-grabber)
        if "alert" not in d:
            for alt in ("headline", "title", "summary"):
                if alt in d:
                    d["alert"] = str(d.pop(alt))
                    break

        # follow_up_trigger: combine resolution + escalation variants if split
        if "follow_up_trigger" not in d:
            res = d.pop("follow_up_trigger_resolution", None)
            esc = d.pop("follow_up_trigger_escalation", None)
            parts = []
            if res:
                parts.append(f"Resolution: {res}")
            if esc:
                parts.append(f"Escalation: {esc}")
            if parts:
                d["follow_up_trigger"] = " ".join(parts)
            else:
                # Try other single-field aliases
                for alt in ("follow_up", "next_check", "resolution_trigger"):
                    if alt in d:
                        d["follow_up_trigger"] = str(d.pop(alt))
                        break

        # caveats: coerce strings to Caveat objects
        cv = d.get("caveats")
        if isinstance(cv, list):
            normalized = []
            for item in cv:
                if isinstance(item, str):
                    normalized.append({"text": item, "severity": "medium", "reason": ""})
                else:
                    normalized.append(item)
            d["caveats"] = normalized

        return d


class CommunicationAgentPayload(StrictModel):
    output_mode: OutputMode
    rendered_output_markdown: str
    action_cards: list[ActionCard] = Field(default_factory=list)
    descriptive_summary: dict[str, Any] | None = None
    carried_caveats: list[Caveat] = Field(default_factory=list)
    follow_up_suggestions: list[str] = Field(default_factory=list)
    visualization_recommendations: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize_comms_output_mode(cls, data: Any) -> Any:
        """Coerce hybrid output_mode strings (e.g. 'action-card+descriptive-summary')
        to one of the three canonical modes — same rule used on the framer.
        Also pull output_mode from run_metadata.output_mode if it's nested there."""
        if not isinstance(data, dict):
            return data
        d = dict(data)

        # If output_mode is missing at the top level, check run_metadata for it
        if "output_mode" not in d:
            rm = d.get("run_metadata") or d.get("metadata") or {}
            if isinstance(rm, dict) and "output_mode" in rm:
                d["output_mode"] = rm["output_mode"]

        # Coerce hybrid / non-canonical modes
        om = d.get("output_mode")
        if isinstance(om, str) and om not in {"narrative", "action-card", "descriptive-summary"}:
            lower = om.lower()
            if "action" in lower or "card" in lower:
                d["output_mode"] = "action-card"
            elif "narrative" in lower:
                d["output_mode"] = "narrative"
            else:
                d["output_mode"] = "descriptive-summary"
        elif om is None:
            # If still no output_mode and there are action_cards in the payload, default to action-card
            if d.get("action_cards"):
                d["output_mode"] = "action-card"
            elif d.get("descriptive_summary"):
                d["output_mode"] = "descriptive-summary"
            else:
                d["output_mode"] = "descriptive-summary"

        # Also ensure rendered_output_markdown exists — default to empty string if missing
        if "rendered_output_markdown" not in d:
            d["rendered_output_markdown"] = ""

        return d


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
