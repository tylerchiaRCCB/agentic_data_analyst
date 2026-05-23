"""Snowflake connection client — scaffolding for production data access.

The framework's value proposition depends on being able to analyze REAL,
GOVERNED data. Today the only data path is CSV/Excel on local disk. This
module is the connection foundation for the Cortex Analyst and Cortex
Agents integrations defined in cortex_analyst_client.py and
cortex_agent_client.py.

## Why direct SQL is NOT the recommended path

A direct SQL approach (hand-written queries against Snowflake) defeats the
framework's value proposition. The whole point of the Cortex integration is
that the LLM generates SQL against a GOVERNED semantic model — not us
hand-curating queries per analytical question.

This module exists only as the *connection layer* that Cortex Analyst and
Cortex Agents need to talk to Snowflake. Direct query execution is exposed
for debugging and for the rare case where a stage needs a known-safe
parameterized query (e.g. fetching the semantic model file itself, or
checking data freshness before launching a run).

## Auth pattern

Snowflake credentials are pulled from Azure Key Vault via the same pattern
the team's fork uses for ANTHROPIC_API_KEY. Required secrets:

    SNOWFLAKE_ACCOUNT     — account locator (e.g. xy12345.us-east-1.aws)
    SNOWFLAKE_USER        — service-principal user
    SNOWFLAKE_PRIVATE_KEY — base64-encoded private key (preferred)  OR
    SNOWFLAKE_PASSWORD    — password (less preferred; rotate frequently)
    SNOWFLAKE_WAREHOUSE   — compute warehouse to use
    SNOWFLAKE_ROLE        — role with read access to the analytical semantic model
    SNOWFLAKE_DATABASE    — database containing the semantic model
    SNOWFLAKE_SCHEMA      — schema for the semantic model + analytical views

When the secrets are absent, `connect()` raises `NoCredentialsConfigured`
cleanly — tests and scaffolding work without real Snowflake access. The
mock mode (returns canned data) is enabled via SNOWFLAKE_MOCK=1.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


class NoCredentialsConfigured(RuntimeError):
    """Raised when Snowflake credentials are not present in env / AKV.

    Caller should either configure credentials (production), enable
    SNOWFLAKE_MOCK=1 (scaffolding/testing), or fall back to the CSV
    data path (early-stage testing without warehouse access).
    """


class SnowflakeNotInstalled(RuntimeError):
    """Raised when snowflake-connector-python is not installed but
    a real (non-mock) Snowflake call is attempted."""


@dataclass
class SnowflakeConfig:
    """Snowflake connection configuration. Populated from env / AKV."""

    account: str
    user: str
    warehouse: str
    role: str
    database: str
    schema: str
    private_key: str | None = None  # base64-encoded
    password: str | None = None
    mock_mode: bool = False

    @classmethod
    def from_env(cls) -> "SnowflakeConfig":
        """Load config from environment variables. Mock mode if SNOWFLAKE_MOCK=1."""
        mock = os.environ.get("SNOWFLAKE_MOCK", "").lower() in {"1", "true", "yes"}
        if mock:
            return cls(
                account="mock",
                user="mock",
                warehouse="mock_wh",
                role="mock_role",
                database="MOCK_DB",
                schema="ANALYTICS",
                mock_mode=True,
            )

        missing: list[str] = []
        required = ["SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_WAREHOUSE",
                    "SNOWFLAKE_ROLE", "SNOWFLAKE_DATABASE", "SNOWFLAKE_SCHEMA"]
        for var in required:
            if not os.environ.get(var):
                missing.append(var)
        if missing:
            raise NoCredentialsConfigured(
                f"Missing required Snowflake env vars: {missing}. Set them (typically "
                "from Azure Key Vault) or enable SNOWFLAKE_MOCK=1 for scaffolding mode."
            )

        priv = os.environ.get("SNOWFLAKE_PRIVATE_KEY")
        pwd = os.environ.get("SNOWFLAKE_PASSWORD")
        if not (priv or pwd):
            raise NoCredentialsConfigured(
                "Either SNOWFLAKE_PRIVATE_KEY or SNOWFLAKE_PASSWORD must be set."
            )

        return cls(
            account=os.environ["SNOWFLAKE_ACCOUNT"],
            user=os.environ["SNOWFLAKE_USER"],
            warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
            role=os.environ["SNOWFLAKE_ROLE"],
            database=os.environ["SNOWFLAKE_DATABASE"],
            schema=os.environ["SNOWFLAKE_SCHEMA"],
            private_key=priv,
            password=pwd,
        )


class SnowflakeClient:
    """Connection-layer wrapper. Used by CortexAnalystClient and CortexAgentClient.

    Direct query execution is exposed but not the recommended analytical path
    (use Cortex Analyst for governed NL-to-SQL instead).
    """

    def __init__(self, config: SnowflakeConfig | None = None) -> None:
        self.config = config or SnowflakeConfig.from_env()
        self._connection: Any = None

    @property
    def mock_mode(self) -> bool:
        return self.config.mock_mode

    def connect(self) -> Any:
        """Open or return the cached Snowflake connection.

        In mock mode, returns a lightweight stub object so code paths still
        execute without raising. Real connection requires
        snowflake-connector-python to be installed.
        """
        if self._connection is not None:
            return self._connection

        if self.config.mock_mode:
            logger.info("SnowflakeClient in mock mode — no real connection opened.")
            self._connection = _MockConnection()
            return self._connection

        try:
            import snowflake.connector
        except ImportError as e:
            raise SnowflakeNotInstalled(
                "snowflake-connector-python is not installed. Add it as a dependency "
                "for real Snowflake connectivity, or set SNOWFLAKE_MOCK=1 for scaffolding."
            ) from e

        conn_args: dict[str, Any] = {
            "account": self.config.account,
            "user": self.config.user,
            "warehouse": self.config.warehouse,
            "role": self.config.role,
            "database": self.config.database,
            "schema": self.config.schema,
        }
        if self.config.private_key:
            # Real impl: decode + load private key per snowflake-connector docs
            conn_args["private_key"] = self.config.private_key
        else:
            conn_args["password"] = self.config.password

        logger.info(
            "Connecting to Snowflake account=%s warehouse=%s role=%s db=%s.%s",
            self.config.account, self.config.warehouse, self.config.role,
            self.config.database, self.config.schema,
        )
        self._connection = snowflake.connector.connect(**conn_args)
        return self._connection

    def execute_query(self, sql: str, params: tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
        """Execute a SQL query and return rows as list-of-dicts.

        Used by Cortex Analyst / Cortex Agents under the hood. Not the
        recommended path for analytical agents — they should go through
        the Cortex layer for governance.
        """
        if self.config.mock_mode:
            logger.info("Mock-mode execute_query (returning empty): %s", sql[:120])
            return []

        conn = self.connect()
        cursor = conn.cursor()
        try:
            cursor.execute(sql, params)
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        finally:
            cursor.close()

    def close(self) -> None:
        if self._connection is not None:
            try:
                self._connection.close()
            except Exception:  # noqa: BLE001
                pass
            self._connection = None


class _MockConnection:
    """Stub connection object for mock mode. Supports the minimal cursor API."""

    def cursor(self) -> Any:
        return _MockCursor()

    def close(self) -> None:
        pass


class _MockCursor:
    description: list[tuple[str, Any]] = []

    def execute(self, sql: str, params: Any = None) -> None:  # noqa: ARG002
        pass

    def fetchall(self) -> list[Any]:
        return []

    def close(self) -> None:
        pass
