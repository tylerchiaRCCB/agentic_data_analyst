"""Snowflake metadata profiler for semantic view generation.

Pulls schema + sample data for a list of tables/views, assembles a rich
metadata payload that the YAML generator LLM prompt can consume.

Extracted per table:
  - Column names, Snowflake data types, nullable flag
  - Row count
  - Null rate per column
  - Distinct count per column (capped at 10k for speed)
  - Sample values (up to 10 representative, non-null values per column)

Auth uses the same team AKV pattern as the rest of the system.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_SAMPLE_ROWS = 500       # rows pulled for value sampling
_MAX_SAMPLE_VALUES = 10  # unique sample values shown per column


@dataclass
class ColumnProfile:
    name: str
    data_type: str
    nullable: bool
    null_rate: float          # 0.0 – 1.0
    distinct_count: int | None
    sample_values: list[Any] = field(default_factory=list)


@dataclass
class TableProfile:
    database: str
    schema: str
    table: str
    row_count: int
    columns: list[ColumnProfile] = field(default_factory=list)

    @property
    def qualified_name(self) -> str:
        return f"{self.database}.{self.schema}.{self.table}"


def _parse_table_ref(ref: str) -> tuple[str, str, str]:
    """Parse 'DB.SCHEMA.TABLE' or 'SCHEMA.TABLE' into (db, schema, table).

    If only two parts are given, database defaults to empty string — the
    caller is expected to supply a default database from the connection config.
    """
    parts = [p.strip().upper() for p in ref.split(".")]
    if len(parts) == 3:
        return parts[0], parts[1], parts[2]
    if len(parts) == 2:
        return "", parts[0], parts[1]
    raise ValueError(
        f"Cannot parse table reference {ref!r}. "
        "Expected 'DATABASE.SCHEMA.TABLE' or 'SCHEMA.TABLE'."
    )


def profile_tables(
    table_refs: list[str],
    *,
    database: str = "CCB_DATASCIENCE_DEV",
    schema: str = "WALMART_STANDARDIZED_EXTERNAL_DATA",
    role: str = "CCB_DATASCIENCE_SNOWFLAKE",
) -> list[TableProfile]:
    """Profile a list of Snowflake table/view references.

    Parameters
    ----------
    table_refs:
        List of fully or partially qualified table names, e.g.
        ["DB.SCHEMA.TABLE", "SCHEMA.VIEW", "JUST_TABLE"].
    database:
        Default database when the ref omits one.
    schema:
        Default schema when the ref omits one.
    role:
        Snowflake role to use. Defaults to the team analytics role.

    Returns a list of TableProfile objects, one per input ref.
    """
    # Import here so the module is importable without snowflake installed.
    try:
        from src.data_access.snowflake_client import SnowflakeClient, SnowflakeConfig
    except ImportError:
        from data_access.snowflake_client import SnowflakeClient, SnowflakeConfig  # type: ignore[no-redef]

    config = SnowflakeConfig.from_team_keyvault(database=database, schema=schema)
    # Override role if requested
    config.role = role
    client = SnowflakeClient(config)

    profiles: list[TableProfile] = []
    for ref in table_refs:
        db, sch, tbl = _parse_table_ref(ref)
        db = db or database
        sch = sch or schema
        try:
            prof = _profile_one_table(client, db, sch, tbl)
            profiles.append(prof)
            logger.info("Profiled %s.%s.%s — %d rows, %d cols",
                        db, sch, tbl, prof.row_count, len(prof.columns))
        except Exception as exc:
            logger.warning("Failed to profile %s.%s.%s: %s", db, sch, tbl, exc)
            raise

    return profiles


def _profile_one_table(
    client: Any, database: str, schema: str, table: str
) -> TableProfile:
    import pandas as pd

    qualified = f"{database}.{schema}.{table}"

    # 1. Row count
    row_df: pd.DataFrame = client.execute_query(f"SELECT COUNT(*) AS N FROM {qualified}")
    row_count = int(row_df.iloc[0, 0])

    # 2. Column schema from INFORMATION_SCHEMA
    schema_df: pd.DataFrame = client.execute_query(f"""
        SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
        FROM {database}.INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = '{schema}'
          AND TABLE_NAME   = '{table}'
        ORDER BY ORDINAL_POSITION
    """)

    columns: list[ColumnProfile] = []
    col_names = schema_df["COLUMN_NAME"].tolist()

    # 3. Sample rows (limit for speed)
    sample_limit = min(_SAMPLE_ROWS, row_count) if row_count > 0 else 0
    sample_df: pd.DataFrame | None = None
    if sample_limit > 0:
        try:
            sample_df = client.execute_query(
                f"SELECT * FROM {qualified} TABLESAMPLE SYSTEM ({_SAMPLE_ROWS} ROWS)"
            )
        except Exception:
            # TABLESAMPLE not supported on all object types — fall back to LIMIT
            sample_df = client.execute_query(
                f"SELECT * FROM {qualified} LIMIT {_SAMPLE_ROWS}"
            )

    for _, row in schema_df.iterrows():
        col = str(row["COLUMN_NAME"])
        dtype = str(row["DATA_TYPE"])
        nullable = str(row.get("IS_NULLABLE", "YES")).upper() != "NO"

        # Null rate from sample
        null_rate = 0.0
        sample_vals: list[Any] = []
        distinct_ct: int | None = None

        if sample_df is not None and col in sample_df.columns:
            col_series = sample_df[col]
            null_rate = round(float(col_series.isna().mean()), 4)
            non_null = col_series.dropna()
            unique_vals = non_null.unique().tolist()
            distinct_ct = len(unique_vals)
            # Pick representative sample values — prefer variety
            sample_vals = [str(v) for v in unique_vals[:_MAX_SAMPLE_VALUES]]

        columns.append(ColumnProfile(
            name=col,
            data_type=dtype,
            nullable=nullable,
            null_rate=null_rate,
            distinct_count=distinct_ct,
            sample_values=sample_vals,
        ))

    return TableProfile(
        database=database,
        schema=schema,
        table=table,
        row_count=row_count,
        columns=columns,
    )


def profiles_to_markdown(profiles: list[TableProfile]) -> str:
    """Render profiles as structured markdown for inclusion in an LLM prompt."""
    lines: list[str] = []
    for p in profiles:
        lines.append(f"## Table: {p.qualified_name}")
        lines.append(f"- Row count: {p.row_count:,}")
        lines.append(f"- Columns: {len(p.columns)}")
        lines.append("")
        lines.append("| Column | Type | Nullable | Null% | Distinct | Sample values |")
        lines.append("|--------|------|----------|-------|----------|---------------|")
        for c in p.columns:
            null_pct = f"{c.null_rate * 100:.1f}%"
            distinct = str(c.distinct_count) if c.distinct_count is not None else "?"
            samples = ", ".join(c.sample_values[:5]) if c.sample_values else "—"
            lines.append(
                f"| {c.name} | {c.data_type} | {'Y' if c.nullable else 'N'} "
                f"| {null_pct} | {distinct} | `{samples}` |"
            )
        lines.append("")
    return "\n".join(lines)
