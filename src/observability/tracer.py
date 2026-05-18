"""Span tracking for pipeline runs.

Per pipeline-definitions.md §9 and the spec's Part 6 observability requirements:
- Trace = full pipeline run from input to output.
- Span = each agent call, each skill load, each code execution, each memory operation.

MVP scope: in-memory spans, persisted to a `spans.jsonl` file per run. Production will
swap for OpenTelemetry.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class Span:
    """A single span in a pipeline trace."""

    span_id: str
    parent_span_id: str | None
    name: str
    started_at: datetime
    ended_at: datetime | None = None
    duration_ms: int | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["started_at"] = self.started_at.isoformat()
        d["ended_at"] = self.ended_at.isoformat() if self.ended_at else None
        return d


class Tracer:
    """Collects spans for a single pipeline run. Not thread-safe."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.spans: list[Span] = []
        self._stack: list[str] = []

    @contextmanager
    def span(self, name: str, **attributes: Any) -> Generator[Span, None, None]:
        span = Span(
            span_id=str(uuid.uuid4()),
            parent_span_id=self._stack[-1] if self._stack else None,
            name=name,
            started_at=datetime.now(tz=timezone.utc),
            attributes=dict(attributes),
        )
        self._stack.append(span.span_id)
        start = time.perf_counter()
        try:
            yield span
        except Exception as e:
            span.error = f"{type(e).__name__}: {e}"
            raise
        finally:
            span.ended_at = datetime.now(tz=timezone.utc)
            span.duration_ms = int((time.perf_counter() - start) * 1000)
            self.spans.append(span)
            self._stack.pop()

    def to_jsonl(self) -> str:
        """Serialize the trace as newline-delimited JSON for span log files."""
        import json

        return "\n".join(json.dumps(s.to_dict(), default=str) for s in self.spans)
