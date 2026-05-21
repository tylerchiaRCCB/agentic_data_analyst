"""Extract context-requirements signals from pipeline runs.

When the pipeline runs without a domain context document (the
contextless-initial-testing mode per failure-recovery.md §6a), every agent
surfaces what it WOULD HAVE NEEDED to do its job better:

- The Question Framer's "ideal_but_unavailable" data requirements
- The Data Profiler's mandatory caveats and data integrity risks
- The Pattern Discoverer's "data_gap_to_strengthen" notes on hypotheses
- The Findings Validator's `guardrail_check_results` flagged as missing_data
- The Communication Agent's "Open Data Gaps" section and carried caveats
- Per-finding required_caveats that reference missing thresholds / targets / baselines

This tool reads a run's artifacts (or all runs) and emits a clean structured
list of those signals — the agenda for the domain-context-building meeting.

Usage:
    # Single run
    uv run python -m src.tools.extract_context_gaps --run-id 20260520T223548Z-89dba6ec

    # All runs, deduplicated + frequency-counted
    uv run python -m src.tools.extract_context_gaps --all

    # Output formats
    uv run python -m src.tools.extract_context_gaps --run-id <id> --format json
    uv run python -m src.tools.extract_context_gaps --run-id <id> --out gaps.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNS_ROOT = REPO_ROOT / "runs"


@dataclass
class ContextGap:
    """A single context-requirement signal extracted from a pipeline artifact."""

    text: str  # The actual content (caveat text, gap description, etc.)
    category: str  # caveat | guardrail-pairing | data-gap | hypothesis-rationale | integrity-risk
    severity: str  # high | medium | low | n/a
    source_agent: str  # which agent emitted it
    source_field: str  # which field in the artifact
    run_id: str

    def normalized_text(self) -> str:
        """Lowercase + strip whitespace/punctuation prefix for fuzzy dedup."""
        t = re.sub(r"[^a-z0-9 ]+", " ", self.text.lower())
        t = re.sub(r"\s+", " ", t).strip()
        return t[:120]  # use prefix for dedup key


def _load_artifact(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _coerce_to_list(value: Any) -> list[Any]:
    """Defensively coerce to list: dict → [dict], str → [str], None → [], list → list."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (str, dict)):
        return [value]
    return []


def _extract_caveat_list(
    items: Any,
    *,
    category: str,
    source_agent: str,
    source_field: str,
    run_id: str,
) -> list[ContextGap]:
    """Convert a list of caveat-shaped dicts (or strings) into ContextGap entries."""
    out: list[ContextGap] = []
    items = _coerce_to_list(items)
    for item in items:
        if isinstance(item, str):
            out.append(ContextGap(
                text=item,
                category=category,
                severity="n/a",
                source_agent=source_agent,
                source_field=source_field,
                run_id=run_id,
            ))
        elif isinstance(item, dict):
            text = (
                item.get("text")
                or item.get("description")
                or item.get("caveat")
                or item.get("message")
                or item.get("note")
                or str(item)
            )
            severity = str(item.get("severity", "n/a")).lower()
            out.append(ContextGap(
                text=text,
                category=category,
                severity=severity,
                source_agent=source_agent,
                source_field=source_field,
                run_id=run_id,
            ))
    return out


