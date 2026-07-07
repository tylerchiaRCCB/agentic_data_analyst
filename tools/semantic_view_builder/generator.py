"""LLM-based semantic view YAML generator.

Takes profiled Snowflake table metadata and a business question/domain
description, sends it to Claude, and returns a first-pass semantic model
YAML ready for the user to review and edit.

The output follows the Snowflake Cortex Analyst semantic model spec as
defined in context/semantic_models/_TEMPLATE.yaml.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_TEMPLATE_PATH = Path(__file__).parent.parent.parent / "context" / "semantic_models" / "_TEMPLATE.yaml"

_SYSTEM_PROMPT = """You are an expert Snowflake data modeler and semantic layer architect.
Your job is to generate first-pass Snowflake Cortex Analyst semantic model YAML files
from raw table metadata.

Rules:
1. Follow the TEMPLATE exactly — do not add sections not in the template.
2. Write business-friendly names and descriptions in plain English.
3. Classify each column correctly: dimension, time_dimension, or measure.
4. For measures, always write the aggregation as SUM(col)/SUM(col) when it is a rate or ratio.
5. Add realistic synonyms (2–4 per field) that a business user would say out loud.
6. Add sample_values for dimension columns only.
7. Flag low-confidence fields with a comment starting: # LOW_CONFIDENCE:
8. Add guardrail_metric_pairings for every rate/percentage measure.
9. Add known_data_quirks for anything suspicious in the null rates or data types.
10. Output ONLY valid YAML — no explanation, no markdown fences, no extra text.
"""


def _build_prompt(
    domain_name: str,
    domain_description: str,
    business_question: str,
    metadata_markdown: str,
    template_yaml: str,
) -> str:
    return f"""Using the metadata below, generate a complete Snowflake Cortex Analyst semantic model YAML
for domain: {domain_name!r}

Business context / domain description:
{domain_description}

Primary business question this model must answer:
{business_question}

--- TABLE METADATA ---
{metadata_markdown}

--- TEMPLATE TO FOLLOW ---
{template_yaml}

Generate the full YAML now. Output only YAML, nothing else.
"""


def generate_semantic_yaml(
    domain_name: str,
    domain_description: str,
    business_question: str,
    metadata_markdown: str,
    model: str = "claude-sonnet-4-5",
    anthropic_api_key: str | None = None,
) -> str:
    """Call Claude to generate a semantic view YAML draft.

    Parameters
    ----------
    domain_name:
        Short identifier for the domain, e.g. 'walmart-opd'.
    domain_description:
        One paragraph describing the business domain.
    business_question:
        The primary analytical question the semantic view must support.
    metadata_markdown:
        Output of profiler.profiles_to_markdown().
    model:
        Claude model ID (without 'anthropic/' prefix).
    anthropic_api_key:
        API key. Falls back to ANTHROPIC_API_KEY env var.

    Returns the raw YAML string.
    """
    try:
        import anthropic
    except ImportError as exc:
        raise ImportError("anthropic package is required. Run: uv add anthropic") from exc

    template_yaml = ""
    if _TEMPLATE_PATH.exists():
        template_yaml = _TEMPLATE_PATH.read_text()
    else:
        logger.warning("Template YAML not found at %s — proceeding without it.", _TEMPLATE_PATH)

    prompt = _build_prompt(
        domain_name=domain_name,
        domain_description=domain_description,
        business_question=business_question,
        metadata_markdown=metadata_markdown,
        template_yaml=template_yaml,
    )

    api_key = anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY is not set. Set it in .env or pass anthropic_api_key= directly."
        )

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=8192,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    # Extract text content
    yaml_text = ""
    for block in response.content:
        if hasattr(block, "text"):
            yaml_text += block.text

    # Strip accidental markdown fences if the model added them
    yaml_text = yaml_text.strip()
    if yaml_text.startswith("```"):
        lines = yaml_text.splitlines()
        # Remove first and last fence lines
        inner = [l for l in lines if not l.strip().startswith("```")]
        yaml_text = "\n".join(inner).strip()

    logger.info(
        "Generated semantic YAML: %d chars, %d input tokens, %d output tokens",
        len(yaml_text),
        response.usage.input_tokens,
        response.usage.output_tokens,
    )

    return yaml_text


def validate_yaml(yaml_text: str) -> tuple[bool, str]:
    """Attempt to parse the generated YAML. Returns (is_valid, error_message)."""
    try:
        import yaml
        yaml.safe_load(yaml_text)
        return True, ""
    except Exception as exc:
        return False, str(exc)
