"""Cross-run synthesis tool — runs the Synthesizer Agent over N completed runs.

Reads each source run's Findings Validator artifact (the validated, graded findings
with caveats) and invokes the Synthesizer Agent to identify cross-functional
connections and notable non-connections.

The Synthesizer:
- Does NOT invent findings. Only connects existing validated ones.
- Caps connection grade at the weakest constituent source finding's grade.
- Carries forward every high-severity caveat from every source run.
- Runs confounding analysis on each connection candidate.
- Calibrates causation language per the investigator's flag in source findings.

Output:
- output/synthesis-<ts>.md — the rendered cross-functional report (or
  output/synthesis-<ts>-pending-review.md + a review prompt when HITL gates)
- runs/synthesis-<ts>/artifacts/<ts>-synthesizer-agent.json — the structured artifact

Usage:
    python -m src.tools.synthesize_runs --run-ids r1,r2,r3
    python -m src.tools.synthesize_runs --runs-glob "20260523T*"
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from src.api.claude_client import ClaudeClient
from src.orchestrator.budget_tracker import BudgetTracker
from src.orchestrator.hitl_gate import build_review_prompt, evaluate as hitl_evaluate
from src.orchestrator.prompt_assembler import assemble_prompt
from src.orchestrator.schemas import (
    SynthesizerPayload,
    agent_output_tool,
    validate_payload,
)

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_validator_artifact(run_dir: Path) -> dict[str, Any] | None:
    """Find this run's Findings Validator artifact. Returns None if not present."""
    artifacts_dir = run_dir / "artifacts"
    if not artifacts_dir.is_dir():
        return None
    # Validator artifacts follow the NN-findings-validator.json naming convention
    candidates = sorted(artifacts_dir.glob("*-findings-validator*.json"))
    if not candidates:
        return None
    # Prefer non-replay artifact if both exist
    primary = [p for p in candidates if "replay" not in p.name]
    chosen = primary[0] if primary else candidates[0]
    with chosen.open() as f:
        return json.load(f)


def _load_framer_metadata(run_dir: Path) -> dict[str, Any]:
    """Pull period/domain context from the Question Framer artifact, if available."""
    framer_path = run_dir / "artifacts" / "00-question-framer.json"
    if not framer_path.exists():
        return {}
    with framer_path.open() as f:
        art = json.load(f)
    payload = art.get("payload", {})
    return {
        "input_mode": payload.get("input_mode"),
        "decision_context": payload.get("decision_context", ""),
        "analytical_questions": payload.get("analytical_questions", []),
    }


