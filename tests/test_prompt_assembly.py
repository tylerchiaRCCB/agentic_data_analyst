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


def test_canonical_skills_load_per_agent() -> None:
    """Each agent's canonical skill set (per DEFAULT_SKILLS_BY_AGENT) is loaded
    automatically. The Framer does not choose skills — the orchestrator owns
    that decision to eliminate skill-name hallucination at the entry point."""
    result = assemble_prompt(agent_name="findings-validator")
    paths = "\n".join(result.sections_loaded)
    # Findings Validator's canonical skill set per DEFAULT_SKILLS_BY_AGENT:
    assert "validation/statistical-revalidation.md" in paths
    assert "validation/guardrail-pairing-check.md" in paths
    assert "analytical/simpsons-paradox-check.md" in paths
    assert "analytical/hypothesis-testing.md" in paths


def test_framer_specified_skills_are_ignored() -> None:
    """The orchestrator no longer trusts the Question Framer to pick skills.
    Whatever the Framer emits in its `skills` field, the runtime loads the
    canonical set per DEFAULT_SKILLS_BY_AGENT.

    This is the structural defense against hallucination at the entry point of
    the framework. The Framer's job is sequencing agents; methodology is
    agent-owned."""
    # Even if the Framer requests garbage skills, the canonical set still loads
    result = assemble_prompt(
        agent_name="data-profiler",
        skills=["nonexistent-skill-xyz", "another-fake-skill"],
    )
    # Framer-specified skills don't appear in loaded paths
    paths = "\n".join(result.sections_loaded)
    assert "nonexistent-skill-xyz" not in paths
    assert "another-fake-skill" not in paths
    # Canonical data-profiler skills DO load (outlier-typology, cpg-derived-metrics)
    assert "outlier-typology.md" in paths
    assert "cpg-derived-metrics.md" in paths
    # missing_skills is empty — canonical skills were found; ignored hallucinations don't count
    assert result.missing_skills == []


def test_every_canonical_agent_has_skill_mapping() -> None:
    """DEFAULT_SKILLS_BY_AGENT must have an entry for every canonical agent.
    Catches the regression where a new agent is added but its skill set is
    forgotten."""
    from src.orchestrator.prompt_assembler import DEFAULT_SKILLS_BY_AGENT
    from src.orchestrator.schemas import PAYLOAD_BY_AGENT
    for agent in PAYLOAD_BY_AGENT:
        assert agent in DEFAULT_SKILLS_BY_AGENT, (
            f"Agent {agent!r} has a payload schema but no entry in "
            f"DEFAULT_SKILLS_BY_AGENT — its prompt won't load any on-demand skills."
        )


def test_canonical_skills_all_resolve() -> None:
    """Every skill named in DEFAULT_SKILLS_BY_AGENT must actually exist in the
    skills/ folder. If this fails, an agent's canonical skill set references a
    file that's missing — the hallucination problem the mapping was designed
    to prevent would re-appear via the mapping itself."""
    from src.orchestrator.prompt_assembler import DEFAULT_SKILLS_BY_AGENT
    for agent, skills in DEFAULT_SKILLS_BY_AGENT.items():
        result = assemble_prompt(agent_name=agent)
        assert result.missing_skills == [], (
            f"Agent {agent!r} has canonical skills that don't exist in the repo: "
            f"{result.missing_skills}. Check DEFAULT_SKILLS_BY_AGENT vs. skills/ folder contents."
        )


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


def test_prompt_sha256_pinned_in_assembled_prompt() -> None:
    """Each AssembledPrompt carries SHAs that pin its exact byte content for
    artifact reproducibility. Hashes are 64-char hex strings."""
    r = assemble_prompt(agent_name="data-profiler")
    assert len(r.prompt_sha256) == 64
    assert len(r.universal_skills_sha256) == 64
    assert len(r.agent_block_sha256) == 64
    # Re-assembling should produce identical hashes (deterministic).
    r2 = assemble_prompt(agent_name="data-profiler")
    assert r.prompt_sha256 == r2.prompt_sha256
    assert r.universal_skills_sha256 == r2.universal_skills_sha256
    assert r.agent_block_sha256 == r2.agent_block_sha256


def test_prompt_sha256_differs_across_agents() -> None:
    """Different agents → different prompt hashes (different agent block).
    Universal-skills hash is the same — that's the whole point of caching it."""
    a = assemble_prompt(agent_name="data-profiler")
    b = assemble_prompt(agent_name="findings-validator", skills=["statistical-revalidation"])
    assert a.universal_skills_sha256 == b.universal_skills_sha256
    assert a.agent_block_sha256 != b.agent_block_sha256
    assert a.prompt_sha256 != b.prompt_sha256
