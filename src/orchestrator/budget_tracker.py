"""Token budget tracking.

MVP scope: telemetry only — no enforcement. Per pipeline-definitions.md §8 and the spec's
Part 12 §1, real budget enforcement is deferred until Week 1 telemetry tells us realistic
limits. This module accumulates per-stage usage and emits warnings at 75%/90%/100% of the
Question Framer's stated budget without blocking execution.

Cost estimates use the per-million-token prices from `config/pipeline_config.yaml`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


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
    stages: list[StageUsage] = field(default_factory=list)
    _warnings_emitted: set[float] = field(default_factory=set)

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
        self._check_warnings()
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

    def _check_warnings(self) -> None:
        if self.budget_tokens <= 0:
            return
        used = self.total_tokens()
        share = used / self.budget_tokens
        for threshold in (0.75, 0.90, 1.00):
            if share >= threshold and threshold not in self._warnings_emitted:
                self._warnings_emitted.add(threshold)
                logger.warning(
                    "Token usage at %.0f%% of budget (%d / %d). MVP is telemetry-only — execution continues.",
                    threshold * 100,
                    used,
                    self.budget_tokens,
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
