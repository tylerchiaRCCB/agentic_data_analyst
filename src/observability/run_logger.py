"""Per-run file-based logger.

Each pipeline run gets its own directory under `runs/<run_id>/` containing:
- `run.log` — structured log lines (one per event)
- `spans.jsonl` — span trace from the Tracer
- `artifacts/<stage_index>-<agent>.json` — artifact dumps for replay/audit
- `lineage.json` — final lineage manifest (written by lineage_tracker)
- `<run_id>-failure.md` — operator-facing failure report (only on hard-fail)

Stdout receives a brief, human-readable summary line per event so live demos and
console runs show progress without grepping log files.

Production swaps this for OpenTelemetry per the spec's Part 7.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_RUNS_ROOT = Path("runs")


def make_run_id() -> str:
    """Run IDs are ISO-timestamp-sortable so `ls` orders runs chronologically."""
    return datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + _short_uuid()


def _short_uuid() -> str:
    import uuid

    return uuid.uuid4().hex[:8]


class RunLogger:
    """Per-run logger writing to both a file and stdout."""

    def __init__(self, run_id: str, runs_root: Path = DEFAULT_RUNS_ROOT) -> None:
        self.run_id = run_id
        self.run_dir = runs_root / run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        (self.run_dir / "artifacts").mkdir(exist_ok=True)

        # Python logger setup — write to run.log and stdout
        self._logger = logging.getLogger(f"run.{run_id}")
        self._logger.setLevel(logging.INFO)
        # Avoid duplicate handlers if RunLogger is constructed twice for the same id
        if not self._logger.handlers:
            file_handler = logging.FileHandler(self.run_dir / "run.log", encoding="utf-8")
            file_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s %(levelname)s %(message)s",
                    datefmt="%Y-%m-%dT%H:%M:%SZ",
                )
            )
            self._logger.addHandler(file_handler)

            stdout_handler = logging.StreamHandler(sys.stdout)
            stdout_handler.setFormatter(logging.Formatter("%(message)s"))
            self._logger.addHandler(stdout_handler)

    # ---------- General logging ----------

    def info(self, msg: str, **fields: Any) -> None:
        self._logger.info(self._format(msg, fields))

    def warning(self, msg: str, **fields: Any) -> None:
        self._logger.warning(self._format(msg, fields))

    def error(self, msg: str, **fields: Any) -> None:
        self._logger.error(self._format(msg, fields))

    @staticmethod
    def _format(msg: str, fields: dict[str, Any]) -> str:
        if not fields:
            return msg
        extras = " ".join(f"{k}={v!r}" for k, v in fields.items())
        return f"{msg} | {extras}"

    # ---------- Artifact persistence ----------

    def write_artifact(self, stage_index: int, agent: str, artifact: dict[str, Any]) -> Path:
        """Persist a stage's artifact for replay/audit."""
        path = self.run_dir / "artifacts" / f"{stage_index:02d}-{agent}.json"
        with path.open("w", encoding="utf-8") as f:
            json.dump(artifact, f, indent=2, default=str)
        return path

    def write_spans(self, jsonl: str) -> Path:
        path = self.run_dir / "spans.jsonl"
        path.write_text(jsonl, encoding="utf-8")
        return path

    def write_failure_report(self, content: str) -> Path:
        path = self.run_dir / f"{self.run_id}-failure.md"
        path.write_text(content, encoding="utf-8")
        return path

    def write_lineage(self, lineage: dict[str, Any]) -> Path:
        path = self.run_dir / "lineage.json"
        with path.open("w", encoding="utf-8") as f:
            json.dump(lineage, f, indent=2, default=str)
        return path
