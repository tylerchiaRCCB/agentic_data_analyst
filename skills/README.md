# Skills — Conventions for Contributors

This folder contains the methodology files agents load at runtime. The skills are organized into five categories:

- **universal/** — always loaded with every agent call. Set the rigor floor.
- **analytical/** — loaded on demand by specific agents per the Question Framer's `pipeline_composition`.
- **validation/** — loaded by the Findings Validator.
- **output/** — loaded by the Communication Agent.
- **domain-specific/** — loaded when the relevant domain context document calls for them. **This is the only category where domain-specific methodology lives.**

Read this file before writing or editing any skill. It captures three conventions that keep skills portable, reviewable, and aligned with the system's framing.

---

## 1. Domain terminology — skills are domain-generic *within our CPG company*

The system is designed to serve multiple **functional domains within our CPG company** — sales (commercial), supply chain, operations / manufacturing, finance, trade marketing, and so on — without re-authoring the agents or skills for each one. Every domain in scope is CPG; the "domain-genericness" we need is across functions, not across industries.

Domain specificity lives in two places:

- **`context/domains/<domain>.md`** — metric definitions, dimension hierarchies, guardrail pairings, quirks, anomaly thresholds. One file per functional domain (e.g., `context/domains/commercial-sales.md`, `context/domains/supply-chain.md`).
- **`skills/domain-specific/`** — methodology that depends on our company's CPG conventions and operating model. Examples in MVP: CPG-derived metrics (velocity, days-of-supply, ACV-weighted distribution); guardrail-pairing logic specific to CPG trade-offs (volume ↔ margin, distribution ↔ fill rate). These are CPG-specific *to our company* — not industry-generic, not cross-vertical.

Everything in `universal/`, `analytical/`, `validation/`, and `output/` should be **methodology that applies regardless of which CPG functional domain it's running against.**

### What this means in practice

- **Methodology rules speak in generic terms.** "For skewed metrics, default to median/MAD" — not "for sales volume, default to median/MAD." The methodology is general; sales volume is one example.
- **Concrete examples are valuable for instruction-following, but they must be labeled.** When using a specific scenario, mark it clearly: *"Example (sales): Account 47's instock dropped..."* or *"Example (supply chain): DC fill rate fell from 96% to 89%..."*. The LLM gets the anchor, the reader knows it's illustration, and a reviewer can spot what's load-bearing vs. what's example.
- **Multi-domain examples beat single-domain examples** when convenient — within our CPG company: *"an account (sales), a DC (supply chain), a production line (operations), a campaign (trade marketing), a region (any)"*. Small overhead, large portability gain across the functional domains we'll serve.
- **CPG-specific math lives in `domain-specific/` or in domain context documents,** not in `universal/`, `analytical/`, `validation/`, or `output/` skills. If you find yourself writing the velocity equation, days-of-supply formula, ACV-weighted distribution, fill-rate definition, OEE breakdown, or trade-deduction logic in a non-domain-specific skill, move it.

### Audit checklist when reviewing a skill

- Does the methodology rule depend on which CPG functional domain it's running in? If yes, the skill belongs in `domain-specific/` (or the rule belongs in the relevant domain context document). If no, the rule is generic — concrete examples are fine but should be labeled with the functional domain they illustrate.
- Are CPG-specific operational terms (instock, fill rate, ACV, days-of-supply, velocity, trade spend, OEE) mentioned outside `domain-specific/` without an explicit "Example (sales)" / "Example (supply chain)" framing? If so, fix.
- Are specific entity names ("Account 47", "DC Atlanta") used in examples? Fine — but label which functional domain they illustrate, and don't let them become the only level the rule is stated at.
- Are there examples drawn from other industries (e-commerce, SaaS, healthcare)? **Remove them.** Our system is for CPG. Cross-industry examples are noise.

---

## 2. Output-shape discipline — code execution returns summaries, not row dumps

Every skill that involves code execution must instruct the agent to request **summaries**, **scalars**, or **small tables of computed results** — never raw row dumps. A `df.head(1000)` returned to context defeats the architecture.

Each skill should include an "Output-shape discipline" section (or equivalent) stating what the relevant code execution returns. See [pipeline-definitions.md](../orchestration/pipeline-definitions.md) §10 for the full context-discipline rules.

---

## 3. Framing discipline — skills must allow honest negatives

Universal skills, analytical skills, and validation skills must all permit — and where appropriate, encourage — the conclusion that *nothing of significance was found.* No skill should be written in a way that implicitly obligates the agent to produce a finding.

When reviewing a draft, check:

- Does the language ever read as "find the most interesting X" or "surface the top Y" without an accompanying "or report that nothing rose to threshold" clause?
- Are anti-patterns sections honest about the failure mode of *manufacturing volume to look thorough*?
- Does the skill respect that "we tested and found nothing significant" is a valid analytical outcome?

The framing reminder at the top of the spec ([Core Framing](../mvp_plan.md#core-framing-read-first)) is binding on every skill. When in doubt, weaken the language; when not in doubt, weaken it anyway.

---

## 4. Cross-references

When referencing other skills or design documents:

- Link with the correct relative path: `[stl-decomposition.md](stl-decomposition.md)` from within the same folder; `[../universal/statistical-rigor.md](../universal/statistical-rigor.md)` across folders.
- Mark forward references to skills not yet built as `(deferred to Phase 2)` so reviewers know not to expect them.
- Section references use `§N` notation (e.g., `[statistical-rigor.md](../universal/statistical-rigor.md) §4`).

---

## 5. Token budget for skills

Each skill is loaded into the system prompt of every call that needs it. Token budget per skill: aim for **400–800 words** (~500–1,000 tokens). Universal skills should err shorter since they load every call.

Methodology skills can exceed this when warranted (e.g., `hypothesis-generation-from-data.md` is longer because it's the entry point of proactive monitoring). Cosmetic prose and redundant restatement should be trimmed; load-bearing methodology should not.
