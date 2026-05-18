"""Loads markdown files into the system prompt for each agent call.

Assembly order per pipeline-definitions.md §4:
  1. Universal skills (all files in skills/universal/) — always loaded
  2. Agent definition (agents/<name>.md)
  3. Per-stage skills (skills/analytical/<x>.md, skills/validation/<x>.md, etc.)
  4. Domain context (context/domains/<domain>.md or context/examples/<domain>.md if available)

Missing skill file → fail loud (raises FileNotFoundError).
Missing domain context → permissive: proceed with universal + analytical skills only and
return a high-severity caveat the caller must propagate to the run. See
failure-recovery.md §6a.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

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


@dataclass
class AssembledPrompt:
    system_prompt: str
    sections_loaded: list[str] = field(default_factory=list)
    missing_domain_context: bool = False
    domain_attempted: str | None = None


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


def _load_skills(skill_names: list[str]) -> tuple[str, list[str]]:
    if not skill_names:
        return "", []
    parts: list[str] = ["\n\n---\n\n# ON-DEMAND SKILLS\n"]
    loaded: list[str] = []
    for name in skill_names:
        path = _resolve_skill(name)
        parts.append(f"\n\n---\n\n# {path.stem}\n\n{_read(path)}")
        loaded.append(f"{path.parent.name}/{path.name}")
    return "".join(parts), loaded


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

    `skills` is the list from the Question Framer's `pipeline_composition` for this stage.
    `domain` resolves a domain context document; absence is permissive.
    """
    sections: list[str] = []
    loaded_paths: list[str] = []

    universal_text, universal_loaded = _load_universal_skills()
    sections.append(universal_text)
    loaded_paths.extend(universal_loaded)

    agent_text, agent_path = _load_agent(agent_name)
    sections.append(f"\n\n---\n\n# AGENT DEFINITION — {agent_name}\n\n{agent_text}")
    loaded_paths.append(agent_path)

    skills_text, skills_loaded = _load_skills(skills or [])
    sections.append(skills_text)
    loaded_paths.extend(skills_loaded)

    domain_text, domain_loaded, missing, attempted = _load_domain_context(domain)
    sections.append(domain_text)
    loaded_paths.extend(domain_loaded)

    return AssembledPrompt(
        system_prompt="".join(sections).strip(),
        sections_loaded=loaded_paths,
        missing_domain_context=missing,
        domain_attempted=attempted,
    )
