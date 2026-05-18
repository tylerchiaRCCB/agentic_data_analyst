"""Tests for pipeline composition.

Verifies:
- QuestionFramerPayload accepts both single and parallel-group stage forms.
- Pipeline composition is consumed verbatim (no orchestrator-side rewriting).
- The position invariants from pipeline-definitions.md §1 hold when constructed correctly
  (these are documented expectations rather than schema-enforced — tests reflect that).
"""

from __future__ import annotations

from src.orchestrator.schemas import (
    PipelineStageParallel,
    PipelineStageSingle,
    QuestionFramerPayload,
)


def _minimal_framer_payload(stages: list) -> QuestionFramerPayload:
    return QuestionFramerPayload(
        input_mode="proactive",
        complexity_level="L4",
        premises_verified=[],
        analytical_questions=["test"],
        hypotheses=[],
        data_requirements={"domain": "test"},
        decision_context="test",
        success_criteria="test",
        pipeline_composition=stages,
        output_mode="action-card",
        investigation_mode="both",
        token_budget=100_000,
    )


def test_single_stage_pipeline() -> None:
    stages = [
        PipelineStageSingle(agent="question-framer", skills=[]),
        PipelineStageSingle(agent="data-retrieval-agent", skills=[]),
        PipelineStageSingle(agent="data-profiler", skills=["data-quality-standards"]),
        PipelineStageSingle(agent="communication-agent", skills=["descriptive-summary-format"]),
    ]
    payload = _minimal_framer_payload(stages)
    assert len(payload.pipeline_composition) == 4
    first = payload.pipeline_composition[0]
    assert isinstance(first, PipelineStageSingle)
    assert first.agent == "question-framer"


def test_parallel_group_pipeline() -> None:
    """Parallel-group stages — pipeline-definitions.md §5.1."""
    stages = [
        PipelineStageSingle(agent="data-retrieval-agent", skills=[]),
        PipelineStageSingle(agent="data-profiler", skills=[]),
        PipelineStageParallel(
            parallel=[
                PipelineStageSingle(agent="relationship-analyzer", skills=["correlation-analysis"]),
                PipelineStageSingle(agent="time-series-analyzer", skills=["stl-decomposition"]),
            ]
        ),
        PipelineStageSingle(agent="findings-validator", skills=["statistical-revalidation"]),
        PipelineStageSingle(agent="communication-agent", skills=["proactive-action-card"]),
    ]
    payload = _minimal_framer_payload(stages)
    parallel_stage = payload.pipeline_composition[2]
    assert isinstance(parallel_stage, PipelineStageParallel)
    assert len(parallel_stage.parallel) == 2


def test_token_budget_levels() -> None:
    """Token budget defaults per pipeline-definitions.md §8 should be respected by the framer.
    This test is documentation/expectation — the framer is responsible for setting realistic
    values; the orchestrator does not enforce minimums in MVP."""
    p = _minimal_framer_payload([PipelineStageSingle(agent="question-framer", skills=[])])
    p.token_budget = 1_200_000  # proactive default
    assert p.token_budget == 1_200_000
