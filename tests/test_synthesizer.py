"""Tests for the Synthesizer Agent + the synthesize_runs tool."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.orchestrator.schemas import (
    CrossRunConnection,
    CrossRunNonConnection,
    SynthesizerPayload,
    agent_output_tool,
    validate_payload,
)
from tests.mocks.mock_claude_client import fixture_payload, fixture_text


def test_synthesizer_payload_minimal_valid() -> None:
    """An empty synthesis (no connections, no non-connections) is a valid output —
    same first-class-null-result discipline as the per-function null."""
    payload = SynthesizerPayload(
        source_run_ids=["r1", "r2"],
        period_examined="week of 2026-05-20",
        rendered_output_markdown="# Synthesis\n\nNo connections worth surfacing.",
    )
    assert payload.connections == []
    assert payload.non_connections == []


def test_synthesizer_payload_loads_fixture() -> None:
    """The bundled minimal fixture parses against the schema."""
    payload = SynthesizerPayload.model_validate(fixture_payload("synthesizer-agent_minimal.json"))
    assert len(payload.connections) == 1
    assert payload.connections[0].grade == "B"
    assert len(payload.non_connections) == 1
    assert payload.non_connections[0].source_finding["finding_id"] == "f2"


def test_cross_run_connection_requires_fields() -> None:
    """A CrossRunConnection without entity_overlap or mechanism cannot validate."""
    with pytest.raises(ValidationError):
        CrossRunConnection(
            id="c1",
            source_findings=[],
            grade="B",
            # missing entity_overlap, time_overlap, mechanism
        )  # type: ignore[call-arg]


def test_cross_run_non_connection_requires_fields() -> None:
    """A non-connection must name where the connection would appear and why it didn't."""
    with pytest.raises(ValidationError):
        CrossRunNonConnection(
            id="nc1",
            source_finding={"run_id": "r1", "finding_id": "f1"},
            # missing where_connection_would_appear, why_no_connection
        )  # type: ignore[call-arg]


def test_synthesizer_dispatched_via_validate_payload() -> None:
    """The agent registers under PAYLOAD_BY_AGENT and routes correctly."""
    result = validate_payload("synthesizer-agent", fixture_payload("synthesizer-agent_minimal.json"))
    assert isinstance(result, SynthesizerPayload)


def test_synthesizer_output_tool_is_anthropic_valid() -> None:
    """The synthesizer's tool spec follows the same conventions as the others."""
    tool = agent_output_tool("synthesizer-agent")
    assert tool["name"] == "emit_synthesizer_agent_artifact"
    assert "description" in tool
    schema = tool["input_schema"]
    assert schema.get("type") == "object"
    assert "properties" in schema
    # Required top-level keys carry through
    assert "source_run_ids" in schema["properties"]
    assert "connections" in schema["properties"]
    assert "non_connections" in schema["properties"]


def test_synthesizer_normalizer_coerces_source_runs_alias() -> None:
    """A model emitting source_runs instead of source_run_ids should still validate."""
    payload = SynthesizerPayload.model_validate({
        "source_runs": ["r1", "r2"],
        "period_examined": "week of 2026-05-20",
        "rendered_output_markdown": "x",
    })
    assert payload.source_run_ids == ["r1", "r2"]


def test_synthesize_runs_tool_requires_at_least_two_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The CLI tool refuses to run with fewer than 2 source runs (synthesis needs at least 2)."""
    from src.tools import synthesize_runs

    monkeypatch.setattr("sys.argv", ["synthesize_runs", "--run-ids", "only-one-run"])
    rc = synthesize_runs.main()
    assert rc == 2  # exit code for "need ≥2 runs"


def test_hitl_gate_applies_to_synthesis_connections(tmp_path: Path) -> None:
    """When a synthesis produces a grade-A connection and HITL threshold is 'A',
    the gate evaluates correctly with the connections-shaped input.

    Validates the integration between synthesize_runs.py and hitl_gate.evaluate —
    that synthesis findings flow through the same human-review gate as
    per-function findings.
    """
    from src.orchestrator.hitl_gate import evaluate

    # Build a synthesis-action-cards-shaped payload (what synthesize_runs.py constructs
    # to pass to the HITL gate)
    synthesis_action_cards = [
        {
            "alert": "Sales gap × supply tightness on SKU-7",
            "confidence": "A",
            "why_it_matters": "Cross-functional connection.",
            "recommended_action": "Coordinate sales + supply on SKU-7",
            "caveats": [],
        }
    ]
    decision = evaluate(
        run_id="synthesis-test",
        output_dir=tmp_path,
        comms_payload={"action_cards": synthesis_action_cards, "output_mode": "action-card"},
        threshold="A",
    )
    assert decision.gated is True
    assert decision.final_md_path.name == "synthesis-test-pending-review.md"
    assert len(decision.findings_triggering_review) == 1
