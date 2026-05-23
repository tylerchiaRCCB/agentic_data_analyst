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
        limit: int | None = 100000,
    ) -> CortexAnalystResponse:
        """Submit a natural-language analytical question to Cortex Analyst.

        Parameters:
          question:        the analytical question (e.g. "weekly fill rate by DC
                           for the past 13 weeks").
          semantic_model:  the semantic model name (e.g. "supply_chain"). The
                           YAML file must exist at
                           context/semantic_models/<semantic_model>.yaml.
          limit:           row limit to apply (caps cost + token use downstream).

        Returns CortexAnalystResponse with the generated SQL, the resulting
        DataFrame, and any quality warnings.

        Raises NoCredentialsConfigured / SnowflakeNotInstalled in real mode if
        the warehouse isn't reachable. In mock mode, returns canned data based
        on the semantic_model name.
        """
        if self.mock_mode:
            return self._mock_response(question, semantic_model, limit)

        # Real-mode implementation. Cortex Analyst is invoked via REST against
        # the account's Snowflake endpoint. The exact endpoint, auth, and
        # payload shape are documented at:
        #
        #   https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst
        #
        # This stub raises NotImplementedError until production credentials and
        # the semantic model are in place. The interface above is stable; only
        # the body of this branch will change when we wire the real call.
        raise NotImplementedError(
            "CortexAnalystClient.ask() real-mode is not yet wired. Set "
            "SNOWFLAKE_MOCK=1 for scaffolding mode, or implement the REST call "
            "against https://<account>.snowflakecomputing.com/api/v2/cortex/analyst/message "
            "once production credentials and the semantic model are in place."
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
