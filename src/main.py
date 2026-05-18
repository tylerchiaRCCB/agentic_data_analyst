"""Entry point for the agentic data analyst.

Usage examples:

    # Interactive-style question against a CSV (Question Framer composes pipeline)
    python -m src.main \\
        --question "What patterns are present in this dataset?" \\
        --data path/to/file.csv

    # Proactive monitoring with a scheduled prompt
    python -m src.main \\
        --scheduled \\
        --prompt-config config/prompts/weekly-anomaly-scan.yaml \\
        --data path/to/file.csv

    # Optional: name the domain to load context/domains/<name>.md
    #          (omit for contextless initial testing — the orchestrator surfaces
    #           a high-severity caveat in the recipient output)
    python -m src.main --question "..." --data path.csv --domain commercial-sales

MVP-runnable scope: this orchestrates the Question Framer + downstream agent chain
against a real Anthropic API key. The agent prompts are loaded from agents/<name>.md;
skills from skills/; context (if any) from context/.

Demo data generator is deferred — bring your own CSV.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from src.api.claude_client import ClaudeClient
from src.data_access.excel_loader import load_tabular
from src.observability.run_logger import RunLogger, make_run_id
from src.observability.tracer import Tracer
from src.orchestrator.budget_tracker import BudgetTracker
from src.orchestrator.lineage_tracker import LineageTracker
from src.orchestrator.pipeline_executor import PipelineConfig, PipelineExecutor

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class CLIArgs:
    question: str | None
    scheduled: bool
    prompt_config: Path | None
    data: Path
    domain: str | None
    config_path: Path
    output_dir: Path
    no_upload: bool


def parse_args() -> CLIArgs:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--question", type=str, help="Interactive-style question.")
    p.add_argument(
        "--scheduled",
        action="store_true",
        help="Run in proactive-monitoring mode. Requires --prompt-config.",
    )
    p.add_argument(
        "--prompt-config",
        type=Path,
        help="YAML file with scheduled-prompt configuration. Used with --scheduled.",
    )
    p.add_argument("--data", type=Path, required=True, help="Path to CSV or Excel data file.")
    p.add_argument(
        "--domain",
        type=str,
        default=None,
        help="Name of the functional domain. Resolves to context/domains/<name>.md if it exists. "
        "Omit for contextless runs.",
    )
    p.add_argument(
        "--config",
        type=Path,
        default=Path("config/pipeline_config.yaml"),
        help="Path to pipeline_config.yaml.",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output"),
        help="Where to write the rendered output markdown.",
    )
    p.add_argument(
        "--no-upload",
        action="store_true",
        help="Skip uploading the dataset to Anthropic Files API. Use for prompt-assembly testing.",
    )
    a = p.parse_args()

    if not a.scheduled and not a.question:
        p.error("Either --question or --scheduled (with --prompt-config) must be provided.")
    if a.scheduled and not a.prompt_config:
        p.error("--scheduled requires --prompt-config.")

    return CLIArgs(
        question=a.question,
        scheduled=a.scheduled,
        prompt_config=a.prompt_config,
        data=a.data,
        domain=a.domain,
        config_path=a.config,
        output_dir=a.output_dir,
        no_upload=a.no_upload,
    )


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> int:
    args = parse_args()

    if not os.getenv("ANTHROPIC_API_KEY"):
        logger.error("ANTHROPIC_API_KEY environment variable is required.")
        return 2

    cfg = load_config(args.config_path)
    pipeline_cfg = PipelineConfig(
        model_per_agent=cfg["model_per_agent"],
        max_tokens_per_call=cfg.get("max_tokens_per_call", 8192),
        max_retries_per_stage=cfg.get("max_retries_per_stage", 1),
    )

    run_id = make_run_id()
    run_logger = RunLogger(run_id=run_id)
    tracer = Tracer(run_id=run_id)
    lineage = LineageTracker(run_id=run_id)

    run_logger.info("Pipeline run starting", run_id=run_id, data=str(args.data), domain=args.domain or "(none)")

    # ---- Load data locally for profiling metadata (orchestrator-side summary) ----
    with tracer.span("data_access.load_tabular"):
        dataset = load_tabular(args.data, row_threshold=cfg.get("row_threshold", 5_000_000))

    data_summary = {
        "source_path": str(dataset.source_path),
        "row_count": dataset.row_count,
        "was_sampled": dataset.was_sampled,
        "sample_size": dataset.sample_size,
        "columns": dataset.column_metadata,
        "free_text_columns_sanitized": dataset.free_text_columns_sanitized,
        "sanitization_counts": dataset.sanitization_counts,
        "load_warnings": dataset.load_warnings,
    }

    run_logger.info(
        "Data loaded",
        rows=dataset.row_count,
        columns=len(dataset.column_metadata),
        free_text_cols=len(dataset.free_text_columns_sanitized),
        sampled=dataset.was_sampled,
    )

    client = ClaudeClient()
    budget = BudgetTracker(
        budget_tokens=cfg.get("budget_tokens_default", 1_200_000),
        cost_per_million=cfg.get("cost_per_million", {}),
    )

    # ---- Upload dataset to Anthropic Files API for code execution ----
    dataset_file_id: str | None = None
    if not args.no_upload:
        with tracer.span("data_access.upload_to_anthropic"):
            try:
                dataset_file_id = client.upload_file(args.data)
                run_logger.info("Dataset uploaded to Anthropic Files API", file_id=dataset_file_id)
            except Exception as e:
                run_logger.warning(
                    "Could not upload dataset to Files API; code execution will lack data access",
                    error=str(e),
                )

    # ---- Run pipeline ----
    executor = PipelineExecutor(
        client=client,
        config=pipeline_cfg,
        run_logger=run_logger,
        tracer=tracer,
        budget=budget,
        lineage=lineage,
        domain=args.domain,
    )

    proactive_prompt: str | None = None
    if args.scheduled and args.prompt_config:
        with args.prompt_config.open("r", encoding="utf-8") as f:
            sp = yaml.safe_load(f)
        proactive_prompt = sp.get("prompt", "Weekly anomaly scan.")

    with tracer.span("pipeline.question_framer"):
        framer_payload = executor.invoke_framer(
            user_question=args.question or "",
            proactive_prompt=proactive_prompt,
            data_summary=data_summary,
        )

    run_logger.info(
        "Question Framer composed pipeline",
        complexity=framer_payload.complexity_level,
        stages=len(framer_payload.pipeline_composition),
        budget=framer_payload.token_budget,
    )

    with tracer.span("pipeline.execute"):
        run = executor.execute_pipeline(framer_payload, dataset_file_id=dataset_file_id)

    # ---- Persist outputs ----
    tracer_path = run_logger.write_spans(tracer.to_jsonl())
    lineage_path = run_logger.write_lineage(lineage.manifest())

    # The Communication Agent's rendered markdown is the recipient-facing output.
    final_md_path = args.output_dir / f"{run_id}.md"
    final_md_path.parent.mkdir(parents=True, exist_ok=True)
    comms_artifact = run.artifacts_by_agent.get("communication-agent")
    if comms_artifact:
        rendered = comms_artifact["payload"].get("rendered_output_markdown", "")
        final_md_path.write_text(rendered, encoding="utf-8")
        run_logger.info("Final output written", path=str(final_md_path))
    else:
        run_logger.warning("No Communication Agent artifact found; final output not written.")

    # ---- Summary ----
    run_logger.info(
        "Pipeline complete",
        status=run.status,
        stages_completed=len(run.stage_results),
        total_tokens=budget.total_tokens(),
        total_cost_usd=round(budget.total_cost(), 4),
        run_dir=str(run_logger.run_dir),
        spans=str(tracer_path),
        lineage=str(lineage_path),
    )

    return 0 if run.status != "failed" else 1


if __name__ == "__main__":
    sys.exit(main())