def _extract_from_run(run_dir: Path) -> list[ContextGap]:
    """Walk a single run's artifacts and pull every context-gap signal."""
    run_id = run_dir.name
    artifacts_dir = run_dir / "artifacts"
    if not artifacts_dir.exists():
        return []

    gaps: list[ContextGap] = []

    # ---- Question Framer ----
    framer = _load_artifact(artifacts_dir / "00-question-framer.json")
    if framer:
        payload = framer.get("payload", {})
        # Top-level caveats
        gaps.extend(_extract_caveat_list(
            payload.get("caveats", []),
            category="caveat",
            source_agent="question-framer",
            source_field="caveats",
            run_id=run_id,
        ))
        # data_requirements.ideal_but_unavailable / limitations_from_gaps
        dr = payload.get("data_requirements", {})
        if isinstance(dr, dict):
            for item in _coerce_to_list(dr.get("ideal_but_unavailable")):
                if isinstance(item, str) and len(item) > 5:
                    gaps.append(ContextGap(
                        text=item,
                        category="data-gap",
                        severity="medium",
                        source_agent="question-framer",
                        source_field="data_requirements.ideal_but_unavailable",
                        run_id=run_id,
                    ))
            for item in _coerce_to_list(dr.get("limitations_from_gaps")):
                if isinstance(item, str) and len(item) > 5:
                    gaps.append(ContextGap(
                        text=item,
                        category="data-gap",
                        severity="medium",
                        source_agent="question-framer",
                        source_field="data_requirements.limitations_from_gaps",
                        run_id=run_id,
                    ))

    # ---- Data Retrieval Agent ----
    for path in artifacts_dir.glob("*-data-retrieval-agent.json"):
        art = _load_artifact(path)
        if not art:
            continue
        gaps.extend(_extract_caveat_list(
            art.get("payload", {}).get("load_warnings", []),
            category="caveat",
            source_agent="data-retrieval-agent",
            source_field="load_warnings",
            run_id=run_id,
        ))

    # ---- Data Profiler ----
    for path in artifacts_dir.glob("*-data-profiler.json"):
        art = _load_artifact(path)
        if not art:
            continue
        p = art.get("payload", {})
        gaps.extend(_extract_caveat_list(
            p.get("mandatory_caveats", []),
            category="caveat",
            source_agent="data-profiler",
            source_field="mandatory_caveats",
            run_id=run_id,
        ))
        gaps.extend(_extract_caveat_list(
            p.get("quality_issues", []),
            category="caveat",
            source_agent="data-profiler",
            source_field="quality_issues",
            run_id=run_id,
        ))
        # data integrity risks
        for risk in p.get("data_integrity_risks", []) or []:
            if isinstance(risk, dict):
                text = risk.get("explanation") or risk.get("description") or risk.get("text") or str(risk)
                gaps.append(ContextGap(
                    text=text,
                    category="integrity-risk",
                    severity=str(risk.get("severity", "medium")).lower(),
                    source_agent="data-profiler",
                    source_field="data_integrity_risks",
                    run_id=run_id,
                ))

    # ---- Pattern Discoverer (hypotheses' data_gap_to_strengthen) ----
    for path in artifacts_dir.glob("*-pattern-discoverer.json"):
        art = _load_artifact(path)
        if not art:
            continue
        p = art.get("payload", {})
        for h in _coerce_to_list(p.get("generated_hypotheses")):
            if not isinstance(h, dict):
                continue
            gap_text = h.get("data_gap_to_strengthen")
            if gap_text and isinstance(gap_text, str) and len(gap_text) > 5:
                gaps.append(ContextGap(
                    text=gap_text,
                    category="hypothesis-rationale",
                    severity="medium",
                    source_agent="pattern-discoverer",
                    source_field=f"generated_hypotheses[{h.get('id','?')}].data_gap_to_strengthen",
                    run_id=run_id,
                ))
        # structural caveats
        gaps.extend(_extract_caveat_list(
            p.get("caveats", []),
            category="caveat",
            source_agent="pattern-discoverer",
            source_field="caveats",
            run_id=run_id,
        ))

    # ---- Findings Validator (guardrail check + cross-cutting) ----
    for path in artifacts_dir.glob("*-findings-validator.json"):
        art = _load_artifact(path)
        if not art:
            continue
        p = art.get("payload", {})
        for gc in p.get("guardrail_check_results", []) or []:
            if isinstance(gc, dict) and gc.get("flag") == "missing_data":
                primary = gc.get("primary_metric", "?")
                paired = gc.get("paired_metric", "?")
                gaps.append(ContextGap(
                    text=f"No guardrail pairing computable for primary={primary} / paired={paired}",
                    category="guardrail-pairing",
                    severity="medium",
                    source_agent="findings-validator",
                    source_field="guardrail_check_results",
                    run_id=run_id,
                ))
        for cci in p.get("cross_cutting_issues", []) or []:
            if isinstance(cci, dict):
                text = cci.get("issue") or cci.get("description") or str(cci)
                gaps.append(ContextGap(
                    text=text,
                    category="caveat",
                    severity=str(cci.get("severity", "medium")).lower(),
                    source_agent="findings-validator",
                    source_field="cross_cutting_issues",
                    run_id=run_id,
                ))
        # Per-finding required_caveats
        for f in p.get("findings_review", []) or []:
            if not isinstance(f, dict):
                continue
            gaps.extend(_extract_caveat_list(
                f.get("required_caveats", []),
                category="caveat",
                source_agent="findings-validator",
                source_field=f"findings_review[{f.get('finding_id','?')}].required_caveats",
                run_id=run_id,
            ))

    # ---- Communication Agent (carried caveats + action card caveats + descriptive summary gaps) ----
    for path in (
        list(artifacts_dir.glob("*-communication-agent.json"))
        + list(artifacts_dir.glob("*-communication-agent-replay.json"))
    ):
        art = _load_artifact(path)
        if not art:
            continue
        p = art.get("payload", {})
        gaps.extend(_extract_caveat_list(
            p.get("carried_caveats", []),
            category="caveat",
            source_agent="communication-agent",
            source_field="carried_caveats",
            run_id=run_id,
        ))
        for card in p.get("action_cards", []) or []:
            if isinstance(card, dict):
                gaps.extend(_extract_caveat_list(
                    card.get("caveats", []),
                    category="caveat",
                    source_agent="communication-agent",
                    source_field=f"action_cards[{card.get('source_finding_id','?')}].caveats",
                    run_id=run_id,
                ))
        # Descriptive-summary open_data_gaps if present
        ds = p.get("descriptive_summary") or {}
        if isinstance(ds, dict):
            for gap in ds.get("open_data_gaps", []) or []:
                if isinstance(gap, str):
                    gaps.append(ContextGap(
                        text=gap,
                        category="data-gap",
                        severity="medium",
                        source_agent="communication-agent",
                        source_field="descriptive_summary.open_data_gaps",
                        run_id=run_id,
                    ))
                elif isinstance(gap, dict):
                    text = gap.get("text") or gap.get("description") or gap.get("gap") or str(gap)
                    gaps.append(ContextGap(
                        text=text,
                        category="data-gap",
                        severity=str(gap.get("severity", "medium")).lower(),
                        source_agent="communication-agent",
                        source_field="descriptive_summary.open_data_gaps",
                        run_id=run_id,
                    ))

    return gaps


