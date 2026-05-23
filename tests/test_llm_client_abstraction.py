"""Tests for the provider-agnostic LLMClient abstraction.

The framework must support testing alternative providers (OpenAI, Gemini) so
the team can A/B test which gives best results. Anthropic remains primary for
production economics (cache savings), but the abstraction makes swapping a
config change rather than a code change.
"""

from __future__ import annotations

import pytest

from src.api.claude_client import ClaudeClient
from src.api.llm_client import (
    LLMResponse,
    get_llm_client,
    parse_model_id,
    resolve_model_for_call,
)


# ---------------------------------------------------------------------------
# parse_model_id — separating provider from model name
# ---------------------------------------------------------------------------


def test_parse_model_id_anthropic_prefixed() -> None:
    assert parse_model_id("anthropic/claude-opus-4-7") == ("anthropic", "claude-opus-4-7")


def test_parse_model_id_openai_prefixed() -> None:
    assert parse_model_id("openai/gpt-5") == ("openai", "gpt-5")


def test_parse_model_id_google_prefixed() -> None:
    assert parse_model_id("google/gemini-3-pro") == ("google", "gemini-3-pro")


def test_parse_model_id_bare_name_defaults_to_anthropic() -> None:
    """Backward compat: bare model names (no slash) default to Anthropic so
    existing config files keep working."""
    assert parse_model_id("claude-opus-4-7") == ("anthropic", "claude-opus-4-7")
    assert parse_model_id("claude-sonnet-4-6") == ("anthropic", "claude-sonnet-4-6")


def test_parse_model_id_handles_uppercase_provider() -> None:
    assert parse_model_id("Anthropic/claude-opus-4-7") == ("anthropic", "claude-opus-4-7")
    assert parse_model_id("OpenAI/gpt-5") == ("openai", "gpt-5")


# ---------------------------------------------------------------------------
# resolve_model_for_call — strip prefix for native Anthropic; keep for LiteLLM
# ---------------------------------------------------------------------------


def test_resolve_model_for_call_anthropic_strips_prefix() -> None:
    assert resolve_model_for_call("anthropic/claude-opus-4-7") == "claude-opus-4-7"
    assert resolve_model_for_call("claude-opus-4-7") == "claude-opus-4-7"


def test_resolve_model_for_call_litellm_keeps_prefix() -> None:
    """LiteLLM expects the `provider/model` prefixed form."""
    assert resolve_model_for_call("openai/gpt-5") == "openai/gpt-5"
    assert resolve_model_for_call("google/gemini-3-pro") == "google/gemini-3-pro"


# ---------------------------------------------------------------------------
# Factory dispatch — get_llm_client returns the right concrete client
# ---------------------------------------------------------------------------


def test_factory_dispatches_anthropic_to_claude_client() -> None:
    """Anthropic models route to the native ClaudeClient (preserves caching)."""
    client = get_llm_client("anthropic/claude-opus-4-7")
    assert isinstance(client, ClaudeClient)
    assert client.provider == "anthropic"


def test_factory_dispatches_bare_anthropic_to_claude_client() -> None:
    """Backward compat: bare model name also dispatches to ClaudeClient."""
    client = get_llm_client("claude-opus-4-7")
    assert isinstance(client, ClaudeClient)


def test_factory_dispatches_openai_to_litellm_client() -> None:
    """OpenAI models route to LiteLLMClient. Construction does not require keys."""
    from src.api.litellm_client import LiteLLMClient
    client = get_llm_client("openai/gpt-5")
    assert isinstance(client, LiteLLMClient)


def test_factory_dispatches_google_to_litellm_client() -> None:
    from src.api.litellm_client import LiteLLMClient
    client = get_llm_client("google/gemini-3-pro")
    assert isinstance(client, LiteLLMClient)


def test_factory_raises_on_unknown_provider() -> None:
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        get_llm_client("acme/whatever-model")


# ---------------------------------------------------------------------------
# Capability flags — what each client advertises
# ---------------------------------------------------------------------------


def test_anthropic_client_advertises_full_capability_set() -> None:
    client = ClaudeClient()
    assert client.provider == "anthropic"
    assert client.supports_code_execution is True
    assert client.supports_prompt_caching is True


def test_litellm_client_advertises_limited_capability_set() -> None:
    """LiteLLM client supports neither prompt caching nor (in our wiring)
    code execution. This is correctly reflected in its capability flags so
    the executor can refuse / degrade gracefully when needed."""
    from src.api.litellm_client import LiteLLMClient
    client = LiteLLMClient()
    assert client.supports_code_execution is False  # conservative; per-call check enforces
    assert client.supports_prompt_caching is False


# ---------------------------------------------------------------------------
# Executor's per-stage client dispatch
# ---------------------------------------------------------------------------


def test_executor_client_for_model_returns_injected_anthropic_client_for_bare_models() -> None:
    """The executor's _client_for_model returns the injected primary client
    when the model is Anthropic (bare or prefixed). This preserves the
    existing single-client path for the default deployment."""
    from src.orchestrator.budget_tracker import BudgetTracker
    from src.orchestrator.lineage_tracker import LineageTracker
    from src.orchestrator.pipeline_executor import PipelineConfig, PipelineExecutor
    from src.observability.run_logger import RunLogger
    from src.observability.tracer import Tracer

    primary = ClaudeClient()
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        from pathlib import Path
        executor = PipelineExecutor(
            client=primary,
            config=PipelineConfig(model_per_agent={}),
            run_logger=RunLogger("t", runs_root=Path(tmp)),
            tracer=Tracer(run_id="t"),
            budget=BudgetTracker(budget_tokens=1, cost_per_million={}),
            lineage=LineageTracker(run_id="t"),
        )
        assert executor._client_for_model("claude-opus-4-7") is primary
        assert executor._client_for_model("anthropic/claude-opus-4-7") is primary


def test_executor_client_for_model_dispatches_non_anthropic_via_factory() -> None:
    """A non-Anthropic model gets routed via the factory; the result is
    cached so we don't reconstruct per call."""
    from src.api.litellm_client import LiteLLMClient
    from src.orchestrator.budget_tracker import BudgetTracker
    from src.orchestrator.lineage_tracker import LineageTracker
    from src.orchestrator.pipeline_executor import PipelineConfig, PipelineExecutor
    from src.observability.run_logger import RunLogger
    from src.observability.tracer import Tracer

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        from pathlib import Path
        executor = PipelineExecutor(
            client=ClaudeClient(),
            config=PipelineConfig(model_per_agent={}),
            run_logger=RunLogger("t", runs_root=Path(tmp)),
            tracer=Tracer(run_id="t"),
            budget=BudgetTracker(budget_tokens=1, cost_per_million={}),
            lineage=LineageTracker(run_id="t"),
        )
        c1 = executor._client_for_model("openai/gpt-5")
        c2 = executor._client_for_model("openai/gpt-5")
        assert isinstance(c1, LiteLLMClient)
        assert c1 is c2  # cached
