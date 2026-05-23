"""Snowflake Cortex Agents client — multi-step agentic SQL workflows.

Cortex Agents are Snowflake's higher-level agentic primitive (announced 2025):
they orchestrate multi-step SQL workflows against the semantic model. Where
Cortex Analyst answers a single question with a single SQL query, a Cortex
Agent can decompose a complex analytical question into a sequence of queries,
intermediate transformations, and final summarization.

For our framework: Cortex Agents become the right path when the analytical
question requires multi-table reasoning, temporal-range joins, or iterative
refinement (e.g. "for each filler downtime event, query the production log
for what was running, then summarize by SKU"). Cortex Analyst would require
hand-decomposing this; Cortex Agents handle it.

## Relationship to Cortex Analyst

Both go through the same semantic model. They are complementary:
  - Use Cortex Analyst for one-shot governed queries.
  - Use Cortex Agents for multi-step workflows that benefit from agentic
    decomposition.

The framework's Data Retrieval Agent picks based on the Question Framer's
specification — simple data needs use Cortex Analyst; complex multi-source
or multi-step needs use Cortex Agents.

## Status

Cortex Agents are in active development at Snowflake. The exact REST API
shape may evolve; this client mirrors what's documented as of 2026-05-23.
Real-mode invocation is `NotImplementedError` pending production credentials
and confirmation of the current API.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import pandas as pd

from src.data_access.snowflake_client import (
    NoCredentialsConfigured,
    SnowflakeClient,
)

logger = logging.getLogger(__name__)


@dataclass
class CortexAgentStep:
    """One step in a Cortex Agent's multi-step workflow."""

    step_index: int
    description: str
    generated_sql: str | None
    rows_returned: int | None
    output_summary: str


@dataclass
class CortexAgentResponse:
    """Normalized response from a Cortex Agents workflow run.

    `final_dataframe` is the workflow's final result that flows into the
    framework as the dataset slice. `steps` are the intermediate steps the
    agent took — recorded in lineage for audit.
    """

    workflow_id: str
    semantic_model: str
    final_dataframe: pd.DataFrame
    steps: list[CortexAgentStep]
    rows_returned: int
    warnings: list[str]
    is_mock: bool = False


class CortexAgentClient:
    """Wrapper for Snowflake Cortex Agents' multi-step SQL workflow API."""

    def __init__(self, snowflake: SnowflakeClient | None = None) -> None:
        try:
            self._snowflake = snowflake or SnowflakeClient()
        except NoCredentialsConfigured:
            raise NoCredentialsConfigured(
                "CortexAgentClient requires Snowflake credentials. Configure the "
                "SNOWFLAKE_* env vars (typically from Azure Key Vault) or enable "
                "SNOWFLAKE_MOCK=1 for scaffolding mode."
            ) from None

    @property
    def mock_mode(self) -> bool:
        return self._snowflake.mock_mode

    def run_workflow(
        self,
        *,
        task: str,
        semantic_model: str,
        max_steps: int = 10,
    ) -> CortexAgentResponse:
        """Submit an analytical task to Cortex Agents.

        Parameters:
          task:            the multi-step analytical task in plain English
                           (e.g. "for each filler downtime event last week,
                            find what product was running and summarize
                            downtime minutes by SKU").
          semantic_model:  semantic model name (same convention as Cortex
                           Analyst).
          max_steps:       cap on the agent's step count to bound cost.

        Returns CortexAgentResponse with the final DataFrame, the full step
        trace, and any warnings.
        """
        if self.mock_mode:
            return self._mock_response(task, semantic_model)

        raise NotImplementedError(
            "CortexAgentClient.run_workflow() real-mode is not yet wired. Set "
            "SNOWFLAKE_MOCK=1 for scaffolding mode. Once production credentials "
            "and the Cortex Agents API confirmation are in place, implement the "
            "REST call (or Python SDK call once available)."
        )

    def _mock_response(self, task: str, semantic_model: str) -> CortexAgentResponse:
        """Return canned multi-step response for scaffolding mode."""
        if semantic_model == "production_operations":
            # Simulate the temporal-range-join scenario: downtime + production log.
            df = pd.DataFrame({
                "filler_id": ["F03", "F03", "F03", "F07"],
                "downtime_minutes": [180, 90, 45, 30],
                "product_running": ["SKU-A", "SKU-B", "SKU-A", "SKU-C"],
                "week": ["2026-05-19"] * 4,
            })
            steps = [
                CortexAgentStep(
                    step_index=1,
                    description="Pull downtime events for the week",
                    generated_sql="SELECT filler_id, ts, duration_min FROM downtime WHERE week = '2026-05-19'",
                    rows_returned=42,
                    output_summary="42 downtime events identified",
                ),
                CortexAgentStep(
                    step_index=2,
                    description="Temporal-range-join with production log to attach product running",
                    generated_sql="SELECT d.*, p.product_running FROM downtime d JOIN production_log p ON d.ts BETWEEN p.start_ts AND p.end_ts",
                    rows_returned=42,
                    output_summary="Each downtime event labeled with the product running",
                ),
                CortexAgentStep(
                    step_index=3,
                    description="Aggregate downtime minutes by filler × product",
                    generated_sql="SELECT filler_id, product_running, SUM(duration_min) FROM ... GROUP BY 1,2",
                    rows_returned=4,
                    output_summary="4 (filler, product) aggregates",
                ),
            ]
        else:
            df = pd.DataFrame({
                "entity_id": ["E001", "E002"],
                "summary_metric": [1.0, 2.0],
            })
            steps = [
                CortexAgentStep(
                    step_index=1,
                    description="MOCK step",
                    generated_sql="SELECT * FROM mock_table",
                    rows_returned=2,
                    output_summary="Mock data",
                ),
            ]

        return CortexAgentResponse(
            workflow_id="mock-workflow-" + str(abs(hash(task)) % 100000),
            semantic_model=semantic_model,
            final_dataframe=df,
            steps=steps,
            rows_returned=len(df),
            warnings=["MOCK MODE — no real warehouse data."],
            is_mock=True,
        )
