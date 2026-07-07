"""Tests for the Snowflake / Cortex Analyst / Cortex Agents scaffolding.

These exercise:
- Mock-mode behavior (works without real credentials).
- NoCredentialsConfigured raised cleanly when secrets are missing.
- The semantic model loader / lister.
- Interface stability (the calls return the right normalized shapes).

Real-mode tests against actual Snowflake are deferred until production
credentials land (a few weeks per the team's plan).
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest

from src.data_access.snowflake_client import (
    NoCredentialsConfigured,
    SnowflakeClient,
    SnowflakeConfig,
)


@pytest.fixture
def mock_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enable mock mode so client construction succeeds without real creds."""
    monkeypatch.setenv("SNOWFLAKE_MOCK", "1")


@pytest.fixture
def no_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip all Snowflake env vars so the no-credentials path is exercised."""
    for var in [
        "SNOWFLAKE_MOCK",
        "SNOWFLAKE_ACCOUNT",
        "SNOWFLAKE_USER",
        "SNOWFLAKE_PRIVATE_KEY",
        "SNOWFLAKE_PASSWORD",
        "SNOWFLAKE_WAREHOUSE",
        "SNOWFLAKE_ROLE",
        "SNOWFLAKE_DATABASE",
        "SNOWFLAKE_SCHEMA",
    ]:
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# SnowflakeClient — connection scaffolding
# ---------------------------------------------------------------------------


def test_snowflake_client_constructs_in_mock_mode(mock_env: None) -> None:
    client = SnowflakeClient()
    assert client.mock_mode is True
    # Mock connection opens without raising
    conn = client.connect()
    assert conn is not None
    # execute_query returns empty list in mock mode
    rows = client.execute_query("SELECT 1")
    assert rows == []


def test_snowflake_client_raises_no_credentials_when_env_missing(no_env: None) -> None:
    with pytest.raises(NoCredentialsConfigured) as exc:
        SnowflakeClient()
    assert "SNOWFLAKE_ACCOUNT" in str(exc.value)


def test_snowflake_config_from_env_loads_all_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SNOWFLAKE_ACCOUNT", "myacct")
    monkeypatch.setenv("SNOWFLAKE_USER", "myuser")
    monkeypatch.setenv("SNOWFLAKE_PRIVATE_KEY", "mykey")
    monkeypatch.setenv("SNOWFLAKE_WAREHOUSE", "ANALYTICS_WH")
    monkeypatch.setenv("SNOWFLAKE_ROLE", "ANALYST")
    monkeypatch.setenv("SNOWFLAKE_DATABASE", "PROD")
    monkeypatch.setenv("SNOWFLAKE_SCHEMA", "ANALYTICS")
    monkeypatch.delenv("SNOWFLAKE_MOCK", raising=False)

    cfg = SnowflakeConfig.from_env()
    assert cfg.account == "myacct"
    assert cfg.user == "myuser"
    assert cfg.private_key == "mykey"
    assert cfg.warehouse == "ANALYTICS_WH"
    assert cfg.mock_mode is False


# ---------------------------------------------------------------------------
# CortexAnalystClient — governed NL-to-SQL
# ---------------------------------------------------------------------------


def test_cortex_analyst_mock_returns_walmart_dataframe(mock_env: None) -> None:
    """Mock mode returns a canned Walmart shape so downstream agents have
    something to analyze without a real warehouse."""
    from src.data_access.cortex_analyst_client import CortexAnalystClient

    client = CortexAnalystClient()
    assert client.mock_mode is True

    response = client.ask(
        question="How is fill rate trending for SKU-7 across NE accounts?",
        semantic_model="walmart_in_store_execution",
    )
    assert response.is_mock is True
    assert response.semantic_model == "walmart_in_store_execution"
    assert "MOCK" in response.warnings[0]
    assert isinstance(response.dataframe, pd.DataFrame)
    assert len(response.dataframe) > 0
    assert "instock_pct" in response.dataframe.columns
    assert response.generated_sql.startswith("-- MOCK")


def test_cortex_analyst_mock_returns_production_ops_shape(mock_env: None) -> None:
    """A different semantic model returns a different shape — proves the mock
    distinguishes domains."""
    from src.data_access.cortex_analyst_client import CortexAnalystClient

    client = CortexAnalystClient()
    response = client.ask(
        question="Downtime trends",
        semantic_model="production_operations",
    )
    assert "downtime_minutes" in response.dataframe.columns
    assert "filler_id" not in response.dataframe.columns  # that's the Agent shape
    # production_operations mock has 'plant_id' column
    assert "plant_id" in response.dataframe.columns


def test_cortex_analyst_real_mode_raises_not_implemented(monkeypatch: pytest.MonkeyPatch) -> None:
    """In real mode (creds present, mock disabled), the real REST call is not
    yet wired — raises NotImplementedError until production credentials and
    semantic model are confirmed. This is the scaffolding promise."""
    monkeypatch.setenv("SNOWFLAKE_ACCOUNT", "myacct")
    monkeypatch.setenv("SNOWFLAKE_USER", "myuser")
    monkeypatch.setenv("SNOWFLAKE_PASSWORD", "pw")
    monkeypatch.setenv("SNOWFLAKE_WAREHOUSE", "WH")
    monkeypatch.setenv("SNOWFLAKE_ROLE", "R")
    monkeypatch.setenv("SNOWFLAKE_DATABASE", "DB")
    monkeypatch.setenv("SNOWFLAKE_SCHEMA", "S")
    monkeypatch.delenv("SNOWFLAKE_MOCK", raising=False)

    from src.data_access.cortex_analyst_client import CortexAnalystClient

    client = CortexAnalystClient()
    assert client.mock_mode is False
    with pytest.raises(NotImplementedError, match="real-mode is not yet wired"):
        client.ask(question="q", semantic_model="walmart_in_store_execution")


def test_cortex_analyst_lists_available_semantic_models() -> None:
    """The lister should pick up the .yaml files in context/semantic_models/."""
    from src.data_access.cortex_analyst_client import CortexAnalystClient

    available = CortexAnalystClient.list_semantic_models()
    # The template and example files we shipped should appear
    assert any("walmart" in name.lower() for name in available)


def test_cortex_analyst_loads_walmart_example_semantic_model() -> None:
    """The example semantic model loads and has the documented sections."""
    from src.data_access.cortex_analyst_client import CortexAnalystClient

    spec = CortexAnalystClient.load_semantic_model("walmart_in_store_execution.example")
    assert spec["name"] == "walmart_in_store_execution"
    assert "tables" in spec
    assert "guardrail_metric_pairings" in spec
    assert "thresholds" in spec
    assert "stakeholder_map" in spec


# ---------------------------------------------------------------------------
# CortexAgentClient — multi-step agentic SQL workflows
# ---------------------------------------------------------------------------


def test_cortex_agent_mock_returns_multi_step_response(mock_env: None) -> None:
    """Mock mode for production_operations simulates the temporal-range-join
    scenario the user described (downtime ↔ product running)."""
    from src.data_access.cortex_agent_client import CortexAgentClient

    client = CortexAgentClient()
    assert client.mock_mode is True

    response = client.run_workflow(
        task="For each filler downtime event, find what product was running",
        semantic_model="production_operations",
    )
    assert response.is_mock is True
    assert "filler_id" in response.final_dataframe.columns
    assert "product_running" in response.final_dataframe.columns
    assert len(response.steps) >= 2  # multi-step workflow
    # Steps record what the Cortex Agent did — for lineage / audit
    assert all(step.description for step in response.steps)


def test_cortex_agent_real_mode_raises_not_implemented(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same scaffolding promise as Cortex Analyst — real-mode wiring deferred
    until production credentials confirmed."""
    monkeypatch.setenv("SNOWFLAKE_ACCOUNT", "myacct")
    monkeypatch.setenv("SNOWFLAKE_USER", "myuser")
    monkeypatch.setenv("SNOWFLAKE_PASSWORD", "pw")
    monkeypatch.setenv("SNOWFLAKE_WAREHOUSE", "WH")
    monkeypatch.setenv("SNOWFLAKE_ROLE", "R")
    monkeypatch.setenv("SNOWFLAKE_DATABASE", "DB")
    monkeypatch.setenv("SNOWFLAKE_SCHEMA", "S")
    monkeypatch.delenv("SNOWFLAKE_MOCK", raising=False)

    from src.data_access.cortex_agent_client import CortexAgentClient

    client = CortexAgentClient()
    with pytest.raises(NotImplementedError, match="real-mode is not yet wired"):
        client.run_workflow(task="t", semantic_model="walmart_in_store_execution")


