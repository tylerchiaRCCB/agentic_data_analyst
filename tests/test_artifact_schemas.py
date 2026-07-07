"""Tests for the Pydantic artifact schemas.

Verifies:
- All 10 agent payloads parse against the schema dispatch.
- The "empty arrays are valid" invariant holds for fields that the framing requires
  to be empty-able (findings_review, action_cards, opportunity_areas, etc.).
- The Statistic.lineage shape is required and structurally correct.
- Unknown fields are allowed (per schemas §5).
- Missing required fields raise ValidationError.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.orchestrator.schemas import (
    ActionCard,
    Caveat,
    CommunicationAgentPayload,
    DataRetrievalPayload,
    FindingsValidatorPayload,
    LineageRef,
    OpportunityIdentifierPayload,
    Statistic,
    validate_payload,
)


def test_minimal_caveat() -> None:
    c = Caveat(text="x", severity="low", reason="r")
    assert c.severity == "low"


def test_statistic_requires_lineage() -> None:
    with pytest.raises(ValidationError):
        Statistic(
            id="s1",
            metric="m",
            value=1.0,
            computation="c",
            sample_size=10,
        )  # missing lineage


def test_statistic_with_lineage() -> None:
    s = Statistic(
        id="s1",
        metric="m",
        value=1.0,
        computation="c",
        sample_size=10,
        lineage=LineageRef(source="ds-1", data_slice="x == 'y'", code_ref="run/x/exec/y"),
    )
    assert s.lineage.data_slice == "x == 'y'"


def test_findings_validator_payload_empty_findings_review_valid() -> None:
    """The framing-critical invariant: empty findings_review is valid (no findings to review)."""
    payload = FindingsValidatorPayload(
        overall_assessment="Nothing rose to action this period.",
        findings_review=[],
        cross_cutting_issues=[],
        guardrail_check_results=[],
        revalidation_summary={"findings_recomputed": 0, "discrepancies_found": 0},
    )
    assert payload.findings_review == []


def test_communication_agent_payload_empty_action_cards_valid() -> None:
    """Same: action_cards can be empty. Renders descriptive summary instead."""
    payload = CommunicationAgentPayload(
        output_mode="descriptive-summary",
        rendered_output_markdown="## Weekly Summary\n\nNothing rose to action.",
        action_cards=[],
        descriptive_summary={"conclusion": "All clear."},
    )
    assert payload.action_cards == []
    assert payload.descriptive_summary is not None


def test_opportunity_identifier_empty_opportunities_valid() -> None:
    payload = OpportunityIdentifierPayload(
        performance_gaps=[],
        opportunity_areas=[],
        intervention_recommendations=[],
        predictive_readiness_assessment={"candidates": []},
        sensitivity_analysis=[],
    )
    assert payload.opportunity_areas == []


def test_action_card_requires_all_fields() -> None:
    with pytest.raises(ValidationError):
        ActionCard(alert="x")  # type: ignore[call-arg]


def test_validate_payload_dispatches_by_agent() -> None:
    raw = {
        "overall_assessment": "x",
        "findings_review": [],
        "cross_cutting_issues": [],
        "guardrail_check_results": [],
        "revalidation_summary": {"findings_recomputed": 0, "discrepancies_found": 0},
    }
    result = validate_payload("findings-validator", raw)
    assert isinstance(result, FindingsValidatorPayload)


def test_unknown_fields_allowed() -> None:
    """Per schemas §5: agents may extend with unknown fields without breaking validation."""
    raw = {
        "overall_assessment": "x",
        "findings_review": [],
        "cross_cutting_issues": [],
        "guardrail_check_results": [],
        "revalidation_summary": {"findings_recomputed": 0, "discrepancies_found": 0},
        "extra_field": "should not break validation",
    }
    result = validate_payload("findings-validator", raw)
    assert isinstance(result, FindingsValidatorPayload)


# ---------------------------------------------------------------------------
# Regression tests for observed LLM-output variants.
# Each test pins a variant input -> canonical normalized output so the
# normalizer surface only grows.
# ---------------------------------------------------------------------------


def test_caveat_normalizer_accepts_detail_alias() -> None:
    """Observed variant: model returns `{detail: "...", title: "...", caveat_id: "..."}`
    instead of `{text: "..."}`. The normalizer should coerce `detail` to `text`."""
    c = Caveat.model_validate({
        "detail": "Domain context document not loaded; thresholds are inferred.",
        "severity": "high",
        "title": "Missing context",
        "caveat_id": "c1",
    })
    assert c.text == "Domain context document not loaded; thresholds are inferred."
    assert c.severity == "high"


def test_action_card_normalizer_extracts_grade_from_verbose_string() -> None:
    """Observed variant: model emits a verbose confidence string like
    `"HIGH (Grade B) -- Statistical case is grade-A..."` instead of the
    bare letter. The normalizer should extract `B`."""
    card = ActionCard.model_validate({
        "alert": "Instock dropped",
        "confidence": "HIGH (Grade B) -- Statistical case is grade-A...",
        "why_it_matters": "x",
        "root_cause": "x",
        "recommended_action": "x",
        "owner_role": "x",
        "due": "x",
        "follow_up_trigger": "x",
    })
    assert card.confidence == "B"


def test_action_card_normalizer_extracts_grade_dash_form() -> None:
    """The `grade-A` / `grade_C` form should also coerce."""
    card = ActionCard.model_validate({
        "alert": "x",
        "confidence": "grade-A confidence based on triangulation",
        "why_it_matters": "x",
        "root_cause": "x",
        "recommended_action": "x",
        "owner_role": "x",
        "due": "x",
        "follow_up_trigger": "x",
    })
    assert card.confidence == "A"


def test_data_retrieval_payload_coerces_dict_column_metadata() -> None:
    """Observed variant: model returns column_metadata as a dataset-level dict
    (`{total_columns: N, free_text_count: M}`) instead of a per-column list.
    The normalizer should rebuild the list from the schema field."""
    payload = DataRetrievalPayload.model_validate({
        "dataset_handle": "h",
        "data_source_type": "uploaded_file",
        "source_reference": "/tmp/x.csv",
        "row_count": 100,
        "schema": [
            {"name": "account_id", "dtype": "string", "nullable": False},
            {"name": "instock_pct", "dtype": "float", "nullable": True},
        ],
        "column_metadata": {"total_columns": 2, "free_text_count": 0},
    })
    assert isinstance(payload.column_metadata, list)
    assert len(payload.column_metadata) == 2
    assert payload.column_metadata[0].name == "account_id"
    assert payload.column_metadata[1].name == "instock_pct"
    assert payload.column_metadata[1].is_free_text is False


# ---------------------------------------------------------------------------
# Structural-rigor enforcement on Statistic.
# A group_comparison/correlation/regression statistic without effect_size or
# confidence_interval cannot be validated — the artifact itself rejects it.
# ---------------------------------------------------------------------------


def test_statistic_descriptive_kind_does_not_require_effect_size() -> None:
    """Descriptive statistics (means, counts) are exempt from the effect-size rule."""
    from src.orchestrator.schemas import Statistic, LineageRef
    s = Statistic(
        id="s1", metric="mean_volume", value=142.5, computation="df.volume.mean()",
        sample_size=1000, statistic_kind="descriptive",
        lineage=LineageRef(source="dataset", data_slice="all", code_ref="cell_12"),
    )
    assert s.statistic_kind == "descriptive"


def test_statistic_group_comparison_accepts_missing_effect_size() -> None:
    """Schema accepts a group_comparison without effect_size — methodology rigor
    is enforced at the Findings Validator stage (downgrade + caveat), NOT at the
    artifact layer. Rejecting the artifact would throw away the entire stage's
    analytical work for one missing optional field. The Validator's Layer 1
    rigor check is the right place for this enforcement.
    See skills/validation/statistical-revalidation.md for the downgrade rules."""
    from src.orchestrator.schemas import LineageRef, Statistic
    s = Statistic(
        id="s1", metric="volume_diff", value=12.3,
        computation="mannwhitneyu(a, b)",
        sample_size=200,
        p_value=0.001,
        confidence_interval={"lower": 5.0, "upper": 20.0, "level": 0.95},
        statistic_kind="group_comparison",
        # effect_size intentionally MISSING — schema accepts; Validator handles
        lineage=LineageRef(source="dataset", data_slice="region=NE,SE", code_ref="cell_5"),
    )
    assert s.effect_size is None
    assert s.statistic_kind == "group_comparison"


def test_statistic_regression_null_result_accepts_missing_effect_size() -> None:
    """Regression test for the actual failure mode from the first real run:
    OLS slope checking Water-category FTPR stability — slope effectively zero,
    p=0.72, CI straddles zero. The agent correctly emitted this as kind='regression'
    without an effect_size because the ABSENCE of an effect is the finding.

    Previously the schema rejected this; new behavior accepts it. The Validator's
    Layer 1 rigor check renders this as a `pass` outcome (null result correctly
    documented), not a partial/fail."""
    from src.orchestrator.schemas import LineageRef, Statistic
    s = Statistic(
        id="stat_water_stability_check",
        metric="Water category late-segment FTPR slope (stability verification)",
        value=-7.1e-05,
        computation="OLS slope on Water-category volume-weighted weekly FTPR for late segment (weeks 38-51). p=0.72, CI straddles zero.",
        sample_size=14,
        p_value=0.72,
        unit="FTPR rate/week",
        statistic_kind="regression",
        # effect_size intentionally MISSING — null result, no effect to size
        lineage=LineageRef(
            source="synthetic_walmart.csv",
            data_slice="CATEGORY == 'Water' AND DATE >= 2026-03-30; weekly volume-weighted aggregate",
            code_ref="linregress(week_index, water_late_weekly_ftpr)",
        ),
    )
    assert s.effect_size is None  # absence is correct for a null result
    assert s.p_value == 0.72  # null result documented properly


def test_statistic_correlation_accepts_missing_confidence_interval() -> None:
    """CI is strongly recommended but NOT hard-required at the artifact layer.
    Multi-group omnibus tests (Kruskal-Wallis, ANOVA) and many other legitimate
    analyses don't naturally produce a clean CI on the test statistic. The
    Validator's Layer 1 downgrades findings citing CI-less statistics rather
    than rejecting them at the artifact layer.

    See `_enforce_required_fields_by_kind` — effect_size is required; CI is not.
    """
    from src.orchestrator.schemas import LineageRef, Statistic
    # Should validate without raising
    s = Statistic(
        id="s1", metric="spearman_rho", value=-0.235,
        computation="spearmanr(x, y)",
        sample_size=97,
        p_value=0.067,
        effect_size={"kind": "spearman_rho", "value": -0.235},
        # confidence_interval intentionally MISSING — this used to raise; now it's OK
        statistic_kind="correlation",
        lineage=LineageRef(source="dataset", data_slice="all", code_ref="cell_8"),
    )
    assert s.confidence_interval is None  # accepted as optional


def test_statistic_kruskal_wallis_omnibus_test_validates() -> None:
    """Regression test for the actual failure mode: Kruskal-Wallis omnibus
    test as a group_comparison Statistic, with eta_squared as effect size
    and no CI. This is the legitimate analytical pattern for multi-group
    distribution-difference tests. Used to reject at the artifact layer; now
    accepted. See commit retrospective on Walmart-OPD first real run."""
    from src.orchestrator.schemas import LineageRef, Statistic
    s = Statistic(
        id="stat_ftpr_category_kruskal",
        metric="FTPR_RATE variation across 8 categories",
        value=15182.9845,
        computation="Kruskal-Wallis H-statistic across 8 product categories",
        sample_size=100000,
        p_value=0.0,
        effect_size={"eta_squared": 0.151772},
        confidence_interval=None,  # not naturally available for omnibus tests
        statistic_kind="group_comparison",
        correction_method="none-justified",
        correction_notes="Single omnibus test across all categories; no further correction applied at profiling stage",
        lineage=LineageRef(
            source="synthetic_walmart.csv",
            data_slice="all rows grouped by CATEGORY",
            code_ref="stats.kruskal(*groups)",
        ),
    )
    assert s.statistic_kind == "group_comparison"
    assert s.effect_size == {"eta_squared": 0.151772}


def test_statistic_other_kind_is_unenforced_for_backward_compat() -> None:
    """Legacy artifacts without statistic_kind default to 'other' — no enforcement."""
    from src.orchestrator.schemas import Statistic, LineageRef
    s = Statistic(
        id="s1", metric="something", value=1.0, computation="x",
        sample_size=10,
        lineage=LineageRef(source="dataset", data_slice="all", code_ref="cell_1"),
    )
    assert s.statistic_kind == "other"
    # No effect_size required, no CI required


# ---------------------------------------------------------------------------
# Envelope unwrapping — Claude tool_use occasionally wraps the artifact in a
# single-key envelope ($PARAMETER_VALUE etc.); validate_payload strips it
# before Pydantic sees it so the schema doesn't fail on superficial nesting.
# ---------------------------------------------------------------------------


def test_unwrap_envelope_strips_parameter_value_wrapper() -> None:
    """Claude's emit_*_artifact tool_use sometimes wraps the input in
    `{"$PARAMETER_VALUE": {actual payload}}` — likely training-data templating
    bleed-through. The actual payload is one level too deep for Pydantic to
    find the required fields. Test pins this exact failure mode from the DS's
    real run."""
    from src.orchestrator.schemas import validate_payload

    # Build a valid root-cause-investigator payload, then wrap it
    inner_payload = {
        "anomaly_under_investigation": {
            "description": "Test anomaly",
            "scope": "test",
        },
        "primary_root_cause": {
            "causation_vs_correlation": "associational",
            "explanation": "test",
        },
        "analytical_caveats": [],
        "statistics": [],
    }
    wrapped = {"$PARAMETER_VALUE": inner_payload}

    # Without unwrapping, this would fail with "Field required: anomaly_under_investigation"
    result = validate_payload("root-cause-investigator", wrapped)
    assert result.anomaly_under_investigation == {"description": "Test anomaly", "scope": "test"}


def test_unwrap_envelope_strips_input_wrapper() -> None:
    """Variant: Claude sometimes echoes back the tool_use parameter name `input`."""
    from src.orchestrator.schemas import validate_payload

    inner_payload = {
        "anomaly_under_investigation": {"description": "x", "scope": "x"},
        "primary_root_cause": {"causation_vs_correlation": "associational", "explanation": "x"},
    }
    wrapped = {"input": inner_payload}
    result = validate_payload("root-cause-investigator", wrapped)
    assert result.anomaly_under_investigation["description"] == "x"


def test_unwrap_envelope_handles_double_wrap() -> None:
    """Defense in depth: even if the model double-wraps, unwrap up to max_depth."""
    from src.orchestrator.schemas import validate_payload

    inner_payload = {
        "anomaly_under_investigation": {"description": "x", "scope": "x"},
        "primary_root_cause": {"causation_vs_correlation": "associational", "explanation": "x"},
    }
    double_wrapped = {"$PARAMETER_VALUE": {"input": inner_payload}}
    result = validate_payload("root-cause-investigator", double_wrapped)
    assert result.anomaly_under_investigation["description"] == "x"


def test_unwrap_envelope_does_not_unwrap_legitimate_single_key_payloads() -> None:
    """Safeguard: a real payload with one top-level key whose name isn't in the
    known envelope set should NOT be unwrapped. Tests the guard against
    accidentally destructuring legitimate single-field artifacts."""
    from src.orchestrator.schemas import _unwrap_envelope

    legitimate_single_key = {"custom_top_level_field": {"a": 1}}
    result = _unwrap_envelope(legitimate_single_key)
    assert result == legitimate_single_key  # untouched


def test_unwrap_envelope_does_not_unwrap_multi_key_payloads() -> None:
    """Safeguard: payloads with multiple top-level keys are real artifacts,
    not envelopes — never unwrap, regardless of key names."""
    from src.orchestrator.schemas import _unwrap_envelope

    real_payload = {
        "input": "some user input field",  # has "input" but also other keys
        "other_field": 42,
    }
    result = _unwrap_envelope(real_payload)
    assert result == real_payload  # untouched
