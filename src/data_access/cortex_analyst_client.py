"""Snowflake Cortex Analyst client — governed NL-to-SQL.

Cortex Analyst is Snowflake's natural-language-to-SQL agent that operates
against a YAML semantic model (defines tables, dimensions, measures, business
meaning). The LLM in Cortex Analyst generates governed SQL; our framework's
analytical agents reason over the resulting dataset.

This is THE production data path. Direct SQL from our framework is
discouraged (see snowflake_client.py docstring); Cortex Analyst is how
analytical questions become governed queries.

## Lifecycle

1. The Data Retrieval Agent receives an analytical question + dataset spec
   from the Question Framer.
2. It constructs a Cortex Analyst request with the question + semantic model
   reference.
3. Cortex Analyst returns the generated SQL + the result rows.
4. The Data Retrieval Agent returns the dataset slice to the framework
   (uploads to Anthropic Files API for code execution, populates the
   DataRetrievalPayload, records the generated SQL in lineage).

## Auth + endpoint

Cortex Analyst is exposed via Snowflake's REST API at:
    https://<account>.snowflakecomputing.com/api/v2/cortex/analyst/message

Auth uses Snowflake OAuth or key-pair JWT tokens (the same auth as
SnowflakeClient). The endpoint is currently in preview; check
https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst
for current GA status.

## Semantic model format

A YAML file describing tables, columns (dimensions vs measures), business
synonyms, and join keys. Path convention in this repo:

    context/semantic_models/<domain>.yaml

Example domain values: `commercial_sales`, `supply_chain`,
`walmart_in_store_execution`, `production_operations`. The team's BI
partners author and maintain these.

## Mock mode

When SNOWFLAKE_MOCK=1 or no creds are configured, this client returns
canned DataFrames so downstream code paths execute without real
warehouse access. Useful for scaffolding, dry-runs, and tests.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from src.data_access.snowflake_client import (
    NoCredentialsConfigured,
    SnowflakeClient,
    SnowflakeConfig,
)

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
SEMANTIC_MODELS_DIR = REPO_ROOT / "context" / "semantic_models"

# ---------------------------------------------------------------------------
# Question reframing — Cortex is the DATA layer, not the ANALYTICS layer
# ---------------------------------------------------------------------------
# When the pipeline sends an analytical question ("What factors drive FTPR?"),
# Cortex tries to answer it directly by pre-aggregating.  We need granular
# rows (e.g. store × week) so downstream agents can run correlations, change-
# point detection, etc.  These constants + helpers reframe analytical questions
# into data-retrieval requests that preserve grain.

# Keywords whose presence signals an analytical (not lookup) question.
_ANALYTICAL_SIGNALS = frozenset({
    "correlat", "relationship", "factor", "driv", "cause", "impact",
    "predict", "explain", "compar", "trend", "pattern", "anomal",
    "regress", "cluster", "segment", "outlier", "decompos", "forecast",
    "associat", "affect", "influenc", "contribut", "depend", "vary",
    "scatter", "distribut", "effect", "differ", "worst", "best",
})

# Keywords whose presence signals daily (not weekly) grain is needed.
_DAILY_GRAIN_SIGNALS = frozenset({
    "daily", "day-of-week", "day of week", "dayofweek", "intra-week",
    "intraweek", "per day", "each day", "by day", "weekday", "weekend",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
    "sunday",
})

# Minimum row count below which we consider the result over-aggregated for
# an analytical question.  42 DC-level rows can't support correlation analysis.
_MIN_ANALYTICAL_ROWS = 200

# Delivery coverage guardrail: historical baseline from verified diagnostics is
# ~563/623 active stores (~0.904). We do not hardcode that exact ratio in the
# client, but we reject clearly under-covered retrievals and retry once with a
# stricter SQL steering prompt.
_MIN_DELIVERY_COVERAGE_RATIO = 0.60
_DELIVERY_COVERAGE_WARNING_PREFIX = "DELIVERY_COVERAGE_LOW"

_TPO_SEMANTIC_MODELS = frozenset({"tpo_insights"})


def _is_analytical(question: str) -> bool:
    """Return True if the question is analytical rather than a simple lookup."""
    q = question.lower()
    return any(signal in q for signal in _ANALYTICAL_SIGNALS)


def _detect_grain(question: str) -> tuple[str, str]:
    """Detect whether the question needs daily or weekly grain.

    Returns (grain_hint, grain_description) tuple.
    """
    q = question.lower()
    if any(signal in q for signal in _DAILY_GRAIN_SIGNALS):
        return "STORE_NBR × DATE_SID (daily)", "one row per store per day"
    return "STORE_NBR × WEEK (weekly)", "one row per store per week"


def _reframe_for_retrieval(question: str, semantic_model_name: str) -> str:
    """Wrap an analytical question with grain-preservation instructions.

    The reframed question tells Cortex to act as a data-retrieval layer:
    return granular rows with raw numerators/denominators so that downstream
    statistical agents can do the actual analysis.

    Auto-detects daily vs weekly grain based on question keywords.
    """
    grain_hint, grain_desc = _detect_grain(question)

    # The raw OPD table is at UPC × Store × Date grain (millions of rows).
    # Both daily and weekly modes MUST aggregate across UPCs using GROUP BY
    # and SUM. Without this, Cortex returns the raw fact table.
    if "daily" in grain_hint.lower():
        group_by_clause = "GROUP BY STORE_NBR, DATE_SID"
        agg_example = (
            "SELECT STORE_NBR, DATE_SID, "
            "SUM(FTPR_NMRTR) AS ftpr_nmrtr, SUM(FTPR_DNMNTR) AS ftpr_dnmntr, "
            "SUM(NIL_PICK_QTY) AS nil_pick_qty ... "
            "FROM table "
            "GROUP BY STORE_NBR, DATE_SID"
        )
    else:
        group_by_clause = (
            "GROUP BY STORE_NBR, DATE_TRUNC('WEEK', TRY_TO_DATE(DATE_SID, 'YYYYMMDD'))"
        )
        agg_example = (
            "SELECT STORE_NBR, DATE_TRUNC('WEEK', TRY_TO_DATE(DATE_SID, 'YYYYMMDD')) AS week_start, "
            "SUM(FTPR_NMRTR) AS ftpr_nmrtr, SUM(FTPR_DNMNTR) AS ftpr_dnmntr, "
            "SUM(NIL_PICK_QTY) AS nil_pick_qty ... "
            "FROM table "
            "GROUP BY STORE_NBR, DATE_TRUNC('WEEK', TRY_TO_DATE(DATE_SID, 'YYYYMMDD'))"
        )

    return (
        f"DATA RETRIEVAL REQUEST — you MUST aggregate with GROUP BY, not return raw rows.\n\n"
        f"CRITICAL: The source table has one row per UPC × Store × Date. "
        f"You MUST use {group_by_clause} and SUM() all metric columns "
        f"to aggregate across UPCs. Do NOT select individual UPC rows. "
        f"The result should have {grain_desc}, NOT one row per UPC per store per day.\n\n"
        f"REQUIRED SQL PATTERN:\n{agg_example}\n\n"
        f"RULES:\n"
        f"- Return data at {grain_hint} grain ({grain_desc}).\n"
        f"- Use SUM() for all numeric measure columns: FTPR_NMRTR, FTPR_DNMNTR, "
        f"NIL_PICK_QTY, SCHDL_NIL_PICK_RATE_NMRTR, SCHDL_NIL_PICK_RATE_DNMNTR, etc.\n"
        f"- Include dimension columns in GROUP BY: STORE_NBR, and optionally "
        f"distribution center, category, brand as needed for the question.\n"
        f"- Do NOT return raw UPC-level rows — the result must be under 100,000 rows.\n"
        f"- Do NOT compute correlations, averages, or summary statistics.\n"
        f"- Apply date filters and exclude sentinel values (STORE_NBR != 9999).\n\n"
        f"QUESTION CONTEXT (what the analyst wants to explore — retrieve the "
        f"data they need, do not answer it):\n{question}"
    )


def _is_delivery_related(question: str) -> bool:
    """Return True when the question appears to require delivery metrics."""
    q = question.lower()
    return "delivery" in q or "delivered" in q


def _is_tpo_target(semantic_model_name: str, semantic_view: str | None) -> bool:
    """Return True when request targets the TPO semantic domain."""
    if semantic_model_name.strip().lower() in _TPO_SEMANTIC_MODELS:
        return True
    if not semantic_view:
        return False

    sv = semantic_view.upper()
    return "TPO_ANAPLAN_ANALYSIS" in sv or "TPO_" in sv


# ---------------------------------------------------------------------------
# Schema-driven retrieval — generic, works for any domain
# ---------------------------------------------------------------------------

def _load_semantic_model_spec(semantic_model_name: str) -> dict | None:
    """Load the semantic model YAML and return its parsed dict, or None."""
    model_path = SEMANTIC_MODELS_DIR / f"{semantic_model_name}.yaml"
    if not model_path.exists():
        # Try with hyphens/underscores swapped
        alt = semantic_model_name.replace("-", "_")
        model_path = SEMANTIC_MODELS_DIR / f"{alt}.yaml"
    if not model_path.exists():
        return None
    try:
        import yaml
        with model_path.open() as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def _build_schema_driven_prompt(spec: dict, question: str) -> str | None:
    """Build a retrieval prompt from a semantic model YAML.

    For small/medium models (e.g. TPO ~136K rows at week × account × PPG grain),
    requests ALL dimensions and measures at the model's grain.

    For large models where the raw grain is very fine (e.g. UPC × Store × Day =
    millions of rows), defers to Cortex's SQL generation guided by the model's
    own description and granularity rules. The prompt still requests all measures
    but lets the model description control the GROUP BY grain.
    """
    tables = spec.get("tables", [])
    if not tables:
        return None
    table = tables[0]

    dimensions = table.get("dimensions", [])
    time_dims = table.get("time_dimensions", [])
    measures = table.get("measures", []) or table.get("facts", [])

    if not dimensions and not measures:
        return None

    # Detect large/fine-grain models by checking for signals in the description
    model_desc = (spec.get("description", "") + " " + table.get("description", "")).lower()
    is_large_grain = any(signal in model_desc for signal in [
        "upc ×", "upc x", "sku ×", "sku x",
        "daily", "per day", "per date",
        "millions", "store × date", "store x date",
    ])

    dim_names = [d["name"] for d in dimensions if d.get("name")]
    time_dim_names = [d["name"] for d in time_dims if d.get("name")]
    measure_names = [m["name"] for m in measures if m.get("name")]

    # Skip dimensions that are known to be 100% null
    skip_dims = set()
    for d in dimensions:
        if d.get("sample_values") == [] and "null" in d.get("description", "").lower():
            skip_dims.add(d["name"])

    active_dims = [d for d in dim_names if d not in skip_dims]
    measure_bullet = "\n".join(f"- {m}" for m in measure_names)

    if is_large_grain:
        # Large model: explicitly tell Cortex to aggregate to a manageable grain.
        # Extract grain hint from model description if available.
        grain_hint = ""
        for pattern in [
            r"(?:return|aggregate|group).*?at\s+(?:the\s+)?(\w+\s*[×x]\s*\w+(?:\s*[×x]\s*\w+)*)\s+(?:level|grain)",
            r"(\w+\s*[×x]\s*\w+(?:\s*[×x]\s*\w+)*)\s+(?:level|grain)",
        ]:
            import re as _re
            m = _re.search(pattern, model_desc, _re.IGNORECASE)
            if m:
                grain_hint = m.group(1).strip()
                break

        if not grain_hint:
            # Default: aggregate to week level by dropping the finest time dimension
            grain_hint = "weekly (aggregate daily rows to week level)"

        # Collect key dimensions from ALL tables (including bridge/dimension tables)
        # so Cortex joins them in even when aggregating.
        bridge_dims: list[str] = []
        seen_dims: set[str] = set()
        for t in tables[1:]:
            for d in t.get("dimensions", []):
                dname = d.get("name", "")
                if dname and dname not in skip_dims and dname not in seen_dims \
                        and "join" not in d.get("description", "").lower()[:30]:
                    bridge_dims.append(dname)
                    seen_dims.add(dname)

        bridge_bullet = ""
        if bridge_dims:
            bridge_bullet = (
                f"\nINCLUDE THESE DIMENSIONS FROM RELATED TABLES (join as needed):\n"
                + "\n".join(f"- {d}" for d in bridge_dims[:15])  # cap at 15
                + "\n"
            )

        return (
            f"DATA RETRIEVAL REQUEST — aggregate to a manageable grain.\n\n"
            f"You are a data-retrieval layer. The underlying table has millions of rows "
            f"at fine grain. You MUST aggregate to a coarser grain before returning.\n\n"
            f"REQUIRED AGGREGATION GRAIN: {grain_hint}\n"
            f"- Convert daily dates to WEEK (e.g., DATE_TRUNC('WEEK', date_column)) and "
            f"GROUP BY the week, NOT the individual date.\n"
            f"- Do NOT group by individual UPC/SKU/item unless the question specifically "
            f"asks about a specific product. Group by category or brand instead.\n"
            f"- Target fewer than 500,000 rows in the result.\n\n"
            f"MANDATORY MEASURES (include in SELECT as SUM aggregates):\n{measure_bullet}\n"
            f"{bridge_bullet}\n"
            f"RULES:\n"
            f"- JOIN to related/bridge tables to include attribution dimensions.\n"
            f"- Include numerators AND denominators for rate metrics.\n"
            f"- Do NOT pre-compute rankings, top-N, or ORDER BY ... LIMIT.\n"
            f"- Apply date filters ONLY if the question explicitly requests a time range.\n\n"
            f"QUESTION CONTEXT (what the analyst wants to explore):\n"
            f"{question}"
        )

    # Small/medium model: request full grain with all dimensions
    all_group_by = active_dims + time_dim_names
    dim_bullet = "\n".join(f"- {d}" for d in active_dims)
    time_bullet = "\n".join(f"- {d}" for d in time_dim_names)
    group_by_list = ", ".join(all_group_by)

    return (
        f"DATA RETRIEVAL REQUEST — return the FULL dataset, do NOT pre-answer the question.\n\n"
        f"You are a data-retrieval layer. The question below is context for what the analyst "
        f"wants to explore — your job is to return granular rows, not to answer the question.\n\n"
        f"MANDATORY GRAIN: GROUP BY {group_by_list}\n\n"
        f"MANDATORY DIMENSIONS (include in SELECT and GROUP BY):\n{dim_bullet}\n\n"
        f"MANDATORY TIME DIMENSIONS (include in SELECT and GROUP BY):\n{time_bullet}\n\n"
        f"MANDATORY MEASURES (include in SELECT as aggregates):\n{measure_bullet}\n\n"
        f"RULES:\n"
        f"- Return ALL rows — do NOT filter to entities mentioned in the question.\n"
        f"- Do NOT pre-compute rankings, top-N, or ORDER BY ... LIMIT.\n"
        f"- Do NOT omit dimensions or measures not mentioned in the question.\n"
        f"- One row per combination of the GROUP BY dimensions above.\n"
        f"- Apply date filters ONLY if the question explicitly requests a specific time range.\n\n"
        f"QUESTION CONTEXT (what the analyst wants to explore — retrieve the data, do not answer it):\n"
        f"{question}"
    )


def _schema_driven_warnings(spec: dict, df: pd.DataFrame) -> list[str]:
    """Check retrieved DataFrame against the semantic model spec for missing columns."""
    if not spec or not spec.get("tables"):
        return []
    table = spec["tables"][0]
    cols = {str(c).upper() for c in df.columns}

    expected_dims = {d["name"].upper() for d in table.get("dimensions", []) if d.get("name")}
    expected_measures = {m["name"].upper() for m in table.get("measures", []) if m.get("name")}
    expected_time = {d["name"].upper() for d in table.get("time_dimensions", []) if d.get("name")}

    # Normalize: Cortex may alias names (e.g. fiscal_year vs YEAR)
    # Check using the name from the model as-is
    all_expected = expected_dims | expected_measures | expected_time
    missing = all_expected - cols
    if not missing:
        return []

    return [
        f"SCHEMA_DRIVEN_MISSING_COLUMNS: {len(missing)} of {len(all_expected)} "
        f"expected columns missing from retrieval: {', '.join(sorted(missing))}. "
        f"Cortex may have aggregated away dimensions or omitted measures not "
        f"mentioned in the question."
    ]


def _tpo_context_guardrail() -> str:
    """Override Cortex retrieval for TPO: always return the full dimension + measure set.

    Cortex Analyst tries to answer the question directly by pre-aggregating.
    We need granular rows at ACCOUNT × PPG × EVEN_OFFER_STANDARD × WEEK grain
    so downstream analytical agents can do their own analysis.
    """
    return (
        "TPO DATA RETRIEVAL OVERRIDE — ignore the question's apparent scope and return "
        "the FULL dataset at the grain specified below. The question is context for what "
        "the analyst wants to explore, NOT a query to pre-answer.\n\n"
        "MANDATORY GRAIN: GROUP BY account, ppg, even_offer_standard, fiscal_year, week_number, promo_week_start\n\n"
        "MANDATORY DIMENSIONS (all must appear in SELECT and GROUP BY):\n"
        "- ACCOUNT\n"
        "- PPG\n"
        "- EVEN_OFFER_STANDARD\n"
        "- YEAR (alias as FISCAL_YEAR)\n"
        "- WEEK_NUM (alias as WEEK_NUMBER)\n"
        "- TRY_TO_DATE(PROMO_WEEK_START) AS PROMO_WEEK_START\n"
        "- HOLIDAYS (alias as HOLIDAY)\n"
        "- EDV (alias as EDV_FLAG) — if not available, include CAST(FALSE AS BOOLEAN) AS EDV_SCOPE_APPLIED\n"
        "- IN_AD\n"
        "- DIGITAL_DEAL\n"
        "- ACCELERATION\n"
        "- FLAVOR_SEGMENTATION\n\n"
        "MANDATORY MEASURES (all must appear in SELECT as SUM aggregates):\n"
        "- retail_units\n"
        "- base_retail_units\n"
        "- incremental_retail_units\n"
        "- unit_lift_rate\n"
        "- percent_lift\n"
        "- dnnsi\n"
        "- dngp\n\n"
        "RULES:\n"
        "- Do NOT pre-filter to only the entities mentioned in the question. Return ALL accounts, ALL PPGs.\n"
        "- Do NOT pre-answer the question (no ORDER BY ... LIMIT, no top-N, no pre-computed rankings).\n"
        "- Do NOT omit dimensions or measures not mentioned in the question.\n"
        "- The result should have one row per ACCOUNT × PPG × OFFER × WEEK combination.\n"
        "- Apply no date filter unless the question explicitly requests a specific fiscal year.\n"
    )


def _tpo_context_warnings(df: pd.DataFrame) -> list[str]:
    """Return warnings for missing TPO context columns in retrieved output."""
    cols = {str(c).upper() for c in df.columns}
    warnings: list[str] = []

    has_fiscal_year = "FISCAL_YEAR" in cols or "YEAR" in cols
    has_week = "WEEK_NUM" in cols or "WEEK_NUMBER" in cols
    has_week_start = "PROMO_WEEK_START" in cols
    has_edv_context = "EDV" in cols or "EDV_FLAG" in cols or "EDV_SCOPE_APPLIED" in cols

    if not has_fiscal_year or not has_week or not has_week_start:
        warnings.append(
            "TPO_CONTEXT_MISSING_TIME_COLUMNS: expected fiscal year/week context "
            "(YEAR or FISCAL_YEAR, WEEK_NUM or WEEK_NUMBER, PROMO_WEEK_START)."
        )
    if not has_edv_context:
        warnings.append(
            "TPO_CONTEXT_MISSING_EDV_COLUMNS: expected EDV_FLAG/EDV or EDV_SCOPE_APPLIED "
            "to preserve promo-scope provenance."
        )
    if "ACCOUNT" not in cols:
        warnings.append("TPO_CONTEXT_MISSING_ACCOUNT: ACCOUNT dimension not in retrieved columns.")
    if "PPG" not in cols:
        warnings.append("TPO_CONTEXT_MISSING_PPG: PPG dimension not in retrieved columns.")
    if "DNNSI" not in cols:
        warnings.append("TPO_CONTEXT_MISSING_DNNSI: DNNSI measure not in retrieved columns.")
    if "DNGP" not in cols:
        warnings.append("TPO_CONTEXT_MISSING_DNGP: DNGP measure not in retrieved columns.")

    return warnings


def _delivery_retry_reframe(question: str) -> str:
    """Stricter second-pass delivery guidance when coverage looks implausibly low."""
    return (
        "DELIVERY COVERAGE RETRY — previous SQL under-covered delivery-active stores.\n\n"
        "MANDATORY LOGIC:\n"
        "- Build delivery_active_week_flag as:\n"
        "  MAX(COALESCE(IS_DELIVERY_ACTIVE_WEEK, CASE WHEN TOTAL_DELIVERED_QTY > 0 OR DELIVERY_STOP_COUNT > 0 THEN 1 ELSE 0 END))\n"
        "  at STORE_NBR × WEEK grain.\n"
        "- Aggregate across UPC rows first (SUM metrics, MAX activity flag).\n"
        "- Do not group by raw delivery fact columns after computing the weekly flag.\n"
        "- Exclude sentinel stores (STORE_NBR != 9999).\n"
        "- Return weekly store-level rows with the delivery_active_week_flag available for downstream profiling.\n\n"
        f"QUESTION CONTEXT:\n{question}"
    )


def _delivery_coverage_stats(df: pd.DataFrame) -> tuple[int, int, float] | None:
    """Compute delivery active-store coverage from returned data when possible."""
    cols = {str(c).upper(): c for c in df.columns}
    store_col = cols.get("STORE_NBR")
    if store_col is None or df.empty:
        return None

    delivery_flag_col = cols.get("IS_DELIVERY_ACTIVE_WEEK")
    delivered_qty_col = cols.get("TOTAL_DELIVERED_QTY")
    stop_count_col = cols.get("DELIVERY_STOP_COUNT")
    if delivery_flag_col is None and delivered_qty_col is None and stop_count_col is None:
        return None

    local = df.copy()
    active_series = pd.Series([False] * len(local), index=local.index)

    if delivery_flag_col is not None:
        active_series = active_series | local[delivery_flag_col].fillna(0).astype(float).gt(0)
    if delivered_qty_col is not None:
        active_series = active_series | local[delivered_qty_col].fillna(0).astype(float).gt(0)
    if stop_count_col is not None:
        active_series = active_series | local[stop_count_col].fillna(0).astype(float).gt(0)

    local["__delivery_active"] = active_series
    by_store = local.groupby(store_col, dropna=True)["__delivery_active"].max()
    total = int(by_store.shape[0])
    active = int(by_store.sum())
    ratio = (active / total) if total else 0.0
    return active, total, ratio


@dataclass
class CortexAnalystResponse:
    """Normalized Cortex Analyst response.

    `generated_sql` is recorded in lineage. `dataframe` is what flows into
    the framework as the dataset slice. `warnings` carries any data quality
    flags Cortex emitted.
    """

    generated_sql: str
    dataframe: pd.DataFrame
    rows_returned: int
    semantic_model: str
    request_id: str
    warnings: list[str]
    is_mock: bool = False


class CortexAnalystClient:
    """Wrapper for Snowflake Cortex Analyst's NL-to-SQL REST API."""

    def __init__(self, snowflake: SnowflakeClient | None = None) -> None:
        try:
            self._snowflake = snowflake or SnowflakeClient()
        except NoCredentialsConfigured:
            # Surface a clearer error with the Cortex-specific framing
            raise NoCredentialsConfigured(
                "CortexAnalystClient requires Snowflake credentials. Configure the "
                "SNOWFLAKE_* env vars (typically from Azure Key Vault) or enable "
                "SNOWFLAKE_MOCK=1 for scaffolding mode."
            ) from None

    @property
    def mock_mode(self) -> bool:
        return self._snowflake.mock_mode

    def ask(
        self,
        *,
        question: str,
        semantic_model: str,
        semantic_view: str | None = None,
        limit: int | None = 1_000_000,
        query_timeout_seconds: int = 180,
    ) -> CortexAnalystResponse:
        """Submit a natural-language analytical question to Cortex Analyst.

        Parameters:
          question:        the analytical question (e.g. "weekly fill rate by DC
                           for the past 13 weeks").
          semantic_model:  the semantic model name (e.g. "supply_chain"). Used
                           as a label and to locate the YAML when sending inline.
          semantic_view:   fully-qualified semantic view reference
                           (e.g. "CCB_DATASCIENCE_DEV.WALMART_OPD.WALMART_OPD").
                           When provided, the API uses the server-side view
                           instead of sending YAML inline.
          limit:           row limit to apply (caps cost + token use downstream).
          query_timeout_seconds: max seconds for the generated SQL to execute
                           before Snowflake kills it. Prevents runaway full-table
                           scans. Default 60s.

        Returns CortexAnalystResponse with the generated SQL, the resulting
        DataFrame, and any quality warnings.

        Raises NoCredentialsConfigured / SnowflakeNotInstalled in real mode if
        the warehouse isn't reachable. In mock mode, returns canned data based
        on the semantic_model name.
        """
        if self.mock_mode:
            return self._mock_response(question, semantic_model, limit)

        # ---- Schema-driven data retrieval ----
        # Try to load the semantic model YAML and build a deterministic
        # retrieval prompt that requests ALL dimensions and measures.
        # This prevents Cortex from pre-answering the question.
        spec = _load_semantic_model_spec(semantic_model)
        schema_prompt = _build_schema_driven_prompt(spec, question) if spec else None
        analytical = _is_analytical(question)
        is_tpo = _is_tpo_target(semantic_model, semantic_view)

        if schema_prompt:
            # Schema-driven: use the full-schema prompt regardless of question
            effective_question = schema_prompt
            logger.info("Using schema-driven retrieval for model=%s", semantic_model)
        elif analytical:
            # Fallback: generic reframing for domains without a YAML spec
            effective_question = _reframe_for_retrieval(question, semantic_model)
        else:
            effective_question = question

        # TPO legacy guardrail as a safety net (in case schema-driven missed something)
        if is_tpo and not schema_prompt:
            effective_question = f"{effective_question}\n\n{_tpo_context_guardrail()}"
        if _is_delivery_related(question):
            effective_question = (
                effective_question
                + "\n\n"
                + "DELIVERY COVERAGE GUARDRAIL: preserve delivery activity fields in the result "
                + "(IS_DELIVERY_ACTIVE_WEEK, TOTAL_DELIVERED_QTY, DELIVERY_STOP_COUNT where available) "
                + "at the requested grain."
            )
        if analytical:
            logger.info(
                "Analytical question detected — reframed for granular data retrieval"
            )

        # ---- Real-mode: call Cortex Analyst REST API ----
        import requests

        conn = self._snowflake.connect()
        # Get a session token from the active Snowflake connection
        token = conn.rest.token
        account = self._snowflake.config.account

        # Build the REST endpoint URL
        # Account locator keeps dots: "reyesholdings.east-us-2.azure" → host is same
        url = f"https://{account}.snowflakecomputing.com/api/v2/cortex/analyst/message"

        # Build payload — prefer semantic_view when available, else send YAML inline
        def _build_payload(question_text: str) -> dict[str, Any]:
            if semantic_view:
                return {
                    "messages": [
                        {
                            "role": "user",
                            "content": [{"type": "text", "text": question_text}],
                        }
                    ],
                    "semantic_view": semantic_view,
                }

            model_path = SEMANTIC_MODELS_DIR / f"{semantic_model}.yaml"
            if not model_path.exists():
                raise FileNotFoundError(
                    f"Semantic model not found: {model_path}. "
                    f"Available: {self.list_semantic_models()}"
                )
            with model_path.open() as f:
                semantic_model_yaml = f.read()

            return {
                "messages": [
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": question_text}],
                    }
                ],
                "semantic_model": semantic_model_yaml,
            }

        headers = {
            "Authorization": f'Snowflake Token="{token}"',
            "Content-Type": "application/json",
        }

        def _execute_once(question_text: str) -> tuple[str, str, pd.DataFrame, list[str]]:
            payload = _build_payload(question_text)
            source = f"semantic_view={semantic_view}" if semantic_view else f"model={semantic_model}"
            logger.info(
                "Calling Cortex Analyst: %s question=%s",
                source, question[:120],
            )
            resp = requests.post(url, json=payload, headers=headers, timeout=120)
            if resp.status_code != 200:
                # Extract Snowflake's error message from the response body
                # before raising — raw raise_for_status() hides the real cause.
                try:
                    err_body = resp.json()
                    sf_message = err_body.get("message", resp.text[:500])
                except Exception:
                    sf_message = resp.text[:500]
                logger.error(
                    "Cortex Analyst API error: HTTP %d — %s",
                    resp.status_code, sf_message,
                )
                raise requests.exceptions.HTTPError(
                    f"Cortex Analyst HTTP {resp.status_code}: {sf_message}",
                    response=resp,
                )
            result = resp.json()

            request_id = result.get("request_id", "unknown")
            content_blocks = result.get("message", {}).get("content", [])
            warnings_raw = result.get("warnings", [])
            local_warnings = [w.get("message", str(w)) for w in warnings_raw]

            generated_sql_local = ""
            for block in content_blocks:
                if block.get("type") == "sql":
                    generated_sql_local = block.get("statement", "")
                elif block.get("type") == "suggestions":
                    suggestions = block.get("suggestions", [])
                    local_warnings.append(
                        f"Cortex Analyst returned suggestions instead of SQL. "
                        f"Try one of: {suggestions}"
                    )

            if not generated_sql_local:
                return "", request_id, pd.DataFrame(), local_warnings

            sql_upper = generated_sql_local.upper()
            has_limit = "LIMIT" in sql_upper.split("--")[0].rsplit("ORDER", 1)[-1] if "LIMIT" in sql_upper else False
            if limit and not has_limit:
                exec_sql_local = f"{generated_sql_local.rstrip().rstrip(';')}\nLIMIT {limit}"
            else:
                exec_sql_local = generated_sql_local.rstrip().rstrip(';')

            logger.info("Executing Cortex-generated SQL (%d chars)", len(exec_sql_local))
            cursor = conn.cursor()
            try:
                cursor.execute(
                    f"ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = {query_timeout_seconds}"
                )
                cursor.execute(exec_sql_local)
                columns = [col[0].upper() for col in cursor.description]
                rows = cursor.fetchall()
                df_local = pd.DataFrame(rows, columns=columns)
            finally:
                cursor.close()

            if limit and len(df_local) >= limit:
                local_warnings.append(
                    f"Result was capped at {limit:,} rows. The full result set may be larger. "
                    f"Consider narrowing your question with a date range or category filter."
                )
                logger.warning("Result hit row limit (%d rows)", limit)

            logger.info(
                "Cortex Analyst returned %d rows, %d columns",
                len(df_local), len(df_local.columns),
            )
            return generated_sql_local, request_id, df_local, local_warnings

        generated_sql, request_id, df, warnings = _execute_once(effective_question)
        if not generated_sql:
            logger.warning("Cortex Analyst returned no SQL for question: %s", question)
            return CortexAnalystResponse(
                generated_sql="-- No SQL generated",
                dataframe=pd.DataFrame(),
                rows_returned=0,
                semantic_model=semantic_model,
                request_id=request_id,
                warnings=warnings or ["No SQL statement returned by Cortex Analyst."],
            )

        # Delivery quality guard: if coverage is implausibly low, retry once with
        # a stricter query pattern before returning data downstream.
        if _is_delivery_related(question):
            stats = _delivery_coverage_stats(df)
            if stats is not None:
                active, total, ratio = stats
                if total > 0 and ratio < _MIN_DELIVERY_COVERAGE_RATIO:
                    warning = (
                        f"{_DELIVERY_COVERAGE_WARNING_PREFIX} observed={active}/{total} "
                        f"ratio={ratio:.3f} threshold={_MIN_DELIVERY_COVERAGE_RATIO:.3f} "
                        "action=retry_with_strict_delivery_prompt"
                    )
                    warnings.append(warning)
                    logger.warning("%s", warning)

                    retry_prompt = _delivery_retry_reframe(question)
                    retry_sql, retry_request_id, retry_df, retry_warnings = _execute_once(retry_prompt)
                    if retry_sql:
                        retry_stats = _delivery_coverage_stats(retry_df)
                        if retry_stats is not None:
                            r_active, r_total, r_ratio = retry_stats
                            if r_total > 0 and r_ratio > ratio:
                                logger.info(
                                    "Delivery coverage retry improved result: %d/%d (%.3f -> %.3f)",
                                    r_active,
                                    r_total,
                                    ratio,
                                    r_ratio,
                                )
                                generated_sql = retry_sql
                                request_id = retry_request_id
                                df = retry_df
                                warnings.extend(retry_warnings)
                                ratio = r_ratio
                                active = r_active
                                total = r_total

                        final_warning = (
                            f"{_DELIVERY_COVERAGE_WARNING_PREFIX} observed={active}/{total} "
                            f"ratio={ratio:.3f} threshold={_MIN_DELIVERY_COVERAGE_RATIO:.3f} "
                            "action=downstream_quality_gate"
                        )
                        warnings.append(final_warning)
                        logger.warning("%s", final_warning)

        # ---- Grain validation for analytical questions ----
        if analytical and len(df) < _MIN_ANALYTICAL_ROWS and len(df) > 0:
            logger.warning(
                "Cortex returned only %d rows for an analytical question "
                "(expected >= %d for statistical analysis). Data may be "
                "over-aggregated. Consider using a verified query or "
                "narrowing the question.",
                len(df), _MIN_ANALYTICAL_ROWS,
            )
            warnings.append(
                f"Over-aggregation detected: Cortex returned {len(df)} rows for "
                f"an analytical question. Downstream statistical analysis "
                f"(correlations, regressions) may be unreliable with this few "
                f"observations. Expected >= {_MIN_ANALYTICAL_ROWS} rows at "
                f"store × week grain."
            )

        if is_tpo:
            warnings.extend(_tpo_context_warnings(df))

        # Generic schema-driven column check for any domain with a YAML spec
        if spec:
            warnings.extend(_schema_driven_warnings(spec, df))

        return CortexAnalystResponse(
            generated_sql=generated_sql,
            dataframe=df,
            rows_returned=len(df),
            semantic_model=semantic_model,
            request_id=request_id,
            warnings=warnings,
        )

    def _mock_response(
        self, question: str, semantic_model: str, limit: int | None
    ) -> CortexAnalystResponse:
        """Return canned data for scaffolding mode. Lets downstream code execute."""
        # Construct a tiny canned DataFrame so analytical agents have something
        # to "analyze" without real data. The dataframe shape varies by
        # semantic model so testing across domains exercises different code paths.
        if semantic_model == "walmart_in_store_execution":
            df = pd.DataFrame({
                "account_id": ["A001", "A002", "A003"],
                "sku_id": ["S001", "S002", "S003"],
                "week": ["2026-05-19", "2026-05-19", "2026-05-19"],
                "instock_pct": [0.96, 0.94, 0.72],  # third one looks anomalous
                "ftpr_pct": [0.89, 0.91, 0.78],
            })
        elif semantic_model == "production_operations":
            df = pd.DataFrame({
                "plant_id": ["P01", "P01", "P02"],
                "line_id": ["L1", "L2", "L1"],
                "shift": ["A", "B", "A"],
                "downtime_minutes": [12, 45, 8],
                "product_running": ["SKU-A", "SKU-B", "SKU-A"],
                "timestamp": ["2026-05-19T08:00", "2026-05-19T16:00", "2026-05-19T08:00"],
            })
        else:
            df = pd.DataFrame({
                "entity_id": ["E001", "E002"],
                "metric": [1.0, 2.0],
                "period": ["2026-05-19", "2026-05-19"],
            })

        return CortexAnalystResponse(
            generated_sql=f"-- MOCK Cortex Analyst for {semantic_model!r}\n-- Question: {question}\nSELECT * FROM mock_table;",
            dataframe=df,
            rows_returned=len(df),
            semantic_model=semantic_model,
            request_id="mock-request-" + str(abs(hash(question)) % 100000),
            warnings=["MOCK MODE — no real warehouse data."],
            is_mock=True,
        )

    @staticmethod
    def list_semantic_models() -> list[str]:
        """Return the available semantic models from context/semantic_models/."""
        if not SEMANTIC_MODELS_DIR.is_dir():
            return []
        return sorted(p.stem for p in SEMANTIC_MODELS_DIR.glob("*.yaml"))

    @staticmethod
    def load_semantic_model(name: str) -> dict[str, Any]:
        """Load a semantic model YAML by name. Returns the parsed dict."""
        path = SEMANTIC_MODELS_DIR / f"{name}.yaml"
        if not path.exists():
            raise FileNotFoundError(
                f"Semantic model not found: {path}. Available: "
                f"{CortexAnalystClient.list_semantic_models()}"
            )
        import yaml
        with path.open() as f:
            return yaml.safe_load(f) or {}
