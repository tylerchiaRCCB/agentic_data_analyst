"""Tests for structured JSON logging in RunLogger."""

from __future__ import annotations

import json
from pathlib import Path

from src.observability.run_logger import RunLogger


def test_run_logger_writes_jsonl(tmp_path: Path) -> None:
    rl = RunLogger("test-run-123", runs_root=tmp_path)
    rl.info("Pipeline started", stage_index=1, agent="data-profiler")
    rl.warning("Some warning", reason="threshold")
    rl.error("Some error", error_code="E001")

    jsonl_path = tmp_path / "test-run-123" / "run.jsonl"
    assert jsonl_path.exists()
    lines = jsonl_path.read_text().strip().splitlines()
    assert len(lines) == 3

    first = json.loads(lines[0])
    assert first["level"] == "INFO"
    assert first["run_id"] == "test-run-123"
    assert "Pipeline started" in first["msg"]
    assert first["attrs"]["stage_index"] == 1
    assert first["attrs"]["agent"] == "data-profiler"
    assert "ts" in first

    second = json.loads(lines[1])
    assert second["level"] == "WARNING"
    assert second["attrs"]["reason"] == "threshold"

    third = json.loads(lines[2])
    assert third["level"] == "ERROR"


def test_run_logger_human_log_also_written(tmp_path: Path) -> None:
    rl = RunLogger("test-run-456", runs_root=tmp_path)
    rl.info("Hello world", k=1)
    text_path = tmp_path / "test-run-456" / "run.log"
    assert text_path.exists()
    contents = text_path.read_text()
    assert "Hello world" in contents