def _build_synthesizer_user_message(
    *,
    source_inputs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build the user message handed to the Synthesizer Agent.

    Includes each source run's metadata + its full validator artifact payload.
    The validator artifact already contains the per-finding grades, layer
    results, required caveats, and revalidation summary — the gold standard
    abstraction for cross-run reasoning.
    """
    parts = [
        "# Stage role\nYou are running as the **synthesizer-agent**.",
        "",
        f"You have {len(source_inputs)} source run(s) below. Each one's "
        "Findings Validator output is included. Identify cross-functional "
        "connections and notable non-connections per your skills.",
        "",
        "# Source runs",
    ]
    for i, src in enumerate(source_inputs, start=1):
        parts.append(f"\n## Source run {i}: {src['run_id']}")
        if src.get("framer_metadata", {}).get("decision_context"):
            parts.append(f"**Decision context:** {src['framer_metadata']['decision_context']}")
        if src.get("framer_metadata", {}).get("analytical_questions"):
            qs = src['framer_metadata']['analytical_questions']
            parts.append(f"**Analytical questions ({len(qs)}):**")
            for q in qs[:5]:  # cap to first 5
                parts.append(f"  - {q}")
        parts.append("\n**Findings Validator artifact:**")
        parts.append("```json")
        parts.append(json.dumps(src["validator_payload"], indent=2, default=str))
        parts.append("```")

    parts.extend([
        "",
        "# Your task",
        "Produce your output as a `SynthesizerPayload` matching your schema. "
        "Emit via the structured tool. Connections only between findings ALREADY "
        "VALIDATED in the source runs above; never invent new findings. Apply "
        "confounding analysis on every candidate connection. Surface "
        "non-connections explicitly. Carry forward every high-severity caveat.",
    ])
    return [{"type": "text", "text": "\n".join(parts)}]


def _expand_run_ids(args: argparse.Namespace) -> list[str]:
    """Resolve the --run-ids comma-list and/or --runs-glob into a deduplicated list."""
    ids: list[str] = []
    if args.run_ids:
        ids.extend([s.strip() for s in args.run_ids.split(",") if s.strip()])
    if args.runs_glob:
        runs_dir = REPO_ROOT / "runs"
        for path in sorted(runs_dir.glob(args.runs_glob)):
            if path.is_dir():
                ids.append(path.name)
    # Dedup while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for rid in ids:
        if rid not in seen:
            seen.add(rid)
            out.append(rid)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--run-ids", type=str,
        help="Comma-separated list of run IDs (directory names under runs/).",
    )
    parser.add_argument(
        "--runs-glob", type=str,
        help="Glob pattern under runs/ — e.g. '20260523T*' picks every run that day.",
    )
    parser.add_argument(
        "--config", type=Path, default=Path("config/pipeline_config.yaml"),
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("output"),
    )
    parser.add_argument(
        "--domain", type=str, default=None,
        help="Domain context to load (if any). Defaults to no domain.",
    )
    args = parser.parse_args()

    run_ids = _expand_run_ids(args)
    if len(run_ids) < 2:
        logger.error(
            "Synthesizer requires at least 2 source runs; received %d (--run-ids=%r --runs-glob=%r).",
            len(run_ids), args.run_ids, args.runs_glob,
        )
        return 2

    with args.config.open() as f:
        cfg = yaml.safe_load(f)
    model = cfg.get("model_per_agent", {}).get("synthesizer-agent") or cfg["model_per_agent"]["findings-validator"]
    max_tokens = cfg.get("max_tokens_per_call", 16384)

    # Load each source run's Findings Validator artifact + framer metadata
    source_inputs: list[dict[str, Any]] = []
    for rid in run_ids:
        run_dir = REPO_ROOT / "runs" / rid
        if not run_dir.is_dir():
            logger.error("Run directory not found: %s", run_dir)
            return 1
        validator = _load_validator_artifact(run_dir)
        if validator is None:
            logger.warning("Run %s has no Findings Validator artifact — skipping.", rid)
            continue
        source_inputs.append({
            "run_id": rid,
            "validator_payload": validator.get("payload", {}),
            "framer_metadata": _load_framer_metadata(run_dir),
        })

    if len(source_inputs) < 2:
        logger.error(
            "After loading, only %d source run(s) had usable Findings Validator artifacts. Need ≥2.",
            len(source_inputs),
        )
        return 3

    logger.info("Synthesizing across %d source runs: %s", len(source_inputs), [s["run_id"] for s in source_inputs])

    # Build the prompt with the new universal skills + synthesizer skills loaded
    prompt = assemble_prompt(
        agent_name="synthesizer-agent",
        skills=[
            "cross-run-synthesis",
            "confounding-analysis",
            "counterfactual-reasoning",
            "confidence-language",
            "proactive-action-card",
            "descriptive-summary-format",
        ],
        domain=args.domain,
    )
    logger.info("Prompt assembled: %d chars, %d sections", len(prompt.system_prompt), len(prompt.sections_loaded))

    user_message = _build_synthesizer_user_message(source_inputs=source_inputs)

    client = ClaudeClient()
    budget = BudgetTracker(
        budget_tokens=cfg.get("budget_tokens_default", 1_200_000),
        cost_per_million=cfg.get("cost_per_million", {}),
        max_cost_usd=cfg.get("max_cost_usd"),
        cost_warning_thresholds=cfg.get("cost_warning_thresholds", [0.5, 0.75, 0.9]),
    )

    logger.info("Calling Synthesizer Agent (model=%s)...", model)
    t0 = time.perf_counter()
    response = client.call(
        model=model,
        system=prompt.system_blocks,
        messages=[{"role": "user", "content": user_message}],
        max_tokens=max_tokens,
        enable_code_execution=False,  # synthesizer reasons over upstream artifacts; no code-exec
        enable_files_api=False,
        output_tool=agent_output_tool("synthesizer-agent"),
        timeout_seconds=900.0,
    )
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    logger.info(
        "Call returned in %d ms. Tokens: in=%d out=%d (cache_read=%d cache_write=%d)",
        elapsed_ms,
        response.input_tokens, response.output_tokens,
        response.cache_read_tokens, response.cache_write_tokens,
    )
    budget.record(
        stage_index=0, agent="synthesizer-agent", model=model,
        input_tokens=response.input_tokens, output_tokens=response.output_tokens,
        cache_read_tokens=response.cache_read_tokens, cache_write_tokens=response.cache_write_tokens,
    )

    # Prefer structured tool_output; fall back to text parsing if necessary
    parsed: dict[str, Any] | None = response.tool_output
    if parsed is None:
        # Fallback path: try to extract JSON from text
        text = response.text.strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            for fence in ("```json", "```JSON", "```"):
                if fence in text:
                    start = text.find(fence) + len(fence)
                    end = text.find("```", start)
                    if end > start:
                        try:
                            parsed = json.loads(text[start:end].strip())
                            break
                        except json.JSONDecodeError:
                            continue

    if parsed is None:
        logger.error("No structured payload returned. Raw text saved to output/synthesis-failure-raw.txt")
        (args.output_dir / "synthesis-failure-raw.txt").write_text(response.text, encoding="utf-8")
        return 4

    # Ensure source_run_ids is set even if the model omitted it
    if "source_run_ids" not in parsed or not parsed["source_run_ids"]:
        parsed["source_run_ids"] = [s["run_id"] for s in source_inputs]

    try:
        payload = validate_payload("synthesizer-agent", parsed)
        assert isinstance(payload, SynthesizerPayload)
    except Exception as e:
        logger.error("Schema validation failed: %s", e)
        (args.output_dir / "synthesis-failed-payload.json").write_text(
            json.dumps(parsed, indent=2), encoding="utf-8"
        )
        return 5

    # Persist artifact
    synthesis_id = datetime.now(tz=timezone.utc).strftime("synthesis-%Y%m%dT%H%M%SZ")
    synth_run_dir = REPO_ROOT / "runs" / synthesis_id / "artifacts"
    synth_run_dir.mkdir(parents=True, exist_ok=True)
    artifact = {
        "schema_version": "1.0",
        "agent": "synthesizer-agent",
        "run_id": synthesis_id,
        "stage_index": 0,
        "produced_at": datetime.now(tz=timezone.utc).isoformat(),
        "duration_ms": elapsed_ms,
        "token_usage": {
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "cache_read_tokens": response.cache_read_tokens,
            "cache_write_tokens": response.cache_write_tokens,
        },
        "status": "ok",
        "payload": parsed,
        "prompt_sha256": prompt.prompt_sha256,
        "skill_hashes": {
            "universal": prompt.universal_skills_sha256,
            "agent_block": prompt.agent_block_sha256,
        },
    }
    artifact_path = synth_run_dir / f"{synthesis_id}-synthesizer-agent.json"
    artifact_path.write_text(json.dumps(artifact, indent=2, default=str), encoding="utf-8")
    logger.info("Artifact written: %s", artifact_path)

    # ---- HITL gate ----
    # Synthesis findings are high-stakes by definition; route through the same
    # gate the per-function pipelines use. We render the SynthesizerPayload's
    # connections as the action_cards-shaped input the gate expects.
    args.output_dir.mkdir(parents=True, exist_ok=True)
    synthesis_action_cards = [
        {
            "alert": c.mechanism,
            "confidence": c.grade,
            "why_it_matters": f"Cross-functional connection across runs {', '.join([str(s.get('run_id', '')) for s in c.source_findings])}.",
            "recommended_action": c.recommended_action or "(see synthesis report for details)",
            "owner_role": "(synthesis — owner depends on functional area)",
            "due": "(see synthesis report)",
            "caveats": [cv.model_dump() for cv in c.carried_caveats],
        }
        for c in payload.connections
    ]
    decision = hitl_evaluate(
        run_id=synthesis_id,
        output_dir=args.output_dir,
        comms_payload={"action_cards": synthesis_action_cards, "output_mode": "action-card"},
        threshold=cfg.get("hitl_review_threshold"),
    )
    decision.final_md_path.write_text(payload.rendered_output_markdown, encoding="utf-8")
    if decision.gated and decision.review_prompt_path is not None:
        decision.review_prompt_path.write_text(
            build_review_prompt(run_id=synthesis_id, decision=decision), encoding="utf-8"
        )
        logger.warning(
            "HITL gate triggered on synthesis output (threshold=%s, %d connections require review).",
            decision.threshold, len(decision.findings_triggering_review),
        )
        logger.info("Pending review at: %s", decision.final_md_path)
        logger.info("Review prompt at:  %s", decision.review_prompt_path)
    else:
        logger.info("Synthesis report written: %s", decision.final_md_path)

    # Summary
    print()
    print("=" * 72)
    print(f"SYNTHESIS SUCCEEDED — {synthesis_id}")
    print(f"  source runs:           {len(source_inputs)}")
    print(f"  connections found:     {len(payload.connections)}")
    print(f"  non-connections noted: {len(payload.non_connections)}")
    print(f"  carried caveats:       {len(payload.carried_caveats)}")
    print(f"  hitl gated:            {decision.gated}")
    print(f"  total tokens:          in={response.input_tokens}, out={response.output_tokens}")
    print(f"  total cost USD:        ${round(budget.total_cost(), 4)}")
    print(f"  report:                {decision.final_md_path}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
