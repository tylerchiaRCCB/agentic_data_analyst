"""Prompt-injection defense for free-text columns.

Per orchestration/pipeline-definitions.md §10 invariant #1 and the Data Retrieval Agent's
responsibilities, free-text columns must be sanitized at load time so downstream agents
treat their contents as data, not instructions.

This module is intentionally conservative — it neutralizes patterns that look like
system prompts or role-overrides, escapes control characters, and flags content that
matches known injection-shape signatures. False-positives are preferable to false-negatives
here; the alternative is letting customer notes or free-form responses act as instructions.
"""

from __future__ import annotations

import re
from typing import Final

import pandas as pd

# Patterns that look like attempts to override the agent's role or system prompt.
_INJECTION_PATTERNS: Final[list[re.Pattern[str]]] = [
    re.compile(r"(?i)\bignore (?:the )?(?:above|previous|prior) (?:instructions|prompts?)\b"),
    re.compile(r"(?i)\byou are (?:now |actually )?(?:a |an )?[a-z\s]{1,40}(?:assistant|bot|ai|model)\b"),
    re.compile(r"(?i)\bsystem:\s"),
    re.compile(r"(?i)\bassistant:\s"),
    re.compile(r"(?i)<\s*system\s*>"),
    re.compile(r"(?i)<\s*/?\s*instructions?\s*>"),
    re.compile(r"(?i)\bdisregard (?:the )?(?:above|previous|prior)\b"),
    re.compile(r"(?i)\bprint (?:the )?(?:full )?system prompt\b"),
    re.compile(r"(?i)\breveal (?:your |the )?(?:system|prompt|instructions?)\b"),
]

# Characters that complicate downstream rendering and prompt structure.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Placeholder inserted in place of matched injection content. Visible to downstream agents
# so they know sanitization happened on the cell; not so opaque that the cell becomes
# meaningless.
_REDACTION: Final[str] = "[REDACTED: injection-shape content]"

# Threshold: a column is considered "free text" if at least this share of non-null values
# exceed this length and the column dtype is string-like.
_FREE_TEXT_LEN_THRESHOLD: Final[int] = 40
_FREE_TEXT_SHARE_THRESHOLD: Final[float] = 0.10


def is_free_text_column(series: pd.Series) -> bool:
    """Heuristic: is this column free-text (vs. categorical/short-label string)?"""
    if series.dtype != "object" and not pd.api.types.is_string_dtype(series):
        return False
    non_null = series.dropna().astype(str)
    if len(non_null) == 0:
        return False
    long_count = int((non_null.str.len() > _FREE_TEXT_LEN_THRESHOLD).sum())
    return bool((long_count / len(non_null)) >= _FREE_TEXT_SHARE_THRESHOLD)


def sanitize_value(value: str) -> tuple[str, bool]:
    """Sanitize a single string value. Returns (sanitized, was_modified)."""
    modified = False
    cleaned = value

    # Strip control characters
    new_cleaned = _CONTROL_CHARS.sub("", cleaned)
    if new_cleaned != cleaned:
        modified = True
        cleaned = new_cleaned

    # Neutralize injection patterns by replacing with redaction marker
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(cleaned):
            cleaned = pattern.sub(_REDACTION, cleaned)
            modified = True

    return cleaned, modified


def sanitize_column(series: pd.Series) -> tuple[pd.Series, int]:
    """Sanitize an entire column. Returns (sanitized_series, modified_cell_count)."""
    if series.dtype != "object" and not pd.api.types.is_string_dtype(series):
        return series, 0

    modified_count = 0

    def _apply(v: object) -> object:
        nonlocal modified_count
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return v
        sanitized, was_modified = sanitize_value(str(v))
        if was_modified:
            modified_count += 1
        return sanitized

    return series.map(_apply), modified_count


def sanitize_dataframe(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Detect and sanitize all free-text columns in a dataframe.

    Returns (sanitized_df, modifications_by_column). The returned dict's keys are the
    column names that were identified as free-text; values are the count of cells
    modified by sanitization.
    """
    out = df.copy()
    modifications: dict[str, int] = {}
    for col in df.columns:
        if is_free_text_column(df[col]):
            sanitized, count = sanitize_column(df[col])
            out[col] = sanitized
            modifications[col] = count
    return out, modifications
