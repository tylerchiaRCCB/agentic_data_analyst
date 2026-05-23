"""Tests for the human-in-the-loop gate."""

from __future__ import annotations

from pathlib import Path

from src.orchestrator.hitl_gate import HITLDecision, build_review_prompt, evaluate


def _payload(cards: list[dict]) -> dict:
    return {
        "output_mode": "action-card",
        "rendered_output_markdown": "# X\n",
        "action_cards": cards,
    }


def test_hitl_disabled_when_threshold_is_none(tmp_path: Path) -> None:
    """No threshold → no gate, output goes to <run_id>.md."""
    d = evaluate(
        run_id="r1", output_dir=tmp_path,
        comms_payload=_payload([{"confidence": "A", "alert": "x"}]),
        threshold=None,
    )
    assert not d.gated
    assert d.final_md_path.name == "r1.md"
    assert d.review_prompt_path is None


def test_hitl_disabled_for_invalid_threshold(tmp_path: Path) -> None:
    """Garbage threshold → treated as disabled, with no crash."""
    d = evaluate(
        run_id="r1", output_dir=tmp_path,
        comms_payload=_payload([{"confidence": "A", "alert": "x"}]),
        threshold="Z",
    )
    assert not d.gated
    assert d.final_md_path.name == "r1.md"


def test_hitl_gates_when_finding_at_or_above_threshold(tmp_path: Path) -> None:
    """Threshold A; one card grade A → gated."""
    d = evaluate(
        run_id="r1", output_dir=tmp_path,
        comms_payload=_payload([
            {"confidence": "A", "alert": "Big finding", "why_it_matters": "matters", "recommended_action": "do x"},
            {"confidence": "C", "alert": "Smaller"},
        ]),
        threshold="A",
    )
    assert d.gated
    assert d.final_md_path.name == "r1-pending-review.md"
    assert d.review_prompt_path is not None
    assert d.review_prompt_path.name == "r1-review-prompt.md"
    assert len(d.findings_triggering_review) == 1
    assert d.findings_triggering_review[0]["alert"] == "Big finding"


def test_hitl_does_not_gate_when_all_below_threshold(tmp_path: Path) -> None:
    """Threshold A; no card grade A → publish straight through."""
    d = evaluate(
        run_id="r1", output_dir=tmp_path,
        comms_payload=_payload([
            {"confidence": "B", "alert": "Mid"},
            {"confidence": "C", "alert": "Low"},
        ]),
        threshold="A",
    )
    assert not d.gated
    assert d.final_md_path.name == "r1.md"


def test_hitl_threshold_b_gates_a_and_b(tmp_path: Path) -> None:
    """Threshold B → both A and B trigger; C does not."""
    d = evaluate(
        run_id="r1", output_dir=tmp_path,
        comms_payload=_payload([
            {"confidence": "B", "alert": "Mid finding"},
            {"confidence": "C", "alert": "Low"},
        ]),
        threshold="B",
    )
    assert d.gated
    assert len(d.findings_triggering_review) == 1
    assert d.findings_triggering_review[0]["alert"] == "Mid finding"


def test_hitl_review_prompt_renders_card_details() -> None:
    """The review prompt includes alert, confidence, why-it-matters, action, owner, due."""
    decision = HITLDecision(
        gated=True,
        threshold="A",
        findings_triggering_review=[{
            "alert": "Account 47 instock dropped 19 points",
            "confidence": "A",
            "why_it_matters": "Margin exposure of $400k",
            "recommended_action": "Field call to retailer",
            "owner_role": "Field Sales Lead",
            "due": "2026-05-29",
            "caveats": [
                {"severity": "high", "text": "Magnitude estimated; refresh confirmed"},
            ],
        }],
        final_md_path=Path("/tmp/r1-pending-review.md"),
        review_prompt_path=Path("/tmp/r1-review-prompt.md"),
    )
    text = build_review_prompt(run_id="r1", decision=decision)
    assert "Account 47 instock dropped 19 points" in text
    assert "grade A" in text
    assert "Margin exposure of $400k" in text
    assert "Field call to retailer" in text
    assert "Field Sales Lead" in text
    assert "2026-05-29" in text
    assert "Magnitude estimated" in text
    assert "How to proceed" in text
