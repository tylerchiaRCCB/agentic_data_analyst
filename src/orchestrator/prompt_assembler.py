"""Loads markdown files into the system prompt for each agent call.

Assembly order per pipeline-definitions.md §4:
  1. Universal skills (all files in skills/universal/) — always loaded
  2. Agent definition (agents/<name>.md)
  3. Per-stage skills (skills/analytical/<x>.md, skills/validation/<x>.md, etc.)
  4. Domain context (context/domains/<domain>.md or context/examples/<domain>.md if available)

Output is a list of system blocks with prompt-caching breakpoints:
  - Block 1: Universal skills (cacheable; shared across ALL agent calls in a run)
  - Block 2: Agent definition + on-demand skills + domain context (cacheable; shared
    across retries of the same agent)

Anthropic prompt caching dramatically reduces both cost and per-call input tokens
toward TPM rate limits — universal skills (~50K tokens) get billed at 10% on the
9 cache hits per run.

Missing skill file → fail loud (raises FileNotFoundError).
Missing domain context → permissive: proceed with universal + analytical skills only and
return a high-severity caveat the caller must propagate to the run. See
failure-recovery.md §6a.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS_ROOT = REPO_ROOT / "skills"
AGENTS_ROOT = REPO_ROOT / "agents"
CONTEXT_DOMAINS = REPO_ROOT / "context" / "domains"
CONTEXT_EXAMPLES = REPO_ROOT / "context" / "examples"

# Where each per-stage skill can live. Order matters: first hit wins.
SKILL_LOOKUP_DIRS: list[Path] = [
    SKILLS_ROOT / "analytical",
    SKILLS_ROOT / "validation",
    SKILLS_ROOT / "output",
    SKILLS_ROOT / "domain-specific",
]

# Universal skills auto-load with every agent call (see _load_universal_skills).
# If an agent lists one of these in its per-stage `skills`, it's a no-op — already loaded.
# We filter them out silently rather than failing or double-loading.
UNIVERSAL_SKILL_NAMES: frozenset[str] = frozenset({
    "analysis-design-spec",
    "statistical-rigor",
    "data-quality-standards",
    "ethical-analysis",
    "triangulation",
    "close-the-loop",
    "tracking-gaps",
    "resistant-statistics",
    "structured-output-contract",
})


# Per-agent canonical skill set. The framework loads these for every call to
# the named agent, regardless of what the Question Framer specifies.
#
# Rationale: the Question Framer is an LLM and can hallucinate skill names
# (e.g., requesting `date-parsing-integer-yyyymmdd` when no such skill exists).
# For a discipline-first framework, having the entry-point stage make things
# up is exactly the wrong failure mode. The mapping here is authoritative —
# the orchestrator owns the skill set per agent, not the Framer.
#
# Each list is sourced from the corresponding `agents/<name>.md` "Skills loaded
# with this agent" section. Keep this mapping and those markdown files
# synchronized; the markdown is documentation, this is enforcement.
#
# Names omit the category prefix (analytical/, validation/, output/,
# domain-specific/) since _resolve_skill searches all four directories.
DEFAULT_SKILLS_BY_AGENT: dict[str, list[str]] = {
    "question-framer": [
        "hypothesis-generation-from-data",
    ],
    "data-retrieval-agent": [
        # Nothing beyond universals — the data-retrieval agent's job is governed
        # by its agent definition + universals (especially data-quality-standards).
    ],
    "data-profiler": [
        "outlier-typology",
        "cpg-derived-metrics",
    ],
    "relationship-analyzer": [
        "correlation-analysis",
        "group-comparison",
        "cross-tabulation",
        "hypothesis-testing",
        "effect-size-calculation",
        "confounding-analysis",
        "interaction-detection",
    ],
    "pattern-discoverer": [
        "clustering-algorithms",
        "outlier-typology",
        "hypothesis-generation-from-data",
    ],
    "time-series-analyzer": [
        "stl-decomposition",
        "change-point-detection",
        "cohort-analysis",
    ],
    "root-cause-investigator": [
        "hypothesis-testing",
        "effect-size-calculation",
        "simpsons-paradox-check",
        "confounding-analysis",
        "counterfactual-reasoning",
    ],
    "opportunity-identifier": [
        "benchmarking-methods",
        "performance-gap-analysis",
        "predictive-readiness-assessment",
        "counterfactual-reasoning",
        "guardrail-metric-pairing",
    ],
    "findings-validator": [
        "statistical-revalidation",
        "guardrail-pairing-check",
        "hypothesis-testing",
        "simpsons-paradox-check",
        "guardrail-metric-pairing",
    ],
    "communication-agent": [
        "proactive-action-card",
        "descriptive-summary-format",
        "insight-first-formatting",
        "confidence-language",
        "stakeholder-communication",
        "visualization-recommendations",
    ],
    "synthesizer-agent": [
        "cross-run-synthesis",
        "confounding-analysis",
        "counterfactual-reasoning",
        "confidence-language",
        "proactive-action-card",
        "descriptive-summary-format",
    ],
}


@dataclass
class AssembledPrompt:
    """The result of assembling all markdown into a system prompt.

    `system_prompt` is the concatenated string form (kept for display, dry-run reports,
    and token estimation). `system_blocks` is the structured form passed to the API
    with cache_control hints on the cacheable blocks.

    Hash fields (`universal_skills_sha256`, `agent_block_sha256`, `prompt_sha256`)
    pin the exact bytes of the prompt that produced an artifact. Stored in every
    Artifact envelope for reproducibility — if a skill changes after a run, the
    old artifact still records exactly which prompt-version it was generated from.
    """

    system_prompt: str
    system_blocks: list[dict[str, Any]]
    sections_loaded: list[str] = field(default_factory=list)
    missing_domain_context: bool = False
    domain_attempted: str | None = None
    universal_skills_sha256: str = ""
    agent_block_sha256: str = ""
    prompt_sha256: str = ""
    missing_skills: list[str] = field(default_factory=list)


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_universal_skills() -> tuple[str, list[str]]:
    universal_dir = SKILLS_ROOT / "universal"
    if not universal_dir.exists():
        raise FileNotFoundError(f"Missing universal skills directory: {universal_dir}")

    files = sorted(p for p in universal_dir.glob("*.md") if p.name != "README.md")
    parts: list[str] = ["# UNIVERSAL SKILLS (always loaded)\n"]
    loaded: list[str] = []
    for f in files:
        parts.append(f"\n\n---\n\n# {f.stem}\n\n{_read(f)}")
        loaded.append(f"universal/{f.name}")
    return "".join(parts), loaded


def _load_agent(agent_name: str) -> tuple[str, str]:
    path = AGENTS_ROOT / f"{agent_name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Missing agent definition: {path}")
    return _read(path), f"agents/{path.name}"


def _resolve_skill(skill_name: str) -> Path:
    """Find `<skill_name>.md` in any of the on-demand skill directories."""
    candidate = f"{skill_name}.md"
    for d in SKILL_LOOKUP_DIRS:
        path = d / candidate
        if path.exists():
            return path
    raise FileNotFoundError(
        f"Missing skill: {skill_name}.md (searched: "
        f"{', '.join(str(d.relative_to(REPO_ROOT)) for d in SKILL_LOOKUP_DIRS)})"
    )


def _load_skills(skill_names: list[str]) -> tuple[str, list[str], list[str]]:
    """Return (skills_block_text, loaded_paths, missing_skill_names).

    The Question Framer can invent skill names that don't exist in our repo
    (it doesn't have a registry of available skills). Rather than hard-fail
    the run, we skip missing skills with a logged warning. The caller
    surfaces them as a caveat. The agent loses a bit of context but
    proceeds — strictly better than aborting the whole pipeline.
    """
    import logging
    logger = logging.getLogger(__name__)

    # Drop any universal skills the agent listed by mistake — they're auto-loaded.
    on_demand = [n for n in skill_names if n not in UNIVERSAL_SKILL_NAMES]
    if not on_demand:
        return "", [], []
    parts: list[str] = ["\n\n---\n\n# ON-DEMAND SKILLS\n"]
    loaded: list[str] = []
    missing: list[str] = []
    for name in on_demand:
        try:
            path = _resolve_skill(name)
        except FileNotFoundError:
            logger.warning(
                "Skill %r not found in repo; the requesting agent will run without it. "
                "Question Framer may have hallucinated a skill name.",
                name,
            )
            missing.append(name)
            continue
        parts.append(f"\n\n---\n\n# {path.stem}\n\n{_read(path)}")
        loaded.append(f"{path.parent.name}/{path.name}")
    return "".join(parts), loaded, missing


def _load_domain_context(domain: str | None) -> tuple[str, list[str], bool, str | None]:
    """Returns (text, loaded_paths, missing_flag, domain_attempted).

    Search order: context/domains/<domain>.md, then context/examples/<domain>.md.
    Missing context is permissive — return empty text and missing_flag=True.
    """
    if not domain:
        return "", [], False, None

    for root in (CONTEXT_DOMAINS, CONTEXT_EXAMPLES):
        path = root / f"{domain}.md"
        if path.exists():
            return (
                f"\n\n---\n\n# DOMAIN CONTEXT — {domain}\n\n{_read(path)}",
                [f"{path.parent.name}/{path.name}"],
                False,
                domain,
            )

    return "", [], True, domain


def assemble_prompt(
    *,
    agent_name: str,
    skills: list[str] | None = None,
    domain: str | None = None,
) -> AssembledPrompt:
    """Build the system prompt for one agent call.

    `skills` is **deprecated and ignored**. Skills are now owned by the agent
    per `DEFAULT_SKILLS_BY_AGENT` — the Question Framer no longer chooses them.
    This eliminates skill-name hallucination at the pipeline entry point, which
    is exactly the kind of discipline breach a rigor-first framework cannot
    tolerate. The argument is kept for backward compatibility with existing
    callers (tests, replay tools) but its value does not affect prompt assembly.

    `domain` resolves a domain context document; absence is permissive.

    Returns the prompt as both a concatenated string (display/testing) and a structured
    list of system blocks with cache_control hints (for API calls with prompt caching).
    """
    # Note `skills` is intentionally unused. The canonical per-agent skill set
    # comes from DEFAULT_SKILLS_BY_AGENT. The orchestrator owns this; the LLM
    # Framer cannot influence it.
    del skills  # ignored by design
    canonical_skills = DEFAULT_SKILLS_BY_AGENT.get(agent_name, [])
    loaded_paths: list[str] = []

    # ---------- Block 1: Universal skills (cacheable; shared across all agents) ----------
    universal_text, universal_loaded = _load_universal_skills()
    loaded_paths.extend(universal_loaded)

    # ---------- Block 2: Agent + on-demand skills + domain context ----------
    # (cacheable; shared across retries of the same agent within a run)
    agent_section_parts: list[str] = []

    agent_text, agent_path = _load_agent(agent_name)
    agent_section_parts.append(f"\n\n---\n\n# AGENT DEFINITION — {agent_name}\n\n{agent_text}")
    loaded_paths.append(agent_path)

    skills_text, skills_loaded, missing_skills = _load_skills(canonical_skills)
    agent_section_parts.append(skills_text)
    loaded_paths.extend(skills_loaded)

    domain_text, domain_loaded, missing, attempted = _load_domain_context(domain)
    agent_section_parts.append(domain_text)
    loaded_paths.extend(domain_loaded)

    agent_section_text = "".join(agent_section_parts)

    # Both blocks are marked cacheable. Two cache breakpoints, well under Anthropic's
    # 4-breakpoint limit. Per Anthropic, cache_control on a block caches the prefix
    # *through* that block — so block 2's cache_control caches both blocks together
    # when both are identical (i.e., same agent re-invoked); block 1's cache_control
    # is the savings vehicle across different agents (universal skills don't change).
    system_blocks: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": universal_text,
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": agent_section_text,
            "cache_control": {"type": "ephemeral"},
        },
    ]

    concatenated = (universal_text + agent_section_text).strip()

    return AssembledPrompt(
        system_prompt=concatenated,
        system_blocks=system_blocks,
        sections_loaded=loaded_paths,
        missing_domain_context=missing,
        domain_attempted=attempted,
        universal_skills_sha256=_sha256_hex(universal_text),
        agent_block_sha256=_sha256_hex(agent_section_text),
        prompt_sha256=_sha256_hex(concatenated),
        missing_skills=missing_skills,
    )
