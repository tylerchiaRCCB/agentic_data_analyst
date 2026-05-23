"""Anthropic API client wrapper.

Thin layer over the official `anthropic` SDK. Handles:
- Model selection per agent (per spec Part 12)
- Code-execution tool enablement (the sandbox where computed work happens)
- Files API for dataset uploads (so the dataset is referenced by file_id, not re-uploaded each call)
- Retry logic for transient errors per failure-recovery.md §4.2
- Token usage accounting (returned to the orchestrator for budget telemetry)

This module is intentionally narrow. It does not assemble prompts (prompt_assembler.py does)
or parse responses into artifacts (pipeline_executor.py does).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anthropic
from anthropic import APIConnectionError, APIError, APIStatusError, APITimeoutError, RateLimitError

# OverloadedError isn't always re-exported at the top level depending on SDK version.
# Resolve it dynamically so the import doesn't break older/newer SDK versions.
try:
    from anthropic import OverloadedError  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover
    OverloadedError = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Beta header strings for the SDK's `betas=` parameter.
# Both must be passed together when running code execution against an uploaded file.
BETA_FILES_API = "files-api-2025-04-14"
BETA_CODE_EXECUTION = "code-execution-2025-05-22"

# Tool definition for Anthropic-hosted code execution. The version constant
# may need updating as Anthropic ships new tool revisions.
CODE_EXECUTION_TOOL: dict[str, str] = {
    "type": "code_execution_20250522",
    "name": "code_execution",
}


@dataclass
class ClaudeResponse:
    """Container for a Claude API response, with token usage and the raw response.

    `tool_output` is set when the call was made with an `output_tool` and Claude
    emitted a tool_use block matching it — that's the structured artifact, used
    in preference to text parsing. See pipeline_executor's _call_and_validate.
    """

    text: str
    stop_reason: str | None
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    raw: Any  # the original SDK response, for inspection / tool-use extraction
    tool_output: dict[str, Any] | None = None


class ClaudeClient:
    """Wrapper around `anthropic.Anthropic`.

    Initialization reads `ANTHROPIC_API_KEY` from the environment by default.
    For production, this will be swapped for Azure AI Foundry per
    `orchestration/pipeline-definitions.md` §10's data-flow section.
    """

    def __init__(self, api_key: str | None = None, max_retries: int = 5) -> None:
        # The SDK retries internally on transient errors; we add an additional
        # logical-retry layer at the orchestrator level per failure-recovery.md §2.
        self._client = anthropic.Anthropic(api_key=api_key, max_retries=0)
        self._max_retries = max_retries

    # ---------- Files API: upload dataset once per run ----------

    def upload_file(self, path: Path) -> str:
        """Upload a file to Anthropic's Files API, return the file_id.

        Used at run start by pipeline_executor.py — every agent's code execution
        references the file_id rather than re-uploading.

        Requires the `files-api-2025-04-14` beta. The SDK passes that via the
        `betas=` parameter (not as a query string).
        """
        mime = "text/csv" if path.suffix.lower() == ".csv" else "application/vnd.ms-excel"
        with path.open("rb") as f:
            result = self._client.beta.files.upload(
                file=(path.name, f, mime),
                betas=[BETA_FILES_API],
            )
        return result.id

    # ---------- Main call path ----------

    def call(
        self,
        *,
        model: str,
        system: str | list[dict[str, Any]],
        messages: list[dict[str, Any]],
        max_tokens: int = 8192,
        enable_code_execution: bool = True,
        enable_files_api: bool = True,
        extra_tools: list[dict[str, Any]] | None = None,
        output_tool: dict[str, Any] | None = None,
        timeout_seconds: float = 900.0,
    ) -> ClaudeResponse:
        """Call Claude with the given system prompt and messages.

        `system` may be a plain string OR a list of structured content blocks. The list
        form enables prompt caching via `{"type": "text", "text": "...",
        "cache_control": {"type": "ephemeral"}}` blocks — see prompt_assembler.py.

        When `enable_files_api=True`, the call passes through `container_upload` blocks
        in the user message so code execution can read uploaded files via
        $INPUT_DIR/<filename> in the sandbox.

        Handles rate-limit retries with exponential backoff per failure-recovery.md §4.2.
        Other errors propagate; the caller decides how to handle.
        """
        tools: list[dict[str, Any]] = []
        if enable_code_execution:
            tools.append(CODE_EXECUTION_TOOL)
        if extra_tools:
            tools.extend(extra_tools)
        if output_tool is not None:
            # The structured-output tool. We do NOT force tool_choice — Claude
            # is allowed to use code_execution mid-stream and the output_tool
            # at the end. The strong prompt-level instruction is that the final
            # emit_*_artifact call is required. Forcing tool_choice would
            # prevent code_execution; that breaks the whole compute-before-
            # reasoning discipline.
            tools.append(output_tool)

        betas: list[str] = []
        if enable_code_execution:
            betas.append(BETA_CODE_EXECUTION)
        if enable_files_api:
            betas.append(BETA_FILES_API)

        attempt = 0
        delay = 2.0
        while True:
            attempt += 1
            try:
                response = self._client.beta.messages.create(
                    model=model,
                    system=system,
                    messages=messages,
                    max_tokens=max_tokens,
                    tools=tools if tools else anthropic.NOT_GIVEN,
                    betas=betas if betas else anthropic.NOT_GIVEN,
                    timeout=timeout_seconds,
                )
                return self._wrap_response(response)
            except RateLimitError:
                if attempt >= self._max_retries:
                    raise
                logger.warning(
                    "Rate limited on attempt %d/%d; sleeping %.1fs",
                    attempt,
                    self._max_retries,
                    delay,
                )
                time.sleep(delay)
                delay = min(delay * 2, 30.0)
            except Exception as e:  # broaden catch to cover transient errors
                # Transient categories — retry up to 5 attempts with exponential backoff:
                #  - OverloadedError (Anthropic infra overload)
                #  - APIStatusError with 5xx status code
                #  - APIConnectionError / APITimeoutError (network blips, dropped SSL)
                is_overloaded = OverloadedError is not None and isinstance(e, OverloadedError)
                is_5xx = isinstance(e, APIStatusError) and 500 <= e.status_code < 600
                is_conn = isinstance(e, (APIConnectionError, APITimeoutError))
                if (is_overloaded or is_5xx or is_conn) and attempt < 5:
                    if is_overloaded:
                        label = "OverloadedError"
                    elif is_conn:
                        label = f"connection error ({type(e).__name__})"
                    else:
                        label = f"transient {getattr(e, 'status_code', '5xx')}"
                    logger.warning(
                        "%s on attempt %d/5; sleeping %.1fs",
                        label,
                        attempt,
                        delay,
                    )
                    time.sleep(delay)
                    delay = min(delay * 2, 30.0)
                    continue
                # Anything else: not retryable here, propagate
                raise

    # ---------- Response unpacking ----------

    @staticmethod
    def _wrap_response(response: Any) -> ClaudeResponse:
        # Extract the final assistant text. We concatenate text blocks; tool-use
        # blocks (code execution requests AND structured-output emissions) are
        # surfaced separately. If a tool_use block matches the convention
        # `emit_*_artifact`, treat its input dict as the structured output.
        text_parts: list[str] = []
        tool_output: dict[str, Any] | None = None
        for block in response.content:
            btype = getattr(block, "type", None)
            if btype == "text":
                text_parts.append(block.text)
            elif btype == "tool_use":
                name = getattr(block, "name", "") or ""
                # Our convention: emit_<agent_underscored>_artifact
                if name.startswith("emit_") and name.endswith("_artifact"):
                    tool_input = getattr(block, "input", None)
                    if isinstance(tool_input, dict):
                        tool_output = tool_input

        usage = response.usage
        return ClaudeResponse(
            text="\n".join(text_parts),
            stop_reason=response.stop_reason,
            input_tokens=getattr(usage, "input_tokens", 0),
            output_tokens=getattr(usage, "output_tokens", 0),
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
            raw=response,
            tool_output=tool_output,
        )
