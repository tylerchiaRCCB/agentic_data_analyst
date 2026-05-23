"""Provider-agnostic LLM client abstraction.

The framework needs to be able to test Anthropic vs. OpenAI vs. Google models
(via Azure AI Foundry or direct provider APIs) without rewriting agent logic.
This module defines the contract every LLM client must satisfy, plus a
factory that dispatches to the right concrete implementation based on the
model identifier.

## Provider-specific tradeoffs (read before swapping in production)

| Provider  | Code execution | Prompt caching | Files API | Notes                                          |
|-----------|----------------|----------------|-----------|------------------------------------------------|
| Anthropic | ✅ native      | ✅ 90% cache-read discount | ✅ | Native SDK. PRIMARY for production economics. |
| OpenAI    | ✅ via Code Interpreter (Assistants/Responses API) | ❌ no | ✅ different shape | LiteLLM. Different code-exec semantics.       |
| Google    | ✅ via tool spec | ⚠️ implicit only | ⚠️ via Vertex AI | LiteLLM. Less mature tool-use support.        |

**The cache-read discount is significant.** Our universal-skills block is ~50K
tokens, loaded across all 10-11 agent calls per run. On Anthropic, only the
first call pays full price; subsequent calls pay ~10%. On OpenAI/Gemini, every
call pays full price. A run that costs $10-15 on Anthropic likely costs $50-100
on OpenAI for the same workload. Provider-agnostic in the framework does NOT
mean provider-agnostic in production economics.

The intended deployment: Anthropic primary, alternatives for A/B testing.

## Model identifier convention

Use prefixed model IDs to disambiguate provider per call:

  - "anthropic/claude-opus-4-7"  → AnthropicLLMClient via native SDK
  - "anthropic/claude-sonnet-4-6"
  - "openai/gpt-5"               → LiteLLMClient
  - "openai/gpt-4.1"
  - "google/gemini-3-pro"        → LiteLLMClient
  - "azure/<deployment-name>"    → LiteLLMClient w/ AZURE_API_KEY env
  - bare "claude-opus-4-7"       → treated as "anthropic/claude-opus-4-7" (backward compat)

The factory `get_llm_client(model_id)` returns the right concrete client.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Normalized response across LLM providers.

    Mirrors the existing ClaudeResponse shape so the orchestrator does not
    need to know which provider produced the response.

    `tool_output` is the structured artifact when the call was made with an
    `output_tool` and the model emitted matching tool_use content. The
    pipeline executor prefers this over text-parsing.
    """

    text: str
    stop_reason: str | None
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    raw: Any  # provider-specific raw response
    tool_output: dict[str, Any] | None = None
    provider: str = ""  # "anthropic" | "openai" | "google" | "azure"


class LLMClient(Protocol):
    """Protocol every LLM client must satisfy."""

    @property
    def provider(self) -> str:
        """Provider identifier — 'anthropic', 'openai', 'google', etc."""
        ...

    @property
    def supports_code_execution(self) -> bool:
        """Whether this provider supports native code-execution tool calls.

        Code execution is essential to the framework's compute-before-reasoning
        rule. Providers without code execution cannot run analytical agents
        reliably (the LLM would be reasoning over data rather than computing on
        it). The pipeline executor checks this capability before launching
        analytical stages and degrades / refuses gracefully when missing.
        """
        ...

    @property
    def supports_prompt_caching(self) -> bool:
        """Whether this provider supports explicit prompt caching."""
        ...

    def upload_file(self, path: Path) -> str:
        """Upload a file for the provider's code-execution sandbox.

        Returns a provider-specific file_id used in subsequent calls. Raises
        NotImplementedError if the provider does not support files.
        """
        ...

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
    ) -> LLMResponse:
        """Issue a single LLM call. See ClaudeClient.call for the canonical
        semantics; non-Anthropic implementations adapt their native APIs to
        match.
        """
        ...


# ---------------------------------------------------------------------------
# Model identifier parsing + dispatch factory
# ---------------------------------------------------------------------------


def parse_model_id(model_id: str) -> tuple[str, str]:
    """Parse a model identifier into (provider, model_name).

    >>> parse_model_id("anthropic/claude-opus-4-7")
    ('anthropic', 'claude-opus-4-7')
    >>> parse_model_id("openai/gpt-5")
    ('openai', 'gpt-5')
    >>> parse_model_id("claude-opus-4-7")  # bare → assume anthropic
    ('anthropic', 'claude-opus-4-7')
    """
    if "/" in model_id:
        provider, model = model_id.split("/", 1)
        return provider.lower(), model
    # Backward compat: bare claude-* / claude_* names default to anthropic
    return "anthropic", model_id


def get_llm_client(model_id: str, *, api_key: str | None = None) -> LLMClient:
    """Factory — return the right concrete LLMClient for the given model id.

    Anthropic models go through the native SDK to preserve prompt caching +
    code execution + Files API. All other providers route through LiteLLM.
    """
    provider, _ = parse_model_id(model_id)

    if provider == "anthropic":
        from src.api.claude_client import ClaudeClient
        return ClaudeClient(api_key=api_key)

    if provider in {"openai", "google", "gemini", "azure", "vertex_ai", "bedrock"}:
        from src.api.litellm_client import LiteLLMClient
        return LiteLLMClient(api_key=api_key)

    raise ValueError(
        f"Unknown LLM provider: {provider!r} (from model_id={model_id!r}). "
        f"Supported: anthropic, openai, google, gemini, azure, vertex_ai, bedrock."
    )


def resolve_model_for_call(model_id: str) -> str:
    """Strip the provider prefix to get the bare model name the provider's API expects.

    Anthropic: "anthropic/claude-opus-4-7" → "claude-opus-4-7"
    LiteLLM accepts the prefixed form natively — pass-through is fine.
    """
    provider, model = parse_model_id(model_id)
    if provider == "anthropic":
        return model  # native SDK wants bare model name
    # LiteLLM accepts both bare and prefixed; prefixed is unambiguous so we keep it
    return f"{provider}/{model}"