def test_tpo_target_detection_by_model_and_view() -> None:
    from src.data_access.cortex_analyst_client import _is_tpo_target

    assert _is_tpo_target("tpo_insights", None) is True
    assert _is_tpo_target("other_domain", "CCB_DATASCIENCE_DEV.TPO_ANAPLAN_ANALYSIS.TPO_V_PROMO_ONLY") is True
    assert _is_tpo_target("other_domain", "CCB_DATASCIENCE_DEV.WALMART_OPD.WALMART_OPD") is False


def test_tpo_context_warnings_require_time_and_edv_columns() -> None:
    from src.data_access.cortex_analyst_client import _tpo_context_warnings

    minimal = pd.DataFrame(
        {
            "ACCOUNT": ["A"],
            "PPG": ["P"],
            "EVEN_OFFER_STANDARD": ["Offer"],
            "INCREMENTAL_RETAIL_UNITS": [100],
        }
    )
    warnings = _tpo_context_warnings(minimal)
    assert any("TPO_CONTEXT_MISSING_TIME_COLUMNS" in w for w in warnings)
    assert any("TPO_CONTEXT_MISSING_EDV_COLUMNS" in w for w in warnings)

    complete = pd.DataFrame(
        {
            "FISCAL_YEAR": ["FY25"],
            "WEEK_NUM": [12],
            "PROMO_WEEK_START": ["2025-03-17"],
            "EDV_SCOPE_APPLIED": [False],
        }
    )
    assert _tpo_context_warnings(complete) == []
