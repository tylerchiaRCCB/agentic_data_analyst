"""Tests for the Pydantic artifact schemas.

Verifies:
- All 10 agent payloads parse against the schema dispatch.
- The "empty arrays are valid" invariant holds for fields that the framing requires
  to be empty-able (findings_review, action_cards, opportunity_areas, etc.).
- The Statistic.lineage shape is required and structurally correct.
- Unknown fields are allowed (per schemas §5).
- Missing required fields raise ValidationError.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.orchestrator.schemas import (
    ActionCard,
    Caveat,
    CommunicationAgentPayload,
    DataRetrievalPayload,
    FindingsValidatorPayload,
    LineageRef,
    OpportunityIdentifierPayload,
    Statistic,
    validate_payload,
)


def test_minimal_caveat() -> None:
    c = Caveat(text="x", severity="low", reason="r")
    assert c.severity == "low"


def test_statistic_requires_lineage() -> None:
    with pytest.raises(ValidationError):
        Statistic(
            id="s1",
            metric="m",
            value=1.0,
            computation="c",
            sample_size=10,
        )  # missing lineage


def test_statistic_with_lineage() -> None:
    s = Statistic(
        id="s1",
        metric="m",
        value=1.0,
        computation="c",
        sample_size=10,
        lineage=LineageRef(source="ds-1", data_slice="x == 'y'", code_ref="run/x/exec/y"),
    )
    assert s.lineage.data_slice == "x == 'y'"


def test_findings_validator_payload_empty_findings_review_valid() -> None:
    """The framing-critical invariant: empty findings_review is valid (no findings to review)."""
    payload = FindingsValidatorPayload(
        overall_assessment="Nothing rose to action this period.",
        findings_review=[],
        cross_cutting_issues=[],
        guardrail_check_results=[],
        revalidation_summary={"findings_recomputed": 0, "discrepancies_found": 0},
    )
    assert payload.findings_review == []


def test_communication_agent_payload_empty_action_cards_valid() -> None:
    """Same: action_cards can be empty. Renders descriptive summary instead."""
    payload = CommunicationAgentPayload(
        output_mode="descriptive-summary",
        rendered_output_markdown="## Weekly Summary\n\nNothing rose to action.",
        action_cards=[],
        descriptive_summary={"conclusion": "All clear."},
    )
    assert payload.action_cards == []
    assert payload.descriptive_summary is not None


def test_opportunity_identifier_empty_opportunities_valid() -> None:
    payload = OpportunityIdentifierPayload(
        performance_gaps=[],
        opportunity_areas=[],
        intervention_recommendations=[],
        predictive_readiness_assessment={"candidates": []},
        sensitivity_analysis=[],
    )
    assert payload.opportunity_areas == []


def test_action_card_requires_all_fields() -> None:
    with pytest.raises(ValidationError):
        ActionCard(alert="x")  # type: ignore[call-arg]


def test_validate_payload_dispatches_by_agent() -> None:
    raw = {
        "overall_assessment": "x",
        "findings_review": [],
        "cross_cutting_issues": [],
        "guardrail_check_results": [],
        "revalidation_summary": {"findings_recomputed": 0, "discrepancies_found": 0},
    }
    result = validate_payload("findings-validator", raw)
    assert isinstance(result, FindingsValidatorPayload)


def test_unknown_fields_allowed() -> None:
    """Per schemas §5: agents may extend with unknown fields without breaking validation."""
    raw = {
        "overall_assessment": "x",
        "findings_review": [],
        "cross_cutting_issues": [],
        "guardrail_check_results": [],
        "revalidation_summary": {"findings_recomputed": 0, "discrepancies_found": 0},
        "extra_field": "should not break validation",
    }
    result = validate_payload("findings-validator", raw)
    assert isinstance(result, FindingsValidatorPayload)


# ---------------------------------------------------------------------------
# Regression tests for observed LLM-output variants.
# Each test pins a variant input -> canonical normalized output so the
# normalizer surface only grows.
# ---------------------------------------------------------------------------


def test_caveat_normalizer_accepts_detail_alias() -> None:
    """Observed variant: model returns `{detail: "...", title: "...", caveat_id: "..."}`
    instead of `{text: "..."}`. The normalizer should coerce `detail` to `text`."""
    c = Caveat.model_validate({
        "detail": "Domain context document not loaded; thresholds are inferred.",
        "severity": "high",
        "title": "Missing context",
        "caveat_id": "c1",
    })
    assert c.text == "Domain context document not loaded; thresholds are inferred."
    assert c.severity == "high"


def test_action_card_normalizer_extracts_grade_from_verbose_string() -> None:
    """Observed variant: model emits a verbose confidence string like
    `"HIGH (Grade B) -- Statistical case is grade-A..."` instead of the
    bare letter. The normalizer should extract `B`."""
    card = ActionCard.model_validate({
        "alert": "Instock dropped",
        "confidence": "HIGH (Grade B) -- Statistical case is grade-A...",
        "why_it_matters": "x",
        "root_cause": "x",
        "recommended_action": "x",
        "owner_role": "x",
        "due": "x",
        "follow_up_trigger": "x",
    })
    assert card.confidence == "B"


def test_action_card_normalizer_extracts_grade_dash_form() -> None:
    """The `grade-A` / `grade_C` form should also coerce."""
    card = ActionCard.model_validate({
        "alert": "x",
        "confidence": "grade-A confidence based on triangulation",
        "why_it_matters": "x",
        "root_cause": "x",
        "recommended_action": "x",
        "owner_role": "x",
        "due": "x",
        "follow_up_trigger": "x",
    })
    assert card.confidence == "A"


def test_data_retrieval_payload_coerces_dict_column_metadata() -> None:
    """Observed variant: model returns column_metadata as a dataset-level dict
    (`{total_columns: N, free_text_count: M}`) instead of a per-column list.
    The normalizer should rebuild the list from the schema field."""
    payload = DataRetrievalPayload.model_validate({
        "dataset_handle": "h",
        "data_source_type": "uploaded_file",
        "source_reference": "/tmp/x.csv",
        "row_count": 100,
        "schema": [
            {"name": "account_id", "dtype": "string", "nullable": False},
            {"name": "instock_pct", "dtype": "float", "nullable": True},
        ],
        "column_metadata": {"total_columns": 2, "free_text_count": 0},
    })
    assert isinstance(payload.column_metadata, list)
    assert len(payload.column_metadata) == 2
    assert payload.column_metadata[0].name == "account_id"
    assert payload.column_metadata[1].name == "instock_pct"
    assert payload.column_metadata[1].is_free_text is False


# ---------------------------------------------------------------------------
# Structural-rigor enforcement on Statistic.
# A group_comparison/correlation/regression statistic without effect_size or
# confidence_interval cannot be validated — the artifact itself rejects it.
# ---------------------------------------------------------------------------


def test_statistic_descriptive_kind_does_not_require_effect_size() -> None:
    """Descriptive statistics (means, counts) are exempt from the effect-size rule."""
    from src.orchestrator.schemas import Statistic, LineageRef
    s = Statistic(
        id="s1", metric="mean_volume", value=142.5, computation="df.volume.mean()",
        sample_size=1000, statistic_kind="descriptive",
        lineage=LineageRef(source="dataset", data_slice="all", code_ref="cell_12"),
    )
    assert s.statistic_kind == "descriptive"


def test_statistic_group_comparison_requires_effect_size() -> None:
    """A group_comparison statistic without effect_size raises ValidationError."""
    from pydantic import ValidationError
    from src.orchestrator.schemas import Statistic, LineageRef
    with pytest.raises(ValidationError) as exc:
        Statistic(
            id="s1", metric="volume_diff", value=12.3,
            computation="mannwhitneyu(a, b)",
            sample_size=200,
            p_value=0.001,
            confidence_interval={"lower": 5.0, "upper": 20.0, "level": 0.95},
            statistic_kind="group_comparison",
            # effect_size MISSING
            lineage=LineageRef(source="dataset", data_slice="region=NE,SE", code_ref="cell_5"),
        )
    assert "effect_size" in str(exc.value)


def test_statistic_correlation_requires_confidence_interval() -> None:
    """A correlation statistic without confidence_interval raises ValidationError."""
    from pydantic import ValidationError
    from src.orchestrator.schemas import Statistic, LineageRef
    with pytest.raises(ValidationError) as exc:
        Statistic(
            id="s1", metric="spearman_rho", value=-0.235,
            computation="spearmanr(x, y)",
            sample_size=97,
            p_value=0.067,
            effect_size={"kind": "spearman_rho", "value": -0.235},
            # confidence_interval MISSING
            statistic_kind="correlation",
            lineage=LineageRef(source="dataset", data_slice="all", code_ref="cell_8"),
        )
    assert "confidence_interval" in str(exc.value)


def test_statistic_other_kind_is_unenforced_for_backward_compat() -> None:
    """Legacy artifacts without statistic_kind default to 'other' — no enforcement."""
    from src.orchestrator.schemas import Statistic, LineageRef
    s = Statistic(
        id="s1", metric="something", value=1.0, computation="x",
        sample_size=10,
        lineage=LineageRef(source="dataset", data_slice="all", code_ref="cell_1"),
    )
    assert s.statistic_kind == "other"
    # No effect_size required, no CI required
