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

        # ---- Reframe analytical questions for data retrieval ----
        analytical = _is_analytical(question)
        effective_question = (
            _reframe_for_retrieval(question, semantic_model) if analytical else question
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
        if semantic_view:
            payload = {
                "messages": [
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": effective_question}],
                    }
                ],
                "semantic_view": semantic_view,
            }
        else:
            # Load the semantic model YAML from context/semantic_models/ and send inline
            model_path = SEMANTIC_MODELS_DIR / f"{semantic_model}.yaml"
            if not model_path.exists():
                raise FileNotFoundError(
                    f"Semantic model not found: {model_path}. "
                    f"Available: {self.list_semantic_models()}"
                )
            with model_path.open() as f:
                semantic_model_yaml = f.read()

            payload = {
                "messages": [
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": effective_question}],
                    }
                ],
                "semantic_model": semantic_model_yaml,
            }

        headers = {
            "Authorization": f'Snowflake Token="{token}"',
            "Content-Type": "application/json",
        }

        source = f"semantic_view={semantic_view}" if semantic_view else f"model={semantic_model}"
        logger.info(
            "Calling Cortex Analyst: %s question=%s",
            source, question[:120],
        )
        resp = requests.post(url, json=payload, headers=headers, timeout=120)
        resp.raise_for_status()
        result = resp.json()

        # Parse response: extract SQL statement and any text/warnings
        request_id = result.get("request_id", "unknown")
        content_blocks = result.get("message", {}).get("content", [])
        warnings_raw = result.get("warnings", [])
        warnings = [w.get("message", str(w)) for w in warnings_raw]

        generated_sql = ""
        for block in content_blocks:
            if block.get("type") == "sql":
                generated_sql = block.get("statement", "")
            elif block.get("type") == "suggestions":
                # Cortex couldn't generate SQL — question was ambiguous
                suggestions = block.get("suggestions", [])
                warnings.append(
                    f"Cortex Analyst returned suggestions instead of SQL. "
                    f"Try one of: {suggestions}"
                )

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

        # Apply row limit only if the generated SQL doesn't already have one
        sql_upper = generated_sql.upper()
        has_limit = "LIMIT" in sql_upper.split("--")[0].rsplit("ORDER", 1)[-1] if "LIMIT" in sql_upper else False
        if limit and not has_limit:
            exec_sql = f"{generated_sql.rstrip().rstrip(';')}\nLIMIT {limit}"
        else:
            exec_sql = generated_sql.rstrip().rstrip(';')

        # Execute the generated SQL via the Snowflake connection
        logger.info("Executing Cortex-generated SQL (%d chars)", len(exec_sql))
        cursor = conn.cursor()
        try:
            # Set per-statement timeout to kill runaway full-table scans
            cursor.execute(
                f"ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = {query_timeout_seconds}"
            )
            cursor.execute(exec_sql)
            columns = [col[0].upper() for col in cursor.description]
            rows = cursor.fetchall()
            df = pd.DataFrame(rows, columns=columns)
        finally:
            cursor.close()

        # Guard: warn if result set is unexpectedly large
        if limit and len(df) >= limit:
            warnings.append(
                f"Result was capped at {limit:,} rows. The full result set may be larger. "
                f"Consider narrowing your question with a date range or category filter."
            )
            logger.warning("Result hit row limit (%d rows)", limit)

        logger.info(
            "Cortex Analyst returned %d rows, %d columns",
            len(df), len(df.columns),
        )

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
