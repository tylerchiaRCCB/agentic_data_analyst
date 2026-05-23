"""Token + cost budget tracking with hard enforcement.

Accumulates per-stage usage and:
- Emits soft warnings at configurable fractions of the cost cap (default 50/75/90%).
- Raises `BudgetExceeded` when cumulative cost crosses `max_cost_usd`. The pipeline
  catches this and aborts cleanly, preserving the current stage's artifact.

Token budget tracking remains telemetry-only (the QuestionFramer's token_budget is
advisory). Cost enforcement is the production-safety guarantee.

Cost estimates use the per-million-token prices from `config/pipeline_config.yaml`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


class BudgetExceeded(RuntimeError):
    """Raised by BudgetTracker.record() when cumulative cost crosses max_cost_usd.

    Carries the total cost and the configured cap so the orchestrator can
    surface them in the failure report.
    """

    def __init__(self, total_cost_usd: float, max_cost_usd: float, stage_index: int, agent: str) -> None:
        self.total_cost_usd = total_cost_usd
        self.max_cost_usd = max_cost_usd
        self.stage_index = stage_index
        self.agent = agent
        super().__init__(
            f"Cost cap exceeded after stage {stage_index} ({agent}): "
            f"${total_cost_usd:.4f} > ${max_cost_usd:.4f}. Pipeline aborted."
        )


@dataclass
class StageUsage:
    stage_index: int
    agent: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0


@dataclass
class BudgetTracker:
    budget_tokens: int  # from QuestionFramerPayload.token_budget
    cost_per_million: dict[str, dict[str, float]] = field(default_factory=dict)
    max_cost_usd: float | None = None  # hard cap; None disables enforcement
    cost_warning_thresholds: list[float] = field(default_factory=lambda: [0.5, 0.75, 0.9])
    stages: list[StageUsage] = field(default_factory=list)
    _token_warnings_emitted: set[float] = field(default_factory=set)
    _cost_warnings_emitted: set[float] = field(default_factory=set)

    def record(
        self,
        *,
        stage_index: int,
        agent: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> StageUsage:
        cost = self._compute_cost(model, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens)
        usage = StageUsage(
            stage_index=stage_index,
            agent=agent,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
            cost_usd=cost,
        )
        self.stages.append(usage)
        self._check_token_warnings()
        self._check_cost(stage_index=stage_index, agent=agent)
        return usage

    def _compute_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_read: int,
        cache_write: int,
    ) -> float:
        pricing = self.cost_per_million.get(model)
        if not pricing:
            return 0.0
        in_per_m = pricing.get("input", 0.0)
        out_per_m = pricing.get("output", 0.0)
        cache_read_per_m = pricing.get("cache_read", in_per_m * 0.1)
        cache_write_per_m = pricing.get("cache_write", in_per_m * 1.25)
        return (
            input_tokens * in_per_m
            + output_tokens * out_per_m
            + cache_read * cache_read_per_m
            + cache_write * cache_write_per_m
        ) / 1_000_000.0

    def total_tokens(self) -> int:
        return sum(s.input_tokens + s.output_tokens for s in self.stages)

    def total_cost(self) -> float:
        return sum(s.cost_usd for s in self.stages)

    def _check_token_warnings(self) -> None:
        if self.budget_tokens <= 0:
            return
        used = self.total_tokens()
        share = used / self.budget_tokens
        for threshold in (0.75, 0.90, 1.00):
            if share >= threshold and threshold not in self._token_warnings_emitted:
                self._token_warnings_emitted.add(threshold)
                logger.warning(
                    "Token usage at %.0f%% of advisory budget (%d / %d). Execution continues.",
                    threshold * 100,
                    used,
                    self.budget_tokens,
                )

    def _check_cost(self, *, stage_index: int, agent: str) -> None:
        if self.max_cost_usd is None or self.max_cost_usd <= 0:
            return
        total = self.total_cost()
        share = total / self.max_cost_usd
        # Soft warnings (under the hard cap)
        for threshold in self.cost_warning_thresholds:
            if share >= threshold and threshold not in self._cost_warnings_emitted:
                self._cost_warnings_emitted.add(threshold)
                logger.warning(
                    "Cost at %.0f%% of cap ($%.4f / $%.2f) after stage %d (%s).",
                    threshold * 100,
                    total,
                    self.max_cost_usd,
                    stage_index,
                    agent,
                )
        # Hard cap: abort
        if total > self.max_cost_usd:
            raise BudgetExceeded(
                total_cost_usd=total,
                max_cost_usd=self.max_cost_usd,
                stage_index=stage_index,
                agent=agent,
            )

    def summary(self) -> dict[str, Any]:
        return {
            "budget_tokens": self.budget_tokens,
            "total_tokens": self.total_tokens(),
            "total_cost_usd": round(self.total_cost(), 4),
            "stages": [
                {
                    "stage_index": s.stage_index,
                    "agent": s.agent,
                    "input_tokens": s.input_tokens,
                    "output_tokens": s.output_tokens,
                    "cost_usd": round(s.cost_usd, 4),
                }
                for s in self.stages
            ],
        }
