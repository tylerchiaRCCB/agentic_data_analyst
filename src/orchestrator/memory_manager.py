"""Session memory — in-memory stub for MVP.

The interactive Q&A mode is deferred to Phase 2, so this is a placeholder. The MVP
proactive-monitoring pipeline does not consume prior session state. When interactive
mode lands, this becomes a real per-session store (likely Redis or Cosmos DB in
production per Part 7).

For now the API is shaped so the orchestrator can call it uniformly, and the methods
are no-ops or trivial in-memory operations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MemoryManager:
    session_id: str | None = None
    established_facts: list[dict[str, Any]] = field(default_factory=list)

    def fetch_context_for_framer(self) -> dict[str, Any]:
        """Return any prior context the Question Framer should consume. MVP: empty."""
        return {"established_facts": [], "session_summary": None}

    def record_established_fact(self, fact: dict[str, Any]) -> None:
        """Stash a stable finding so downstream calls in the same session don't re-derive."""
        self.established_facts.append(fact)
