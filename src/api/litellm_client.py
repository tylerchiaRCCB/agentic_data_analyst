"""LiteLLM-backed LLMClient for non-Anthropic providers.

Uses `litellm.completion()` to issue calls to OpenAI, Google Gemini, Azure
OpenAI, AWS Bedrock, etc., normalizing the response into our `LLMResponse`
shape. Routing is by model identifier — `openai/gpt-5`, `google/gemini-3-pro`,
`azure/<deployment-name>`, etc. LiteLLM accepts the provider-prefixed form
natively.

## What this client does NOT do (vs. ClaudeClient)

1. **Native code execution.** Anthropic's `code_execution` tool is native. For
   other providers, code execution requires the provider-specific equivalent
   (OpenAI Code Interpreter via the Responses API; Google's tool-spec code
   execution). LiteLLM has partial support; this client raises a clear error
   when `enable_code_execution=True` for providers without it.

   **Implication for the framework:** non-Anthropic providers cannot run
   analytical agents that depend on code execution (essentially all of them
   except the Communication Agent). For A/B testing rigor, this is a real
   limitation. Plan: use this client for testing the *Communication Agent's
   render quality* across providers, or for the future analytical agents that
   can reason without code (e.g., the Synthesizer Agent already does this).

2. **Prompt caching.** No provider other than Anthropic offers explicit
   prompt-caching discount. Calls go through at full token-rate pricing.

3. **Files API.** OpenAI's file upload uses a different mechanism; not wired
   up here yet. Pass dataset content inline if needed.

The intent of this client is to *test* provider parity for the parts of the
framework that don't require code execution. For production, Anthropic remains
primary.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from src.api.llm_client import LLMResponse, parse_model_id

logger = logging.getLogger(__name__)


class LiteLLMNotInstalled(RuntimeError):
    """Raised when litellm is not installed but a non-Anthropic call is attempted."""


class CodeExecutionNotSupported(RuntimeError):
    """Raised when enable_code_execution=True for a provider that doesn't support it."""


