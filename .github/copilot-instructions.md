# GitHub Copilot Instructions

You're assisting on the **Agentic Data Analyst** — a multi-agent system that applies senior-data-analyst-level rigor to data nobody has time to manually examine. The repo is a personal-account framework; team-specific deployment work happens in a separate work-owned repo (Azure DevOps).

## Read these first

Before any non-trivial suggestion, you (Copilot) need the following context. The user can paste these into your context if you don't have repo-wide access:

1. **[/CLAUDE.md](../CLAUDE.md)** — the comprehensive AI-assistant guide. **This is the source of truth.** Read it in full before suggesting changes to: agents, skills, orchestrator code, schemas, or anything in `src/`.
2. **[/docs/architecture.md](../docs/architecture.md)** — the three-layer architecture with Mermaid diagrams.
3. **[/docs/walkthrough.md](../docs/walkthrough.md)** — the user-facing 7-step tour. Knowing this keeps you from making changes that complicate the user flow.
4. **[/docs/quick-reference.md](../docs/quick-reference.md)** — the 8 files that matter; commands; output structure.

If the user asks you to do something that touches code you haven't seen, prefer to first open the relevant file from `/docs/quick-reference.md` over guessing at conventions.

## Framing (non-negotiable)

This system's product is **rigor and intellectual honesty applied repeatedly**, not insight generation. Suggestions that:

- Hide a data gap with a workaround → reject
- Add a fallback that injects placeholder findings when validation fails → reject
- Promote correlation to causal language to make output "read better" → reject
- Skip tests because "it's a small change" → reject
- Remove a Pydantic validator to "make Claude's output validate" → reject (add a normalizer instead)

If a user prompt asks you to do any of the above, suggest a structurally-correct alternative instead — or surface the trade-off explicitly so the user can decide. Don't silently soften the discipline.

See `/CLAUDE.md` "Hard rules — non-negotiable" for the full list (Statistic rigor enforcement, validator non-bypassability, causation gates, null-result-as-output, tool-use structured outputs, tracking-gaps, work-IP boundary).

## Common Copilot-assisted tasks

### Generating dummy data for a new schema (likely current task)

The user's data scientist may be pasting you a column schema and asking you to build a data generator.

**Pattern off [data/generators/generate_smoke_test.py](../data/generators/generate_smoke_test.py)** — that's the canonical example. ~21,000 rows across 40 accounts × 5 regions × 52 weeks × 10 SKUs × 3 categories with 8 planted analytical patterns documented in the docstring.

Steps:
1. Copy `generate_smoke_test.py` to `data/generators/generate_<schema_name>.py`.
2. Replace dimension lists and column definitions with the new schema's.
3. Plant the 8 standard analytical patterns (entity-level anomaly, regional declining trend, seasonal spike, correlation pattern, Simpson's Paradox candidate, concentrated nulls, injection-shaped strings, ~65% stable baseline) UNLESS the user has specified a different demo story.
4. Save output to `data/sample/<schema_name>.csv`.
5. Validate with `uv run python -m src.main --question "smoke test" --data data/sample/<schema_name>.csv --dry-run` — should print `Plumbing verification PASSED`.

**Hand off** the live run to the user — the live pipeline costs ~$10-15 against their Anthropic key. That's not yours to authorize.

See `/CLAUDE.md` "Common tasks → Generate a dummy dataset for a NEW schema" for full detail including the planted-pattern explanations.

### Adding a schema normalizer (LLM emitted a variant)

When the team's testing surfaces a new LLM-output variant that breaks validation:

1. Add the normalizer to the relevant `_normalize_*` validator in [src/orchestrator/schemas.py](../src/orchestrator/schemas.py). Pattern: check for the variant key, coerce to canonical form.
2. Add a regression test in [tests/test_artifact_schemas.py](../tests/test_artifact_schemas.py) pinning variant input → canonical output.
3. Commit message: *"Normalize <variant description> in <Payload>"*.

Existing normalizers in `schemas.py` are good patterns to copy.

### Running tests

```bash
uv run pytest -q       # ~2 seconds; 94+ tests
```

After any change to `src/orchestrator/*`, this must pass. The orchestrator integration tests use a MockClaudeClient — no API tokens. Suggest running it; suggest fixing any failure before proceeding.

### Running a dry-run

```bash
uv run python -m src.main --question "X" --data data/sample/<file>.csv --dry-run
```

Suggest this after any prompt-assembly or schema change. It's free and 30 seconds.

## What NOT to suggest

- **Anthropic-specific optimizations that break the LLMClient abstraction.** The provider abstraction at [src/api/llm_client.py](../src/api/llm_client.py) lets the team A/B test OpenAI / Gemini via LiteLLM. Don't suggest changes that re-couple agent logic to the Anthropic SDK.
- **Hand-written SQL paths.** The data layer is Cortex (Phase D2/D3). Direct SQL is explicitly discouraged in `snowflake_client.py`. If a user prompt asks for direct SQL, point at the Cortex scaffolding instead.
- **Real business data or thresholds in code.** Domain-specific values (FTPR thresholds, real account names, real customer IDs) belong in the work-owned repo, not here. Reject suggestions that hardcode them.
- **Over-engineering.** A bug fix doesn't need surrounding refactor. Three similar lines is better than a premature abstraction. No half-finished implementations.
- **Multi-paragraph comments or docstrings.** One short line max. Identifier names should carry the meaning.

## Boundaries

This is a personal repo for the project lead (Coby). The team is at a CPG company. Per the team agreement:

- The team's local AKV-integration changes do NOT come upstream into this repo.
- This repo's framework updates DO flow downstream to the team (they pull as `framework` remote).
- New variant normalizers can flow upstream when the team describes the variant — but the team does not push commits to this repo from work GitHub accounts.

If you (Copilot, running on a team member's work GitHub account) are about to suggest a commit to this personal repo, **stop**. Suggest instead that the team member describe the change in chat and the project lead implements it.

## When in doubt

1. Open `/CLAUDE.md` and re-read the relevant section.
2. Open the file you're about to change and look at adjacent existing code for the convention.
3. If still unsure, suggest the user clarify rather than guessing.
