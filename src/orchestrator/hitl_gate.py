"""Human-in-the-loop gate for high-stakes findings.

When `hitl_review_threshold` is configured (e.g., "A"), any rendered output
that contains an action card at or above that grade is held for review:
- Recipient markdown is written to `output/<run_id>-pending-review.md`
  (not the unsuffixed location a normal delivery would publish from).
- A separate `output/<run_id>-review-prompt.md` summarizes which findings
  need review and why — designed to be opened by a human reviewer who
  approves, edits, or rejects the output before delivery.

When the threshold is `None`, the gate is disabled and outputs publish
straight through — appropriate for the MVP / demo workflow. Enable in
production deployments for findings driving business-impacting decisions.

This is a deterministic post-processing step that runs after the
Communication Agent. It does not call any LLMs; it only inspects the
already-rendered output and routes the files.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Ordering: A is most confident; F is least. Threshold "A" gates ONLY grade-A
# findings; threshold "B" gates A and B; threshold "C" gates A, B, and C.
_GRADE_ORDER: dict[str, int] = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}


@dataclass
class HITLDecision:
    """Result of a HITL gate evaluation."""

    gated: bool
    threshold: str | None
    findings_triggering_review: list[dict[str, Any]]
    final_md_path: Path
    review_prompt_path: Path | None


def evaluate(
    *,
    run_id: str,
    output_dir: Path,
    comms_payload: dict[str, Any],
    threshold: str | None,
) -> HITLDecision:
    """Decide where to write the final markdown and (optionally) a review prompt.

    Returns a HITLDecision that the caller uses to write the actual files.
    Does NOT write anything itself — file IO is the caller's concern.
    """
    if not threshold:
        # Gate disabled; publish straight through.
        return HITLDecision(
            gated=False,
            threshold=None,
            findings_triggering_review=[],
            final_md_path=output_dir / f"{run_id}.md",
            review_prompt_path=None,
        )

    threshold_score = _GRADE_ORDER.get(threshold.upper(), -1)
    if threshold_score < 0:
        # Invalid threshold; act as disabled (with a caveat the caller will log)
        return HITLDecision(
            gated=False,
            threshold=threshold,
            findings_triggering_review=[],
            final_md_path=output_dir / f"{run_id}.md",
            review_prompt_path=None,
        )

    action_cards = comms_payload.get("action_cards") or []
    triggering = [
        card
        for card in action_cards
        if _GRADE_ORDER.get(str(card.get("confidence", "")).upper(), -1) >= threshold_score
    ]

    if not triggering:
        # No findings cross the threshold; publish straight through.
        return HITLDecision(
            gated=False,
            threshold=threshold,
            findings_triggering_review=[],
            final_md_path=output_dir / f"{run_id}.md",
            review_prompt_path=None,
        )

    # Gated.
    return HITLDecision(
        gated=True,
        threshold=threshold,
        findings_triggering_review=triggering,
        final_md_path=output_dir / f"{run_id}-pending-review.md",
        review_prompt_path=output_dir / f"{run_id}-review-prompt.md",
    )


def build_review_prompt(*, run_id: str, decision: HITLDecision) -> str:
    """Build the markdown content of the review-prompt file.

    The reviewer reads this to understand what needs human attention before
    the run is delivered. Designed to be self-contained — the reviewer
    shouldn't need to open the pending-review markdown to know what's at stake.
    """
    lines: list[str] = [
        f"# Human-review required — run {run_id}",
        "",
        f"This run produced **{len(decision.findings_triggering_review)} action card(s)** at confidence "
        f"≥ **{decision.threshold}** — your configured HITL threshold. The recipient-facing "
        f"output has been held at `{decision.final_md_path.name}` pending your review.",
        "",
        "## Findings requiring review",
        "",
    ]

    for i, card in enumerate(decision.findings_triggering_review, start=1):
        alert = card.get("alert") or "(no alert text)"
        confidence = card.get("confidence", "?")
        why = card.get("why_it_matters") or "(no impact statement)"
        action = card.get("recommended_action") or "(no recommended action)"
        owner = card.get("owner_role") or "(unassigned)"
        due = card.get("due") or "(no due date)"
        lines.extend([
            f"### {i}. {alert}  *(grade {confidence})*",
            "",
            f"**Why this matters:** {why}",
            "",
            f"**Recommended action:** {action}",
            "",
            f"**Owner:** {owner}  |  **Due:** {due}",
            "",
            "**Caveats / limitations:**",
        ])
        caveats = card.get("caveats") or []
        if not caveats:
            lines.append("- (none surfaced by the validator)")
        else:
            for c in caveats:
                text = c.get("text") if isinstance(c, dict) else str(c)
                sev = c.get("severity") if isinstance(c, dict) else ""
                lines.append(f"- *[{sev}]* {text}")
        lines.append("")

    lines.extend([
        "## How to proceed",
        "",
        "1. Review each finding above — methodology, caveats, recommended action.",
        f"2. Open `{decision.final_md_path.name}` to see the full rendered output the recipient would receive.",
        "3. To approve: rename `{run_id}-pending-review.md` → `{run_id}.md` and deliver.",
        "4. To edit: modify the pending-review markdown in place, then rename.",
        "5. To reject: delete both files and document the reason.",
        "",
        "The pipeline halted at the HITL gate as configured — this is the system working as designed.",
    ])
    return "\n".join(lines)