def _aggregate(all_gaps: list[ContextGap]) -> list[dict[str, Any]]:
    """Deduplicate gaps across runs by normalized text prefix.

    Returns one entry per unique gap with frequency count, severity (max),
    sources (agents that surfaced it), and list of run_ids.
    """
    by_key: dict[str, list[ContextGap]] = {}
    for g in all_gaps:
        by_key.setdefault(g.normalized_text(), []).append(g)

    severity_order = {"high": 3, "medium": 2, "low": 1, "n/a": 0}

    out: list[dict[str, Any]] = []
    for key, items in by_key.items():
        max_sev = max(items, key=lambda g: severity_order.get(g.severity, 0))
        sources = sorted({g.source_agent for g in items})
        runs = sorted({g.run_id for g in items})
        # Use the longest version of the text (most informative)
        text = max(items, key=lambda g: len(g.text)).text
        out.append({
            "text": text,
            "frequency": len(items),
            "categories": sorted({g.category for g in items}),
            "severity": max_sev.severity,
            "sources": sources,
            "runs": runs,
        })

    # Sort: severity desc, then frequency desc, then category
    out.sort(key=lambda e: (
        -severity_order.get(e["severity"], 0),
        -e["frequency"],
        e["categories"][0] if e["categories"] else "",
    ))
    return out


# ---- Output renderers ----


