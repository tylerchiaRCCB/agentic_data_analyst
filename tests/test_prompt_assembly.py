"""Tests for the prompt assembler.

Verifies:
- Universal skills are always loaded (all 8).
- Agent definition is included.
- On-demand skills resolve across analytical/validation/output/domain-specific folders.
- Missing skills raise FileNotFoundError.
- Missing domain context is permissive — returns missing_domain_context=True without raising.
- Section ordering matches pipeline-definitions.md §4: universal → agent → skills → context.
"""

from __future__ import annotations

import pytest

from src.orchestrator.prompt_assembler import assemble_prompt


def test_universal_skills_always_loaded() -> None:
    result = assemble_prompt(agent_name="data-profiler")
    # All 8 universal skills should appear in the loaded section list
    universal_loaded = [s for s in result.sections_loaded if s.startswith("universal/")]
    assert len(universal_loaded) >= 8, f"Expected ≥8 universal skills, got {universal_loaded}"
    # The universal block should appear before the agent definition
    sp = result.system_prompt
    assert sp.index("UNIVERSAL SKILLS") < sp.index("AGENT DEFINITION")


def test_agent_definition_loaded() -> None:
    result = assemble_prompt(agent_name="data-profiler")
    assert "agents/data-profiler.md" in result.sections_loaded
    assert "data-profiler" in result.system_prompt


def test_on_demand_skills_resolve() -> None:
    skills = ["correlation-analysis", "statistical-revalidation", "proactive-action-card"]
    result = assemble_prompt(agent_name="findings-validator", skills=skills)
    # Each skill should appear in sections_loaded under its category folder
    paths = "\n".join(result.sections_loaded)
    assert "analytical/correlation-analysis.md" in paths
    assert "validation/statistical-revalidation.md" in paths
    assert "output/proactive-action-card.md" in paths


def test_missing_skill_raises() -> None:
    with pytest.raises(FileNotFoundError):
        assemble_prompt(agent_name="data-profiler", skills=["nonexistent-skill-xyz"])


def test_missing_domain_context_is_permissive() -> None:
    result = assemble_prompt(agent_name="data-profiler", domain="nonexistent-domain-xyz")
    assert result.missing_domain_context is True
    assert result.domain_attempted == "nonexistent-domain-xyz"
    # System prompt should still be valid — universal + agent at minimum
    assert "UNIVERSAL SKILLS" in result.system_prompt
    assert "AGENT DEFINITION" in result.system_prompt


def test_no_domain_argument_is_not_missing() -> None:
    result = assemble_prompt(agent_name="data-profiler")
    # No domain attempted ≠ domain attempted and missing
    assert result.missing_domain_context is False
    assert result.domain_attempted is None


def test_section_order() -> None:
    result = assemble_prompt(
        agent_name="findings-validator",
        skills=["statistical-revalidation"],
    )
    sp = result.system_prompt
    universal_pos = sp.index("UNIVERSAL SKILLS")
    agent_pos = sp.index("AGENT DEFINITION")
    skills_pos = sp.index("ON-DEMAND SKILLS")
    assert universal_pos < agent_pos < skills_pos
