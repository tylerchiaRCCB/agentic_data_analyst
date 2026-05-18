"""Excel/CSV loader for the MVP data path.

Loads tabular data from disk, infers schema, applies injection defenses to free-text
columns, and produces metadata suitable for the Data Retrieval Agent's artifact.

The actual `DataRetrievalPayload` is produced by the agent during its API call — this
module is the side-effect-free helper that does the I/O and gives the agent the facts
it needs.

Threshold for auto-sampling vs. failing comes from `config/pipeline_config.yaml`
(default: 5M rows) per pipeline-definitions.md §10.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from src.data_access.injection_defense import is_free_text_column, sanitize_dataframe


@dataclass
class LoadedDataset:
    """Result of loading a tabular file. Contains the dataframe plus structural metadata.

    Per pipeline-definitions.md §10, the dataset itself is *not* shipped to LLM context;
    only the metadata is. The dataframe lives in memory locally / in the sandbox for
    code-execution-driven analysis.
    """

    df: pd.DataFrame
    source_path: Path
    row_count: int
    column_metadata: list[dict[str, object]]  # name, dtype, null_count, distinct_count, is_free_text
    free_text_columns_sanitized: list[str]
    sanitization_counts: dict[str, int]  # column name -> # modified cells
    load_warnings: list[dict[str, str]] = field(default_factory=list)
    was_sampled: bool = False
    sample_size: int | None = None


def load_tabular(
    path: Path,
    *,
    row_threshold: int = 5_000_000,
    auto_sample: bool = True,
    sample_seed: int = 42,
) -> LoadedDataset:
    """Load a CSV or Excel file. Enforces the row-count threshold per §10.

    If `row_count > row_threshold` and `auto_sample=True`, downsamples with a high-severity
    warning. If `auto_sample=False` and the threshold is exceeded, raises ValueError.
    """
    if not path.exists():
        raise FileNotFoundError(f"Data file not found: {path}")

    suffix = path.suffix.lower()
    warnings: list[dict[str, str]] = []

    if suffix == ".csv":
        df = pd.read_csv(path)
    elif suffix in {".xlsx", ".xlsm", ".xls"}:
        df = pd.read_excel(path)
    else:
        raise ValueError(f"Unsupported file extension: {suffix}. Expected .csv or .xlsx.")

    original_rows = len(df)
    was_sampled = False
    sample_size: int | None = None

    if original_rows > row_threshold:
        if not auto_sample:
            raise ValueError(
                f"Dataset has {original_rows:,} rows, exceeds threshold {row_threshold:,}. "
                f"Either enable auto_sample or move to the Snowflake/Cortex path."
            )
        df = df.sample(n=row_threshold, random_state=sample_seed).reset_index(drop=True)
        was_sampled = True
        sample_size = row_threshold
        warnings.append(
            {
                "text": (
                    f"Dataset exceeded the {row_threshold:,}-row threshold "
                    f"({original_rows:,} rows). Auto-sampled to {row_threshold:,} rows "
                    f"using uniform random sampling (seed={sample_seed}). "
                    f"Findings should be interpreted as estimates from a representative sample, "
                    f"not as full-population claims."
                ),
                "severity": "high",
                "reason": "row-count threshold (pipeline_config.yaml)",
            }
        )

    sanitized_df, sanitization_counts = sanitize_dataframe(df)
    free_text_cols = list(sanitization_counts.keys())

    column_metadata: list[dict[str, object]] = []
    for col in sanitized_df.columns:
        series = sanitized_df[col]
        column_metadata.append(
            {
                "name": col,
                "dtype": str(series.dtype),
                "null_count": int(series.isna().sum()),
                "distinct_count": int(series.nunique(dropna=True)),
                "is_free_text": is_free_text_column(df[col]),
            }
        )

    return LoadedDataset(
        df=sanitized_df,
        source_path=path,
        row_count=len(sanitized_df),
        column_metadata=column_metadata,
        free_text_columns_sanitized=free_text_cols,
        sanitization_counts=sanitization_counts,
        load_warnings=warnings,
        was_sampled=was_sampled,
        sample_size=sample_size,
    )
