"""Tests for the BudgetTracker — hard cost cap + soft warnings."""

from __future__ import annotations

import pytest

from src.orchestrator.budget_tracker import BudgetExceeded, BudgetTracker


PRICING = {
    "claude-opus-4-7": {"input": 15.0, "output": 75.0, "cache_read": 1.5, "cache_write": 18.75},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0, "cache_read": 0.3, "cache_write": 3.75},
}


def _tracker(*, max_cost: float | None) -> BudgetTracker:
    return BudgetTracker(
        budget_tokens=1_000_000,
        cost_per_million=PRICING,
        max_cost_usd=max_cost,
        cost_warning_thresholds=[0.5, 0.75, 0.9],
    )


def test_budget_tracker_under_cap_allows_recording() -> None:
    b = _tracker(max_cost=10.0)
    # Sonnet: 100k input, 10k output = 100_000*3 + 10_000*15 per million = 0.3 + 0.15 = $0.45
    b.record(stage_index=1, agent="data-profiler", model="claude-sonnet-4-6",
             input_tokens=100_000, output_tokens=10_000)
    assert b.total_cost() < 1.0


def test_budget_tracker_raises_when_cap_exceeded() -> None:
    b = _tracker(max_cost=1.0)
    # Opus: 200k input + 50k output = 200*15 + 50*75 per million = 3.0 + 3.75 = $6.75
    with pytest.raises(BudgetExceeded) as exc:
        b.record(stage_index=1, agent="findings-validator", model="claude-opus-4-7",
                 input_tokens=200_000, output_tokens=50_000)
    assert exc.value.total_cost_usd > 1.0
    assert exc.value.max_cost_usd == 1.0
    assert exc.value.stage_index == 1
    assert exc.value.agent == "findings-validator"


def test_budget_tracker_disabled_when_cap_is_none() -> None:
    b = _tracker(max_cost=None)
    # Should not raise no matter the cost
    b.record(stage_index=1, agent="findings-validator", model="claude-opus-4-7",
             input_tokens=10_000_000, output_tokens=1_000_000)
    assert b.total_cost() > 100  # huge, but no raise


def test_budget_tracker_soft_warnings_emit_once(caplog: pytest.LogCaptureFixture) -> None:
    """Each warning threshold fires at most once per run."""
    import logging
    caplog.set_level(logging.WARNING)
    b = _tracker(max_cost=10.0)
    # First call: crosses 50% (cost ~$6) — emits 50% warning
    b.record(stage_index=1, agent="findings-validator", model="claude-opus-4-7",
             input_tokens=200_000, output_tokens=40_000)  # $3 + $3 = $6
    # Second call: small additional usage; should NOT re-emit 50%
    pre_warnings = sum(1 for r in caplog.records if "50%" in r.message)
    b.record(stage_index=2, agent="root-cause-investigator", model="claude-sonnet-4-6",
             input_tokens=10_000, output_tokens=1_000)
    post_warnings = sum(1 for r in caplog.records if "50%" in r.message)
    assert post_warnings == pre_warnings  # not re-emitted
