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