def _render_markdown_single(gaps: list[ContextGap]) -> str:
    if not gaps:
        return "# Context Gaps\n\nNo context-gap signals extracted from this run.\n"
    cat_buckets: dict[str, list[ContextGap]] = {}
    for g in gaps:
        cat_buckets.setdefault(g.category, []).append(g)

    out = ["# Context Gaps — single run\n"]
    out.append(f"**Run:** `{gaps[0].run_id}`\n")
    out.append(f"**Total signals extracted:** {len(gaps)}\n")

    for cat in ("data-gap", "guardrail-pairing", "caveat", "integrity-risk", "hypothesis-rationale"):
        bucket = cat_buckets.get(cat, [])
        if not bucket:
            continue
        out.append(f"\n## {cat} ({len(bucket)})\n")
        out.append("| Severity | Source | Text |")
        out.append("|---|---|---|")
        for g in sorted(bucket, key=lambda g: g.severity):
            # Truncate long text for readability
            txt = g.text[:300].replace("|", "\\|").replace("\n", " ")
            out.append(f"| {g.severity} | {g.source_agent} | {txt} |")
    return "\n".join(out) + "\n"


def _render_markdown_aggregated(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return "# Context Gaps — aggregated across runs\n\nNo context-gap signals extracted.\n"
    out = ["# Context Gaps — aggregated across all runs\n"]
    out.append(f"**Total unique signals:** {len(entries)}\n")
    out.append(f"**Sorted by:** severity → frequency → category\n\n")
    out.append("| # | Severity | Freq | Categories | Sources | Text |")
    out.append("|---|---|---|---|---|---|")
    for i, e in enumerate(entries, 1):
        txt = e["text"][:280].replace("|", "\\|").replace("\n", " ")
        cats = ", ".join(e["categories"])
        srcs = ", ".join(e["sources"])
        out.append(f"| {i} | {e['severity']} | {e['frequency']} | {cats} | {srcs} | {txt} |")
    return "\n".join(out) + "\n"


def _render_json_single(gaps: list[ContextGap]) -> str:
    return json.dumps(
        [{
            "text": g.text,
            "category": g.category,
            "severity": g.severity,
            "source_agent": g.source_agent,
            "source_field": g.source_field,
            "run_id": g.run_id,
        } for g in gaps],
        indent=2,
        ensure_ascii=False,
    )


def _render_json_aggregated(entries: list[dict[str, Any]]) -> str:
    return json.dumps(entries, indent=2, ensure_ascii=False)


# ---- CLI ----


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run-id", type=str, help="Specific run directory under runs/")
    group.add_argument("--all", action="store_true", help="Aggregate across all runs in runs/")
    parser.add_argument("--format", choices=["md", "json"], default="md", help="Output format")
    parser.add_argument("--out", type=Path, help="Write output to this file (default: stdout)")
    args = parser.parse_args()

    if args.all:
        all_gaps: list[ContextGap] = []
        for run_dir in sorted(RUNS_ROOT.glob("*/")):
            all_gaps.extend(_extract_from_run(run_dir))
        if not all_gaps:
            print("No gaps extracted from any run.", file=sys.stderr)
            return 1
        aggregated = _aggregate(all_gaps)
        output = (
            _render_markdown_aggregated(aggregated)
            if args.format == "md"
            else _render_json_aggregated(aggregated)
        )
        summary = (
            f"Extracted {len(all_gaps)} raw signals across {len({g.run_id for g in all_gaps})} runs; "
            f"deduplicated to {len(aggregated)} unique gaps."
        )
    else:
        run_dir = RUNS_ROOT / args.run_id
        if not run_dir.is_dir():
            print(f"Run not found: {run_dir}", file=sys.stderr)
            return 1
        gaps = _extract_from_run(run_dir)
        output = (
            _render_markdown_single(gaps)
            if args.format == "md"
            else _render_json_single(gaps)
        )
        summary = f"Extracted {len(gaps)} signals from run {args.run_id}."

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output, encoding="utf-8")
        print(f"{summary}\nWrote: {args.out}", file=sys.stderr)
    else:
        print(output)
        print(f"\n--- {summary}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