class LiteLLMClient:
    """LLMClient implementation for non-Anthropic providers via LiteLLM."""

    # Code execution is provider-specific. The set below is the providers where
    # LiteLLM has decent code-execution support. Update as LiteLLM matures.
    _CODE_EXEC_PROVIDERS: set[str] = {"openai", "azure"}  # OpenAI via Responses API

    @property
    def provider(self) -> str:
        # Indeterminate until we see the model id at call time. Return generic.
        return "litellm"

    @property
    def supports_code_execution(self) -> bool:
        # Per-call check via _check_code_execution; this property is conservative.
        return False

    @property
    def supports_prompt_caching(self) -> bool:
        return False

    def __init__(self, api_key: str | None = None) -> None:  # noqa: ARG002 — interface compat
        # LiteLLM reads provider API keys from env vars by convention:
        #   OPENAI_API_KEY, GEMINI_API_KEY / GOOGLE_API_KEY, AZURE_API_KEY +
        #   AZURE_API_BASE + AZURE_API_VERSION, etc.
        # If a specific key is passed in, the caller is responsible for setting
        # the right env var or override before invocation.
        try:
            import litellm  # noqa: F401
        except ImportError as e:
            raise LiteLLMNotInstalled(
                "litellm is not installed. Add it to dependencies or use the AnthropicClient path. "
                f"Original import error: {e}"
            ) from e

    def upload_file(self, path: Path) -> str:  # noqa: ARG002
        raise NotImplementedError(
            "File upload via LiteLLM is provider-specific and not yet wired. "
            "Use the Anthropic Files API path for code-execution data access."
        )

    def call(
        self,
        *,
        model: str,
        system: str | list[dict[str, Any]],
        messages: list[dict[str, Any]],
        max_tokens: int = 8192,
        enable_code_execution: bool = True,
        enable_files_api: bool = True,  # noqa: ARG002
        extra_tools: list[dict[str, Any]] | None = None,
        output_tool: dict[str, Any] | None = None,
        timeout_seconds: float = 900.0,
    ) -> LLMResponse:
        """Issue a call via LiteLLM, returning a normalized LLMResponse.

        Code execution is gated: if requested for a provider that doesn't
        support it, raises CodeExecutionNotSupported with a clear message.
        """
        import litellm

        provider, _ = parse_model_id(model)

        if enable_code_execution and provider not in self._CODE_EXEC_PROVIDERS:
            raise CodeExecutionNotSupported(
                f"Provider {provider!r} (model={model!r}) does not have wired code-execution support. "
                f"Code execution is supported on: {sorted(self._CODE_EXEC_PROVIDERS)}. "
                "Either disable code execution for this call (and accept degraded analytical "
                "capability) or use the Anthropic client."
            )

        # Translate the Anthropic-shaped system blocks into OpenAI-style messages.
        # LiteLLM accepts the OpenAI message convention; system content is a single
        # "system" role message at the top.
        if isinstance(system, list):
            system_text = "\n\n".join(
                block.get("text", "")
                for block in system
                if isinstance(block, dict) and block.get("type") == "text"
            )
        else:
            system_text = system

        # Reshape user messages: Anthropic's content-block format is mostly
        # compatible with LiteLLM, but some providers want plain strings.
        # Pass through; LiteLLM normalizes.
        openai_messages = [{"role": "system", "content": system_text}]
        openai_messages.extend(messages)

        # Build tools list. Output_tool gets reshaped to OpenAI function format.
        tools: list[dict[str, Any]] = []
        if output_tool is not None:
            tools.append({
                "type": "function",
                "function": {
                    "name": output_tool["name"],
                    "description": output_tool["description"],
                    "parameters": output_tool["input_schema"],
                },
            })
        if extra_tools:
            for t in extra_tools:
                # Best-effort reshape; caller is responsible if a different shape is needed
                if "name" in t and "input_schema" in t:
                    tools.append({
                        "type": "function",
                        "function": {
                            "name": t["name"],
                            "description": t.get("description", ""),
                            "parameters": t["input_schema"],
                        },
                    })
                else:
                    tools.append(t)

        logger.info("LiteLLM call: model=%s tools=%d", model, len(tools))
        response = litellm.completion(
            model=model,
            messages=openai_messages,
            max_tokens=max_tokens,
            tools=tools if tools else None,
            timeout=timeout_seconds,
        )

        return self._wrap_response(response, provider=provider)

    @staticmethod
    def _wrap_response(response: Any, *, provider: str) -> LLMResponse:
        """Normalize LiteLLM's OpenAI-shaped response into LLMResponse."""
        # LiteLLM returns OpenAI-style ChatCompletion. Choices[0].message has
        # content (text) and possibly tool_calls (structured emissions).
        choice = response.choices[0]
        msg = choice.message
        text = getattr(msg, "content", "") or ""

        tool_output: dict[str, Any] | None = None
        tool_calls = getattr(msg, "tool_calls", None) or []
        for tc in tool_calls:
            fn = getattr(tc, "function", None)
            if fn is None:
                continue
            name = getattr(fn, "name", "")
            args = getattr(fn, "arguments", None)
            if name and name.startswith("emit_") and name.endswith("_artifact"):
                if isinstance(args, str):
                    import json
                    try:
                        tool_output = json.loads(args)
                    except json.JSONDecodeError:
                        logger.warning("Could not parse tool call arguments as JSON: %s", args[:200])
                elif isinstance(args, dict):
                    tool_output = args
                break

        usage = getattr(response, "usage", None)
        return LLMResponse(
            text=text,
            stop_reason=getattr(choice, "finish_reason", None),
            input_tokens=getattr(usage, "prompt_tokens", 0) if usage else 0,
            output_tokens=getattr(usage, "completion_tokens", 0) if usage else 0,
            cache_read_tokens=0,  # not supported on these providers
            cache_write_tokens=0,
            raw=response,
            tool_output=tool_output,
            provider=provider,
        )
