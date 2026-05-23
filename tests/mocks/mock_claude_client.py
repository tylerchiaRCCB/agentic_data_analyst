"""MockClaudeClient — drop-in replacement for ClaudeClient in tests.

Returns scripted responses keyed by agent (detected from the AGENT DEFINITION
marker in the system block). Each agent has a queue of responses; each `.call()`
pops the next one. Responses can be:

  - dict with "text" / "usage" fields → returned as a ClaudeResponse
  - an Exception subclass instance → raised when consumed
  - a string → wrapped as text response with zero token usage

This enables unit-testing the orchestrator's retry / skip-and-flag / hard-fail
paths without any real API cost. Standard practice in production AI systems.

Usage:

    mock = MockClaudeClient(
        responses_by_agent={
            "question-framer": [_fixture_text("question-framer-minimal.json")],
            "data-retrieval-agent": [_fixture_text("data-retrieval-minimal.json")],
            ...
        }
    )

    # Pass to PipelineExecutor in place of the real client.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from src.api.claude_client import ClaudeResponse

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"

# Match the agent name in the assembled prompt's "AGENT DEFINITION — <name>" line.
_AGENT_LINE_RE = re.compile(r"AGENT DEFINITION\s*[—\-]\s*([a-z\-]+)")


class MockClaudeClient:
    """Drop-in replacement for ClaudeClient with scripted per-agent responses.

    The mock detects which agent is being called by scanning the system blocks
    for the assembled-prompt marker `# AGENT DEFINITION — <agent-name>`. It then
    pops and returns the next response from that agent's queue.
    """

    def __init__(self, responses_by_agent: dict[str, list[Any]] | None = None) -> None:
        self._queues: dict[str, deque[Any]] = defaultdict(deque)
        if responses_by_agent:
            for agent, responses in responses_by_agent.items():
                self._queues[agent].extend(responses)
        self.calls: list[dict[str, Any]] = []  # for test assertions

    def upload_file(self, path: Path) -> str:  # noqa: ARG002 — interface compatibility
        return "mock-file-id"

    def queue(self, agent: str, response: Any) -> None:
        """Append a response to an agent's queue (for tests that need to mid-stream add)."""
        self._queues[agent].append(response)

    def call(
        self,
        *,
        model: str,
        system: str | list[dict[str, Any]],
        messages: list[dict[str, Any]],
        max_tokens: int = 8192,  # noqa: ARG002 — interface compatibility
        enable_code_execution: bool = True,  # noqa: ARG002
        enable_files_api: bool = True,  # noqa: ARG002
        extra_tools: list[dict[str, Any]] | None = None,  # noqa: ARG002
        output_tool: dict[str, Any] | None = None,  # noqa: ARG002
        timeout_seconds: float = 900.0,  # noqa: ARG002
    ) -> ClaudeResponse:
        agent = self._detect_agent(system)
        if not agent:
            raise RuntimeError("MockClaudeClient: could not detect agent from system prompt")
        self.calls.append({"agent": agent, "model": model, "messages_count": len(messages)})

        queue = self._queues.get(agent)
        if not queue:
            raise RuntimeError(
                f"MockClaudeClient: no scripted responses for agent {agent}. "
                f"Available: {sorted(self._queues.keys())}"
            )

        nxt = queue.popleft()

        # Exception in the queue → raise it (simulating API errors)
        if isinstance(nxt, BaseException):
            raise nxt

        # String → minimal text response
        if isinstance(nxt, str):
            return _make_response(text=nxt)

        # Dict with text/usage → richer response
        if isinstance(nxt, dict):
            return _make_response(
                text=nxt.get("text", ""),
                input_tokens=nxt.get("input_tokens", 100),
                output_tokens=nxt.get("output_tokens", 50),
                cache_read_tokens=nxt.get("cache_read_tokens", 0),
                cache_write_tokens=nxt.get("cache_write_tokens", 0),
            )

        raise TypeError(f"MockClaudeClient: unsupported response type {type(nxt).__name__}")

    @staticmethod
    def _detect_agent(system: str | list[dict[str, Any]]) -> str | None:
        if isinstance(system, str):
            text = system
        else:
            text = " ".join(block.get("text", "") for block in system if isinstance(block, dict))
        m = _AGENT_LINE_RE.search(text)
        return m.group(1) if m else None


def _make_response(
    *,
    text: str,
    input_tokens: int = 100,
    output_tokens: int = 50,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> ClaudeResponse:
    return ClaudeResponse(
        text=text,
        stop_reason="end_turn",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
        raw=None,
    )


def fixture_payload(name: str) -> dict[str, Any]:
    """Load a JSON fixture from tests/fixtures/."""
    path = FIXTURES_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Missing fixture: {path}")
    return json.loads(path.read_text())


def fixture_text(name: str) -> str:
    """Load a JSON fixture and serialize back to a string (for the LLM response text)."""
    return json.dumps(fixture_payload(name))
