"""Lineage tracking — collects every claim's provenance into a single manifest.

Per pipeline-definitions.md §9 and failure-recovery.md, every numeric claim that reaches
the recipient must trace to:
  - the source dataset (file or table reference)
  - the data slice (filter expression — never inline data values)
  - the code that produced it (code_ref pointing to the executed code in the sandbox)
  - the agent that produced the claim

The Statistic objects emitted by each agent carry this information. This module gathers
them across the pipeline run and writes a `lineage.json` manifest at run end.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class LineageTracker:
    run_id: str
    entries: list[dict[str, Any]] = field(default_factory=list)

    def add_statistic(self, *, agent: str, stage_index: int, statistic: dict[str, Any]) -> None:
        """Record one Statistic from an agent's artifact."""
        entry = {
            "agent": agent,
            "stage_index": stage_index,
            "statistic_id": statistic.get("id"),
            "metric": statistic.get("metric"),
            "value": statistic.get("value"),
            "unit": statistic.get("unit"),
            "computation": statistic.get("computation"),
            "sample_size": statistic.get("sample_size"),
            "lineage": statistic.get("lineage"),
        }
        self.entries.append(entry)

    def add_artifact_statistics(self, *, agent: str, stage_index: int, payload: dict[str, Any]) -> None:
        """Convenience: pull all `statistics` from a payload."""
        for stat in payload.get("statistics", []) or []:
            self.add_statistic(agent=agent, stage_index=stage_index, statistic=stat)

    def manifest(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "statistic_count": len(self.entries),
            "entries": self.entries,
        }

    def write(self, path: Path) -> Path:
        with path.open("w", encoding="utf-8") as f:
            json.dump(self.manifest(), f, indent=2, default=str)
        return path
