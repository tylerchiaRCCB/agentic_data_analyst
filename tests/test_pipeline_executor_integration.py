"""Integration tests for PipelineExecutor with a mocked Claude SDK.

These exercise the orchestrator's failure-recovery + retry + skip-and-flag +
hard-fail + budget-cap paths without spending real API tokens. Standard practice
in production AI systems: orchestration logic must be testable end-to-end via
mocks, otherwise regressions are only caught by $10 full runs.

Each test:
1. Builds a MockClaudeClient with a scripted response queue per agent.
2. Constructs the same PipelineExecutor the real entry point would.
3. Asserts on the resulting PipelineRun's status, caveats, and stage_results.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.orchestrator.budget_tracker import BudgetTracker
from src.orchestrator.lineage_tracker import LineageTracker
from src.orchestrator.pipeline_executor import PipelineConfig, PipelineExecutor
from src.orchestrator.schemas import QuestionFramerPayload
from src.observability.run_logger import RunLogger
from src.observability.tracer import Tracer
from tests.mocks.mock_claude_client import MockClaudeClient, fixture_payload, fixture_text


# Models map for the mock. The mock doesn't care about model names, but the
# PipelineConfig must list one per agent.
MODELS = {
    "question-framer": "claude-sonnet-4-6",
    "data-retrieval-agent": "claude-sonnet-4-6",
    "data-profiler": "claude-sonnet-4-6",
    "relationship-analyzer": "claude-sonnet-4-6",
    "pattern-discoverer": "claude-sonnet-4-6",
    "time-series-analyzer": "claude-sonnet-4-6",
    "root-cause-investigator": "claude-opus-4-7",
    "opportunity-identifier": "claude-opus-4-7",
    "findings-validator": "claude-opus-4-7",
    "communication-agent": "claude-sonnet-4-6",
}

PRICING = {
    "claude-opus-4-7": {"input": 15.0, "output": 75.0, "cache_read": 1.5, "cache_write": 18.75},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0, "cache_read": 0.3, "cache_write": 3.75},
}


def _make_executor(
    mock: MockClaudeClient,
    tmp_path: Path,
    *,
    max_cost_usd: float | None = None,
) -> tuple[PipelineExecutor, RunLogger]:
    run_logger = RunLogger("test-run", runs_root=tmp_path)
    tracer = Tracer(run_id="test-run")
    budget = BudgetTracker(
        budget_tokens=1_200_000,
        cost_per_million=PRICING,
        max_cost_usd=max_cost_usd,
    )
    lineage = LineageTracker(run_id="test-run")
    config = PipelineConfig(
        model_per_agent=MODELS,
        max_tokens_per_call=16384,
        max_retries_per_stage=1,
    )
    executor = PipelineExecutor(
        client=mock,  # type: ignore[arg-type]  # MockClaudeClient duck-types ClaudeClient
        config=config,
        run_logger=run_logger,
        tracer=tracer,
        budget=budget,
        lineage=lineage,
        domain=None,
    )
    return executor, run_logger


def _short_framer_payload() -> QuestionFramerPayload:
    """Load the test pipeline fixture: framer with a 3-stage serial pipeline
    (data-retrieval → data-profiler → communication-agent)."""
    return QuestionFramerPayload.model_validate(fixture_payload("question-framer_test-pipeline.json"))


def test_pipeline_happy_path_runs_all_stages(tmp_path: Path) -> None:
    """All scripted responses are valid → all stages OK → run.status == 'ok'."""
    mock = MockClaudeClient({
        "data-retrieval-agent": [fixture_text("data-retrieval-agent_minimal.json")],
        "data-profiler": [fixture_text("data-profiler_minimal.json")],
        "communication-agent": [fixture_text("communication-agent_minimal.json")],
    })
    executor, _ = _make_executor(mock, tmp_path)
    run = executor.execute_pipeline(_short_framer_payload())

    assert run.status == "ok"
    assert len(run.stage_results) == 3
    assert [s.agent for s in run.stage_results] == [
        "data-retrieval-agent", "data-profiler", "communication-agent"
    ]
    assert all(s.status == "ok" for s in run.stage_results)
    # All 3 agents got called exactly once
    assert len([c for c in mock.calls if c["agent"] == "data-retrieval-agent"]) == 1
    assert len([c for c in mock.calls if c["agent"] == "data-profiler"]) == 1
    assert len([c for c in mock.calls if c["agent"] == "communication-agent"]) == 1


def test_pipeline_retries_once_on_schema_failure(tmp_path: Path) -> None:
    """First response is malformed JSON; second response is valid. Agent succeeds with attempt count of 2."""
    mock = MockClaudeClient({
        "data-retrieval-agent": [
            "this is not json at all",  # first call: garbage
            fixture_text("data-retrieval-agent_minimal.json"),  # retry: valid
        ],
        "data-profiler": [fixture_text("data-profiler_minimal.json")],
        "communication-agent": [fixture_text("communication-agent_minimal.json")],
    })
    executor, _ = _make_executor(mock, tmp_path)
    run = executor.execute_pipeline(_short_framer_payload())

    assert run.status == "ok"
    assert len([c for c in mock.calls if c["agent"] == "data-retrieval-agent"]) == 2
    # All stages ultimately produced artifacts
    assert all(s.status == "ok" for s in run.stage_results)


def test_pipeline_hard_fails_on_critical_agent_failure(tmp_path: Path) -> None:
    """data-retrieval-agent (critical) fails twice → run.status='failed', subsequent stages do not run."""
    mock = MockClaudeClient({
        "data-retrieval-agent": [
            "garbage 1",
            "garbage 2",  # exhausts retries; agent fails permanently
        ],
        # These should never be called
        "data-profiler": [fixture_text("data-profiler_minimal.json")],
        "communication-agent": [fixture_text("communication-agent_minimal.json")],
    })
    executor, run_logger = _make_executor(mock, tmp_path)
    run = executor.execute_pipeline(_short_framer_payload())

    assert run.status == "failed"
    # Failure report should have been written
    assert (run_logger.run_dir / f"{run.run_id}-failure.md").exists()
    # data-profiler and communication-agent were never called
    assert len([c for c in mock.calls if c["agent"] == "data-profiler"]) == 0
    assert len([c for c in mock.calls if c["agent"] == "communication-agent"]) == 0


def test_pipeline_aborts_when_cost_cap_exceeded(tmp_path: Path) -> None:
    """Cost cap is small enough that the first stage's reported tokens cross it.
    Run should abort with status='failed' and a budget_exceeded caveat."""
    # First response carries huge cost numbers via the dict form
    big_usage = {
        "text": fixture_text("data-retrieval-agent_minimal.json"),
        "input_tokens": 200_000,
        "output_tokens": 50_000,
    }
    # Opus pricing: 200k*15 + 50k*75 per million = $3 + $3.75 = $6.75 — but data-retrieval uses Sonnet
    # Sonnet pricing: 200k*3 + 50k*15 per million = $0.60 + $0.75 = $1.35 → triggers cap of $1.0
    mock = MockClaudeClient({
        "data-retrieval-agent": [big_usage],
        # Subsequent stages should not be called
        "data-profiler": [fixture_text("data-profiler_minimal.json")],
        "communication-agent": [fixture_text("communication-agent_minimal.json")],
    })
    executor, run_logger = _make_executor(mock, tmp_path, max_cost_usd=1.0)
    run = executor.execute_pipeline(_short_framer_payload())

    assert run.status == "failed"
    # The budget-exceeded caveat should be present
    assert any("Pipeline aborted: cumulative cost" in c["text"] for c in run.run_caveats)
    # Subsequent stages never ran
    assert len([c for c in mock.calls if c["agent"] == "data-profiler"]) == 0


def test_pipeline_artifacts_pin_prompt_hashes(tmp_path: Path) -> None:
    """Every artifact must carry prompt_sha256 + skill_hashes for reproducibility."""
    mock = MockClaudeClient({
        "data-retrieval-agent": [fixture_text("data-retrieval-agent_minimal.json")],
        "data-profiler": [fixture_text("data-profiler_minimal.json")],
        "communication-agent": [fixture_text("communication-agent_minimal.json")],
    })
    executor, run_logger = _make_executor(mock, tmp_path)
    run = executor.execute_pipeline(_short_framer_payload())

    assert run.status == "ok"
    # Inspect each stage's saved artifact
    artifacts_dir = run_logger.run_dir / "artifacts"
    saved = sorted(artifacts_dir.glob("*.json"))
    assert len(saved) == 3
    for path in saved:
        art = json.loads(path.read_text())
        assert "prompt_sha256" in art, f"{path.name} missing prompt_sha256"
        assert len(art["prompt_sha256"]) == 64
        assert "skill_hashes" in art
        assert "universal" in art["skill_hashes"]
        assert "agent_block" in art["skill_hashes"]


def test_pipeline_structured_logs_emitted(tmp_path: Path) -> None:
    """The run should produce a run.jsonl with structured log lines."""
    mock = MockClaudeClient({
        "data-retrieval-agent": [fixture_text("data-retrieval-agent_minimal.json")],
        "data-profiler": [fixture_text("data-profiler_minimal.json")],
        "communication-agent": [fixture_text("communication-agent_minimal.json")],
    })
    executor, run_logger = _make_executor(mock, tmp_path)
    executor.execute_pipeline(_short_framer_payload())

    jsonl_path = run_logger.run_dir / "run.jsonl"
    assert jsonl_path.exists()
    lines = jsonl_path.read_text().strip().splitlines()
    assert len(lines) > 0
    # Each line must be valid JSON
    for line in lines:
        obj = json.loads(line)
        assert "level" in obj
        assert "ts" in obj
        assert "run_id" in obj
        assert "msg" in obj


def test_pipeline_prefers_tool_output_over_text(tmp_path: Path) -> None:
    """When the mock supplies both tool_output and text, the executor uses tool_output.

    This exercises the structured-output enforcement path: Claude emits the artifact
    via tool_use rather than free-form JSON, and the executor takes that as-is.
    """
    from src.api.claude_client import ClaudeResponse

    # Construct a response with tool_output set to a valid artifact, and text set to
    # garbage. Tool_output should win.
    valid_artifact = fixture_payload("data-retrieval-agent_minimal.json")

    def make_response_with_tool_output() -> ClaudeResponse:
        return ClaudeResponse(
            text="this would fail to parse if used",
            stop_reason="end_turn",
            input_tokens=100,
            output_tokens=50,
            cache_read_tokens=0,
            cache_write_tokens=0,
            raw=None,
            tool_output=valid_artifact,
        )

    class _PatchedMock(MockClaudeClient):
        def call(self, **kwargs):  # type: ignore[override]
            agent = self._detect_agent(kwargs.get("system", []))
            self.calls.append({"agent": agent, "model": kwargs.get("model", "")})
            if agent == "data-retrieval-agent":
                return make_response_with_tool_output()
            # Other agents: usual queue-based path
            queue = self._queues.get(agent)
            nxt = queue.popleft()  # type: ignore[union-attr]
            return ClaudeResponse(
                text=nxt if isinstance(nxt, str) else "",
                stop_reason="end_turn",
                input_tokens=100, output_tokens=50,
                cache_read_tokens=0, cache_write_tokens=0,
                raw=None, tool_output=None,
            )

    mock = _PatchedMock({
        "data-profiler": [fixture_text("data-profiler_minimal.json")],
        "communication-agent": [fixture_text("communication-agent_minimal.json")],
    })
    executor, _ = _make_executor(mock, tmp_path)
    run = executor.execute_pipeline(_short_framer_payload())

    assert run.status == "ok"
    # Specifically: data-retrieval-agent succeeded despite garbage text — because
    # tool_output was preferred.
    retrieval_results = [s for s in run.stage_results if s.agent == "data-retrieval-agent"]
    assert len(retrieval_results) == 1
    assert retrieval_results[0].status == "ok"


def test_agent_output_tool_generates_valid_anthropic_tool_spec() -> None:
    """Each agent's output_tool spec has the required Anthropic tool shape."""
    from src.orchestrator.schemas import PAYLOAD_BY_AGENT, agent_output_tool

    for agent in PAYLOAD_BY_AGENT:
        tool = agent_output_tool(agent)
        assert "name" in tool
        assert tool["name"].startswith("emit_")
        assert tool["name"].endswith("_artifact")
        assert "description" in tool
        assert "input_schema" in tool
        schema = tool["input_schema"]
        assert schema.get("type") == "object"
        assert "properties" in schema
        # Pydantic decorations should be stripped:
        assert "title" not in schema  # only at root
