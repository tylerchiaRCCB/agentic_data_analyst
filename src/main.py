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
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from src.api.claude_client import ClaudeClient

# Load environment variables from .env in the repo root (if present).
# Real shell env vars take precedence over .env values.
load_dotenv()
from src.data_access.excel_loader import load_tabular
from src.observability.run_logger import RunLogger, make_run_id
from src.observability.tracer import Tracer
from src.orchestrator.budget_tracker import BudgetTracker
from src.orchestrator.lineage_tracker import LineageTracker
from src.orchestrator.pipeline_executor import PipelineConfig, PipelineExecutor

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger(__name__)

# Suppress verbose Azure SDK HTTP logging
for _azure_logger_name in ("azure", "azure.identity", "azure.core.pipeline.policies.http_logging_policy"):
    logging.getLogger(_azure_logger_name).setLevel(logging.WARNING)

_DELIVERY_COVERAGE_WARNING_PREFIX = "DELIVERY_COVERAGE_LOW"


@dataclass
class CLIArgs:
    question: str | None
    scheduled: bool
    prompt_config: Path | None
    data: Path | None
    source: str  # "file" or "cortex_analyst"
    semantic_view: str | None
    backend: str  # "anthropic" or "foundry"
    domain: str | None
    config_path: Path
    output_dir: Path
    no_upload: bool
    dry_run: bool
    prior_run_id: str | None
    use_latest_run_context: bool
    rerun_communication_from_run: str | None


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
    p.add_argument("--data", type=Path, default=None, help="Path to CSV or Excel data file.")
    p.add_argument(
        "--source",
        type=str,
        choices=["file", "cortex_analyst"],
        default="file",
        help="Data source type. 'file' uses --data CSV/Excel. 'cortex_analyst' uses Snowflake Cortex Analyst.",
    )
    p.add_argument(
        "--semantic-view",
        type=str,
        default=None,
        help="Fully-qualified Snowflake semantic view (e.g. DB.SCHEMA.VIEW). Required when --source=cortex_analyst.",
    )
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
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Verify plumbing without spending API tokens. Loads data, sanitizes free-text, "
        "assembles prompts for every agent, validates schemas, writes a dry-run report. "
        "No Anthropic API calls are made.",
    )
    p.add_argument(
        "--backend",
        type=str,
        choices=["anthropic", "foundry", "foundry-dev", "foundry-sonnet5", "azure-openai"],
        default="foundry-dev",
        help="LLM backend. 'anthropic' uses direct Anthropic API (chris-anderson-anthropic key). "
        "'foundry' uses Azure AI Foundry Anthropic models (raghu-anthropic key, data stays in Azure). "
        "'foundry-dev' uses Azure AI Foundry dev environment (raghu-anthropic-dev key). "
        "'foundry-sonnet5' uses Azure AI Foundry claude-sonnet-5 (raghu-sonnet-dev key). "
        "'azure-openai' uses Azure OpenAI (raghu-openai key, GPT models via LiteLLM).",
    )
    p.add_argument(
        "--prior-run-id",
        type=str,
        default=None,
        help="Prior run ID to load as context (e.g., 20260618T141448Z-483d87f3).",
    )
    p.add_argument(
        "--use-latest-run-context",
        action="store_true",
        help="Auto-load the latest completed run from runs/ as context.",
    )
    p.add_argument(
        "--rerun-communication-from-run",
        type=str,
        default=None,
        help="Run only the communication-agent using upstream artifacts from the given run ID.",
    )
    a = p.parse_args()

    rerun_mode = bool(a.rerun_communication_from_run)
    if rerun_mode:
        if a.question or a.scheduled:
            p.error("--rerun-communication-from-run cannot be combined with --question or --scheduled.")
        if a.prompt_config:
            p.error("--rerun-communication-from-run cannot be combined with --prompt-config.")
        if a.data:
            p.error("--rerun-communication-from-run does not accept --data.")
        if a.semantic_view:
            p.error("--rerun-communication-from-run does not accept --semantic-view.")
        if a.source != "file":
            p.error("--rerun-communication-from-run must use default --source=file.")
    else:
        if not a.scheduled and not a.question:
            p.error("Either --question or --scheduled (with --prompt-config) must be provided.")
        if a.scheduled and not a.prompt_config:
            p.error("--scheduled requires --prompt-config.")
        if a.source == "cortex_analyst" and not a.semantic_view and not a.domain:
            p.error("--source=cortex_analyst requires --semantic-view or --domain.")
        if a.source == "file" and not a.data:
            p.error("--source=file requires --data.")
    if a.prior_run_id and a.use_latest_run_context:
        p.error("Use either --prior-run-id or --use-latest-run-context, not both.")

    return CLIArgs(
        question=a.question,
        scheduled=a.scheduled,
        prompt_config=a.prompt_config,
        data=a.data,
        source=a.source,
        semantic_view=a.semantic_view,
        backend=getattr(a, 'backend', 'foundry-dev'),
        domain=a.domain,
        config_path=a.config,
        output_dir=a.output_dir,
        no_upload=a.no_upload,
        dry_run=a.dry_run,
        prior_run_id=a.prior_run_id,
        use_latest_run_context=a.use_latest_run_context,
        rerun_communication_from_run=a.rerun_communication_from_run,
    )


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _truncate_text(text: str, max_chars: int = 8_000) -> str:
    """Bound long fields so per-run JSONL logs remain compact."""
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}... [truncated {len(text) - max_chars} chars]"


def _sanitize_rendered_markdown(text: str) -> str:
    """Normalize punctuation/spacing that commonly breaks markdown rendering."""
    if not text:
        return text

    # Remove zero-width and BOM-like characters that can split words visually.
    text = re.sub(r"[\u200B-\u200F\u2060\uFEFF]", "", text)

    # Normalize spacing variants.
    text = text.replace("\u00A0", " ").replace("\u202F", " ")

    # Normalize punctuation that often renders inconsistently across viewers.
    replacements = {
        "\u2012": "-",  # figure dash
        "\u2013": "-",  # en dash
        "\u2014": "-",  # em dash
        "\u2015": "-",  # horizontal bar
        "\u2212": "-",  # minus sign
        "\u2018": "'",  # left single quote
        "\u2019": "'",  # right single quote
        "\u201C": '"',  # left double quote
        "\u201D": '"',  # right double quote
        "\u2217": "*",  # asterisk operator
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)

    # Ensure unicode-asterisk bold markers become regular markdown bold markers.
    text = re.sub(r"\*\*+", "**", text)

    # Fix nested bold wrappers like:
    #   > **... **value** ...**
    # Many markdown renderers mis-handle this and produce corrupted text.
    # Keep inner emphasis, drop the outer wrapper when nesting is detected.
    normalized_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("> **") and stripped.endswith("**") and stripped.count("**") > 2:
            # Remove outer "> **" and trailing "**"; preserve any inner bold spans.
            body = stripped[4:-2].strip()
            line = re.sub(r"^\s*>\s*\*\*.*?\*\*\s*$", f"> {body}", line)
        elif stripped.startswith("**") and stripped.endswith("**") and stripped.count("**") > 2:
            # Same normalization for non-blockquote lines.
            line = line.replace("**", "", 1)
            line = line[::-1].replace("**"[::-1], "", 1)[::-1]
        normalized_lines.append(line)
    text = "\n".join(normalized_lines)

    # Escape currency '$' outside fenced code blocks so markdown renderers that
    # support math don't consume spans like "$2.61 to $4.87" as inline math.
    escaped_lines: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            escaped_lines.append(line)
            continue
        if in_fence:
            escaped_lines.append(line)
            continue
        line = re.sub(r"(?<!\\)\$(?=\d)", r"\\$", line)
        escaped_lines.append(line)
    text = "\n".join(escaped_lines)

    # Normalize unicode asterisk to ASCII outside code fences and collapse
    # malformed long star runs that can break emphasis rendering.
    final_lines: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            final_lines.append(line)
            continue
        if in_fence:
            final_lines.append(line)
            continue
        line = line.replace("∗", "*")
        line = re.sub(r"\*{3,}", "**", line)
        final_lines.append(line)
    text = "\n".join(final_lines)
    return text


def _resolve_latest_run_id(runs_root: Path) -> str | None:
    """Return the latest run directory id that contains run.jsonl."""
    if not runs_root.exists():
        return None
    candidates: list[str] = []
    for p in runs_root.iterdir():
        if not p.is_dir():
            continue
        if (p / "run.jsonl").exists():
            candidates.append(p.name)
    if not candidates:
        return None
    return sorted(candidates)[-1]


def _topic_slug(*, question: str | None, proactive_prompt: str | None, domain: str | None) -> str:
    """Build a short, filesystem-safe domain slug for output filenames."""
    # Naming policy: timestamp + domain slug.
    # Question/prompt text are intentionally ignored for output filenames.
    source = (domain or "analysis").strip().lower()
    source = re.sub(r"[^a-z0-9]+", "-", source).strip("-")
    if not source:
        return "analysis"
    return source


def _build_output_stem(*, run_id: str, question: str | None, proactive_prompt: str | None, domain: str | None) -> str:
    """Return filename stem: <timestamp>-<domain>."""
    # run_id format: YYYYMMDDTHHMMSSZ-xxxxxxxx
    timestamp = run_id.split("-", 1)[0]
    slug = _topic_slug(question=question, proactive_prompt=proactive_prompt, domain=domain)
    return f"{timestamp}-{slug}"


def _load_previous_run_context(
    *,
    run_id: str,
    runs_root: Path = Path("runs"),
    output_dir: Path = Path("output"),
    max_markdown_chars: int = 12_000,
) -> dict[str, Any] | None:
    """Load bounded prior-run context for recurring weekly analysis continuity."""
    run_dir = runs_root / run_id
    if not run_dir.exists():
        return None

    context: dict[str, Any] = {"run_id": run_id}

    # 1) Previous recipient-facing markdown (preferred, if present)
    md_candidates = [
        output_dir / f"{run_id}.md",
        output_dir / f"{run_id}-pending-review.md",
    ]
    for md in md_candidates:
        if md.exists():
            context["output_markdown_preview"] = _truncate_text(
                md.read_text(encoding="utf-8"),
                max_chars=max_markdown_chars,
            )
            context["output_markdown_path"] = str(md)
            break

    # 2) Communication-agent payload (structured summary fallback)
    comm_candidates = sorted((run_dir / "artifacts").glob("*-communication-agent*.json"))
    if comm_candidates:
        with comm_candidates[-1].open("r", encoding="utf-8") as f:
            comm = json.load(f)
        payload = comm.get("payload", {})
        context["communication_payload_summary"] = {
            "output_mode": payload.get("output_mode"),
            "action_card_count": len(payload.get("action_cards", [])) if isinstance(payload.get("action_cards", []), list) else None,
            "rendered_output_markdown_preview": _truncate_text(
                payload.get("rendered_output_markdown", ""),
                max_chars=max_markdown_chars,
            ),
        }

    # 3) Pull the prior submitted prompt/question from run.jsonl when available
    run_jsonl = run_dir / "run.jsonl"
    if run_jsonl.exists():
        with run_jsonl.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("msg", "").startswith("Prompt submitted"):
                    attrs = event.get("attrs", {})
                    if isinstance(attrs, dict):
                        context["previous_prompt"] = {
                            "mode": attrs.get("mode"),
                            "question": attrs.get("question"),
                            "proactive_prompt": attrs.get("proactive_prompt"),
                        }
                    break

    return context


def _load_run_metadata(*, run_id: str, runs_root: Path = Path("runs")) -> dict[str, Any]:
    """Load key metadata from a prior run (question/domain/backend/file id)."""
    run_jsonl = runs_root / run_id / "run.jsonl"
    if not run_jsonl.exists():
        return {}

    metadata: dict[str, Any] = {}
    with run_jsonl.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = event.get("msg", "")
            attrs = event.get("attrs", {})
            if not isinstance(attrs, dict):
                continue

            if msg.startswith("Prompt submitted"):
                metadata["question"] = attrs.get("question")
                metadata["proactive_prompt"] = attrs.get("proactive_prompt")
            elif msg.startswith("Pipeline run starting"):
                domain = attrs.get("domain")
                metadata["domain"] = None if domain in (None, "(none)") else domain
            elif msg.startswith("Dataset uploaded to Anthropic Files API"):
                metadata["dataset_file_id"] = attrs.get("file_id")
    return metadata


def _load_upstream_artifacts_for_communication(
    *,
    run_id: str,
    runs_root: Path = Path("runs"),
    max_stage_index: int = 5,
) -> dict[str, dict[str, Any]]:
    """Load prior stage artifacts required to re-run communication-agent only."""
    artifacts_dir = runs_root / run_id / "artifacts"
    if not artifacts_dir.exists():
        raise FileNotFoundError(f"Artifacts directory not found for run_id={run_id}: {artifacts_dir}")

    upstream: dict[str, dict[str, Any]] = {}
    for path in sorted(artifacts_dir.glob("*.json")):
        stem = path.stem
        if "-" not in stem:
            continue
        index_text, agent_name = stem.split("-", 1)
        if not index_text.isdigit():
            continue
        if int(index_text) > max_stage_index:
            continue

        with path.open("r", encoding="utf-8") as f:
            artifact = json.load(f)
        if isinstance(artifact, dict) and "payload" in artifact:
            upstream[agent_name] = artifact

    if not upstream:
        raise ValueError(f"No upstream artifacts found for run_id={run_id} up to stage {max_stage_index}.")
    return upstream


def _delivery_coverage_gate_warning(warnings: list[str] | None) -> str | None:
    """Return delivery coverage gate warning, if emitted by Cortex client."""
    if not warnings:
        return None
    for warning in warnings:
        if isinstance(warning, str) and warning.startswith(_DELIVERY_COVERAGE_WARNING_PREFIX):
            return warning
    return None


def main() -> int:
    args = parse_args()

    # ---- Azure Key Vault: load LLM API key ----
    _FOUNDRY_BASE_URL = "https://rk-sb-project-0-1-resource.services.ai.azure.com/anthropic"
    _FOUNDRY_DEV_BASE_URL = "https://raghu-mpzq4rc5-eastus2.services.ai.azure.com/anthropic"
    _AZURE_OPENAI_BASE_URL = "https://rk-sb-project-0-1-resource.openai.azure.com"
    _AZURE_OPENAI_API_VERSION = "2025-04-01-preview"
    # Map Claude model names → Azure OpenAI deployment names.
    # Update deployment values if your resource uses different names.
    _AZURE_OPENAI_MODEL_MAP: dict[str, str] = {
        "claude-sonnet-4-6": "azure/gpt-4.1",
        "claude-opus-4-7": "azure/gpt-4.1",
    }
    _VAULT_URL = "https://glccbdsdevkv.vault.azure.net/"
    _KEY_NAMES = {
        "anthropic": "chris-anderson-anthropic",
        "foundry": "raghu-anthropic",
        "foundry-dev": "raghu-anthropic-dev",
        "foundry-sonnet5": "raghu-sonnet-dev",
        "azure-openai": "raghu-openai",
    }

    llm_api_key: str | None = os.getenv("ANTHROPIC_API_KEY")
    if not args.dry_run and not llm_api_key:
        try:
            from azure.identity import AzureCliCredential, DefaultAzureCredential
            from azure.keyvault.secrets import SecretClient

            secret_name = _KEY_NAMES[args.backend]
            try:
                credential = DefaultAzureCredential()
                kv_client = SecretClient(vault_url=_VAULT_URL, credential=credential)
                secret = kv_client.get_secret(secret_name)
                cred_name = "DefaultAzureCredential"
            except Exception:
                credential = AzureCliCredential()
                kv_client = SecretClient(vault_url=_VAULT_URL, credential=credential)
                secret = kv_client.get_secret(secret_name)
                cred_name = "AzureCliCredential"
            llm_api_key = secret.value
            logger.info(f"Loaded {secret_name} from Azure Key Vault ({cred_name}) for backend={args.backend}")
        except Exception as e:
            logger.error(f"Failed to load API key from Azure Key Vault: {e}")

    if not args.dry_run and not llm_api_key:
        logger.error("API key is required (unless --dry-run). Check Key Vault or set ANTHROPIC_API_KEY.")
        return 2

    if args.dry_run:
        return _dry_run(args)

    cfg = load_config(args.config_path)

    # For azure-openai, remap model names and set LiteLLM env vars.
    if args.backend == "azure-openai":
        os.environ["AZURE_API_KEY"] = llm_api_key
        os.environ["AZURE_API_BASE"] = _AZURE_OPENAI_BASE_URL
        os.environ["AZURE_API_VERSION"] = _AZURE_OPENAI_API_VERSION
        model_map = cfg["model_per_agent"]
        for agent_name in model_map:
            original = model_map[agent_name]
            if original in _AZURE_OPENAI_MODEL_MAP:
                model_map[agent_name] = _AZURE_OPENAI_MODEL_MAP[original]
                logger.info("Azure OpenAI model remap: %s → %s (agent: %s)", original, model_map[agent_name], agent_name)

    # For foundry-sonnet5, remap all agents to claude-sonnet-5.
    if args.backend == "foundry-sonnet5":
        model_map = cfg["model_per_agent"]
        for agent_name in model_map:
            original = model_map[agent_name]
            if original != "claude-sonnet-5":
                model_map[agent_name] = "claude-sonnet-5"
                logger.info("Sonnet 5 model remap: %s → claude-sonnet-5 (agent: %s)", original, agent_name)

    pipeline_cfg = PipelineConfig(
        model_per_agent=cfg["model_per_agent"],
        max_tokens_per_call=cfg.get("max_tokens_per_call", 8192),
        max_retries_per_stage=cfg.get("max_retries_per_stage", 1),
    )

    run_id = make_run_id()
    run_logger = RunLogger(run_id=run_id)
    tracer = Tracer(run_id=run_id)
    lineage = LineageTracker(run_id=run_id)

    prior_run_id = args.prior_run_id
    if args.use_latest_run_context and not prior_run_id:
        prior_run_id = _resolve_latest_run_id(Path("runs"))

    previous_run_context: dict[str, Any] | None = None
    if prior_run_id:
        if prior_run_id == run_id:
            run_logger.warning("Skipping prior run context because run_id matches current run", run_id=run_id)
        else:
            previous_run_context = _load_previous_run_context(
                run_id=prior_run_id,
                runs_root=Path("runs"),
                output_dir=args.output_dir,
            )
            if previous_run_context:
                run_logger.info(
                    "Loaded prior run context",
                    prior_run_id=prior_run_id,
                    context_keys=sorted(previous_run_context.keys()),
                )
            else:
                run_logger.warning(
                    "Requested prior run context not found; continuing without it",
                    prior_run_id=prior_run_id,
                )

    if args.backend == "azure-openai":
        from src.api.litellm_client import LiteLLMClient

        client = LiteLLMClient(api_key=llm_api_key)  # type: ignore[assignment]
        logger.info("Using Azure OpenAI backend via LiteLLM: %s", _AZURE_OPENAI_BASE_URL)
    else:
        _foundry_urls = {
            "foundry": _FOUNDRY_BASE_URL,
            "foundry-dev": _FOUNDRY_DEV_BASE_URL,
            "foundry-sonnet5": _FOUNDRY_DEV_BASE_URL,
        }
        client = ClaudeClient(
            api_key=llm_api_key,
            backend=args.backend if args.backend not in ("foundry-dev", "foundry-sonnet5") else "foundry",
            base_url=_foundry_urls.get(args.backend),
        )

    budget = BudgetTracker(
        budget_tokens=cfg.get("budget_tokens_default", 1_200_000),
        cost_per_million=cfg.get("cost_per_million", {}),
        max_cost_usd=cfg.get("max_cost_usd"),
        cost_warning_thresholds=cfg.get("cost_warning_thresholds", [0.5, 0.75, 0.9]),
    )

    if args.rerun_communication_from_run:
        source_run_id = args.rerun_communication_from_run
        source_metadata = _load_run_metadata(run_id=source_run_id, runs_root=Path("runs"))
        effective_domain = args.domain or source_metadata.get("domain")
        run_logger.info(
            "Communication-agent-only rerun starting",
            run_id=run_id,
            source_run_id=source_run_id,
            domain=effective_domain or "(none)",
            backend=args.backend,
        )

        try:
            upstream_artifacts = _load_upstream_artifacts_for_communication(
                run_id=source_run_id,
                runs_root=Path("runs"),
            )
        except Exception as e:
            run_logger.error("Could not load upstream artifacts for communication rerun", error=str(e))
            return 1

        executor = PipelineExecutor(
            client=client,
            config=pipeline_cfg,
            run_logger=run_logger,
            tracer=tracer,
            budget=budget,
            lineage=lineage,
            domain=effective_domain,
            previous_run_context=previous_run_context,
        )

        with tracer.span("pipeline.communication_only"):
            stage_result = executor.rerun_communication_agent(
                upstream_artifacts=upstream_artifacts,
                dataset_file_id=None,
            )

        if stage_result.status != "ok":
            run_logger.error(
                "Communication-agent-only rerun failed",
                source_run_id=source_run_id,
                error=stage_result.error or "unknown error",
            )
            return 1

        payload = stage_result.artifact.get("payload", {})
        if not isinstance(payload, dict):
            run_logger.error("Communication rerun produced invalid payload type")
            return 1

        lineage.add_artifact_statistics(
            agent="communication-agent",
            stage_index=stage_result.stage_index,
            payload=payload,
        )

        args.output_dir.mkdir(parents=True, exist_ok=True)
        rendered = _sanitize_rendered_markdown(str(payload.get("rendered_output_markdown", "")))
        if not rendered.strip():
            run_logger.error("Communication rerun returned empty rendered_output_markdown")
            return 1

        from datetime import datetime, timezone
        question_text = (
            source_metadata.get("question")
            or source_metadata.get("proactive_prompt")
            or "(communication-only rerun)"
        )
        run_date = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        metadata_header = (
            f"> **Run date:** {run_date}  \n"
            f"> **Question:** {question_text}  \n"
            f"> **Run ID:** `{run_id}` | **Backend:** `{args.backend}` | "
            f"**Domain:** `{effective_domain or '(none)'}` | "
            f"**Mode:** `communication-only rerun` | "
            f"**Source run:** `{source_run_id}`\n\n"
        )
        rendered = _sanitize_rendered_markdown(metadata_header + rendered)

        from src.orchestrator.hitl_gate import build_review_prompt, evaluate as hitl_evaluate

        decision = hitl_evaluate(
            run_id=run_id,
            output_dir=args.output_dir,
            comms_payload=payload,
            threshold=cfg.get("hitl_review_threshold"),
            output_stem=_build_output_stem(
                run_id=run_id,
                question=None,
                proactive_prompt=None,
                domain=effective_domain,
            ),
        )
        decision.final_md_path.write_text(rendered, encoding="utf-8")
        if decision.gated and decision.review_prompt_path is not None:
            decision.review_prompt_path.write_text(
                build_review_prompt(run_id=run_id, decision=decision),
                encoding="utf-8",
            )
            run_logger.warning(
                "HITL gate triggered for communication-only rerun",
                threshold=decision.threshold,
                findings_for_review=len(decision.findings_triggering_review),
                pending_path=str(decision.final_md_path),
                review_prompt=str(decision.review_prompt_path),
            )
        else:
            run_logger.info("Communication-only output written", path=str(decision.final_md_path))

        tracer_path = run_logger.write_spans(tracer.to_jsonl())
        lineage_path = run_logger.write_lineage(lineage.manifest())
        run_logger.info(
            "Communication-only rerun complete",
            status="ok",
            source_run_id=source_run_id,
            total_tokens=budget.total_tokens(),
            total_cost_usd=round(budget.total_cost(), 4),
            run_dir=str(run_logger.run_dir),
            spans=str(tracer_path),
            lineage=str(lineage_path),
            output_path=str(decision.final_md_path),
        )
        return 0

    run_logger.info("Pipeline run starting", run_id=run_id, data=str(args.data or args.semantic_view), domain=args.domain or "(none)")

    # ---- Acquire data: file-based or Cortex Analyst ----
    if args.source == "cortex_analyst":
        # NL-to-SQL via Snowflake Cortex Analyst → DataFrame → temp CSV for pipeline
        from src.data_access.cortex_analyst_client import CortexAnalystClient
        from src.data_access.snowflake_client import SnowflakeClient, SnowflakeConfig
        import tempfile

        with tracer.span("data_access.cortex_analyst"):
            try:
                sf_config = SnowflakeConfig.from_env()
                logger.info("Loaded Snowflake config from environment variables")
            except Exception:
                sf_config = SnowflakeConfig.from_team_keyvault()
                logger.info("Loaded Snowflake config from Azure Key Vault")
            sf_client = SnowflakeClient(sf_config)
            cortex = CortexAnalystClient(snowflake=sf_client)

            # Derive semantic_model name from domain (e.g. "walmart-opd")
            semantic_model_name = args.domain or "default"
            response = cortex.ask(
                question=args.question or "",
                semantic_model=semantic_model_name,
                semantic_view=args.semantic_view,
            )
            lineage.add_statistic(
                agent="cortex-analyst",
                stage_index=0,
                statistic={
                    "action": "nl_to_sql",
                    "generated_sql": response.generated_sql,
                    "request_id": response.request_id,
                    "rows_returned": response.rows_returned,
                    "warnings": response.warnings,
                    "semantic_view": args.semantic_view,
                },
            )
            run_logger.info(
                "Cortex Analyst returned data",
                rows=response.rows_returned,
                columns=len(response.dataframe.columns) if not response.dataframe.empty else 0,
                sql_chars=len(response.generated_sql),
                request_id=response.request_id,
            )
            run_logger.info(
                "Cortex SQL generated",
                request_id=response.request_id,
                semantic_model=semantic_model_name,
                semantic_view=args.semantic_view or "",
                sql=_truncate_text(response.generated_sql),
            )

            gate_warning = _delivery_coverage_gate_warning(response.warnings)
            if gate_warning:
                run_logger.warning(
                    "Delivery coverage low — proceeding with caveat; delivery analysis will be flagged as unreliable",
                    warning=gate_warning,
                    request_id=response.request_id,
                )

        if response.dataframe.empty:
            run_logger.error("Cortex Analyst returned no data. Cannot proceed.")
            return 3

        # Write to temp CSV so the rest of the pipeline (upload, profiling) works unchanged
        tmp_csv = Path(tempfile.mktemp(suffix=".csv", prefix="cortex_"))
        response.dataframe.to_csv(tmp_csv, index=False)
        data_path = tmp_csv
    else:
        data_path = args.data

    # ---- Load data locally for profiling metadata (orchestrator-side summary) ----
    with tracer.span("data_access.load_tabular"):
        dataset = load_tabular(data_path, row_threshold=cfg.get("row_threshold", 5_000_000))

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

    # ---- Upload dataset to Anthropic Files API for code execution ----
    dataset_file_id: str | None = None
    if not args.no_upload:
        with tracer.span("data_access.upload_to_anthropic"):
            try:
                dataset_file_id = client.upload_file(data_path)
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
        previous_run_context=previous_run_context,
    )

    proactive_prompt: str | None = None
    if args.scheduled and args.prompt_config:
        with args.prompt_config.open("r", encoding="utf-8") as f:
            sp = yaml.safe_load(f)
        proactive_prompt = sp.get("prompt", "Weekly anomaly scan.")

    run_logger.info(
        "Prompt submitted",
        mode="scheduled" if args.scheduled else "interactive",
        question=args.question or "",
        proactive_prompt=proactive_prompt or "",
        prompt_config=str(args.prompt_config) if args.prompt_config else "",
    )

    with tracer.span("pipeline.question_framer"):
        framer_payload = executor.invoke_framer(
            user_question=args.question or "",
            proactive_prompt=proactive_prompt,
            data_summary=data_summary,
            previous_run_context=previous_run_context,
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
    # If a HITL threshold is configured, evaluate whether to gate the output for
    # human review before it gets delivered.
    args.output_dir.mkdir(parents=True, exist_ok=True)
    comms_artifact = run.artifacts_by_agent.get("communication-agent")
    if comms_artifact:
        from src.orchestrator.hitl_gate import build_review_prompt, evaluate as hitl_evaluate

        payload = comms_artifact["payload"]
        rendered = payload.get("rendered_output_markdown", "")

        # Prepend run metadata (date, question, run ID) to the output
        from datetime import datetime, timezone
        run_date = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        question_text = args.question or proactive_prompt or "(scheduled)"
        metadata_header = (
            f"> **Run date:** {run_date}  \n"
            f"> **Question:** {question_text}  \n"
            f"> **Run ID:** `{run_id}` | **Backend:** `{args.backend}` | "
            f"**Domain:** `{args.domain or '(none)'}`\n\n"
        )
        rendered = _sanitize_rendered_markdown(metadata_header + str(rendered))

        decision = hitl_evaluate(
            run_id=run_id,
            output_dir=args.output_dir,
            comms_payload=payload,
            threshold=cfg.get("hitl_review_threshold"),
            output_stem=_build_output_stem(
                run_id=run_id,
                question=args.question,
                proactive_prompt=proactive_prompt,
                domain=args.domain,
            ),
        )
        decision.final_md_path.write_text(rendered, encoding="utf-8")
        if decision.gated and decision.review_prompt_path is not None:
            decision.review_prompt_path.write_text(
                build_review_prompt(run_id=run_id, decision=decision), encoding="utf-8"
            )
            run_logger.warning(
                "HITL gate triggered — output held for human review",
                threshold=decision.threshold,
                findings_for_review=len(decision.findings_triggering_review),
                pending_path=str(decision.final_md_path),
                review_prompt=str(decision.review_prompt_path),
            )
        else:
            run_logger.info("Final output written", path=str(decision.final_md_path))
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


# ---------------------------------------------------------------------------
# Dry-run mode — plumbing verification without API calls
# ---------------------------------------------------------------------------

# A "representative" skill loadout per agent — what would typically be loaded
# during a full proactive-monitoring run. The Question Framer chooses skills
# dynamically in real runs; this map is for dry-run prompt-size estimation.
_DRY_RUN_AGENT_SKILLS: dict[str, list[str]] = {
    # Universal skills (analysis-design-spec, statistical-rigor, etc.) load
    # automatically — only the on-demand skills appear in these per-stage lists.
    "question-framer": ["hypothesis-generation-from-data"],
    "data-retrieval-agent": [],
    "data-profiler": ["outlier-typology"],
    "relationship-analyzer": [
        "correlation-analysis",
        "group-comparison",
        "hypothesis-testing",
        "effect-size-calculation",
    ],
    "pattern-discoverer": [
        "clustering-algorithms",
        "outlier-typology",
        "hypothesis-generation-from-data",
    ],
    "time-series-analyzer": ["stl-decomposition", "change-point-detection", "cohort-analysis"],
    "root-cause-investigator": [
        "hypothesis-testing",
        "effect-size-calculation",
        "simpsons-paradox-check",
    ],
    "opportunity-identifier": [
        "benchmarking-methods",
        "performance-gap-analysis",
        "predictive-readiness-assessment",
        "guardrail-metric-pairing",
    ],
    "findings-validator": [
        "statistical-revalidation",
        "guardrail-pairing-check",
        "hypothesis-testing",
        "simpsons-paradox-check",
    ],
    "communication-agent": [
        "proactive-action-card",
        "descriptive-summary-format",
        "insight-first-formatting",
        "confidence-language",
        "stakeholder-communication",
        "visualization-recommendations",
    ],
}


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~1.3 tokens per word. Good enough for plumbing checks."""
    return int(len(text.split()) * 1.3)


def _dry_run(args: CLIArgs) -> int:
    from src.orchestrator.prompt_assembler import assemble_prompt
    from src.orchestrator.schemas import (
        CommunicationAgentPayload,
        FindingsValidatorPayload,
        OpportunityIdentifierPayload,
        validate_payload,
    )

    print("=" * 72)
    print("[DRY-RUN] Plumbing verification — no Anthropic API calls will be made.")
    print("=" * 72)

    # ---------- 1. Load data ----------
    print("\n[1/5] Loading data...")
    try:
        cfg = load_config(args.config_path)
        if args.source == "cortex_analyst":
            import tempfile
            from src.data_access.cortex_analyst_client import CortexAnalystClient
            from src.data_access.snowflake_client import SnowflakeClient, SnowflakeConfig

            try:
                sf_config = SnowflakeConfig.from_env()
            except Exception:
                sf_config = SnowflakeConfig.from_team_keyvault()
            sf_client = SnowflakeClient(sf_config)
            cortex = CortexAnalystClient(snowflake=sf_client)
            semantic_model_name = args.domain or "default"
            response = cortex.ask(
                question=args.question or "",
                semantic_model=semantic_model_name,
                semantic_view=args.semantic_view,
            )
            print(f"  Cortex Analyst SQL ({response.rows_returned} rows):")
            print(f"    {response.generated_sql[:200]}...")
            if response.dataframe.empty:
                print("  FAIL: Cortex Analyst returned no data.")
                return 1
            tmp_csv = Path(tempfile.mktemp(suffix=".csv", prefix="cortex_"))
            response.dataframe.to_csv(tmp_csv, index=False)
            data_path = tmp_csv
        else:
            data_path = args.data
        dataset = load_tabular(data_path, row_threshold=cfg.get("row_threshold", 5_000_000))
    except Exception as e:
        print(f"  FAIL: {type(e).__name__}: {e}")
        return 1
    print(f"  source:                 {dataset.source_path.name}")
    print(f"  rows:                   {dataset.row_count}")
    print(f"  columns:                {len(dataset.column_metadata)}")
    print(f"  free-text columns:      {dataset.free_text_columns_sanitized}")
    print(f"  sanitized cells:        {sum(dataset.sanitization_counts.values())}")
    print(f"  was_sampled:            {dataset.was_sampled}")
    print(f"  load_warnings:          {len(dataset.load_warnings)}")
    for w in dataset.load_warnings:
        print(f"    - [{w['severity']}] {w['text'][:80]}...")

    # ---------- 2. Config ----------
    print("\n[2/5] Loading pipeline config...")
    print(f"  config_path:            {args.config_path}")
    print(f"  models per agent:")
    for agent, model in cfg["model_per_agent"].items():
        print(f"    {agent:25} -> {model}")

    # ---------- 3. Prompt assembly for each agent ----------
    print("\n[3/5] Assembling system prompts for each agent...")
    print(f"  domain:                 {args.domain or '(none — contextless run)'}")
    total_prompt_tokens = 0
    from src.orchestrator.prompt_assembler import DEFAULT_SKILLS_BY_AGENT
    missing_context_flagged = False
    for agent, _legacy_skills in _DRY_RUN_AGENT_SKILLS.items():
        try:
            # `skills` arg is ignored at runtime; canonical skills come from
            # DEFAULT_SKILLS_BY_AGENT. The dry-run report shows the canonical
            # count so it matches what an actual run would load.
            prompt = assemble_prompt(agent_name=agent, domain=args.domain)
        except FileNotFoundError as e:
            print(f"  FAIL on {agent}: {e}")
            return 1
        tokens = _estimate_tokens(prompt.system_prompt)
        total_prompt_tokens += tokens
        flag = " (missing domain context)" if prompt.missing_domain_context else ""
        canonical_count = len(DEFAULT_SKILLS_BY_AGENT.get(agent, []))
        print(
            f"  {agent:25} skills:{canonical_count:2}  files:{len(prompt.sections_loaded):2}  ~{tokens:5} tokens{flag}"
        )
        if prompt.missing_domain_context:
            missing_context_flagged = True
    print(f"  total estimated prompt tokens (all 10 agents): ~{total_prompt_tokens:,}")
    if missing_context_flagged:
        print(
            "  [INFO] Missing domain context is expected for contextless runs. "
            "The orchestrator will surface a high-severity caveat in the recipient output."
        )

    # ---------- 4. Schema dispatch test ----------
    print("\n[4/5] Schema dispatch test (empty-arrays-valid invariants)...")
    schema_tests = [
        (
            "findings-validator",
            {
                "overall_assessment": "x",
                "findings_review": [],
                "cross_cutting_issues": [],
                "guardrail_check_results": [],
                "revalidation_summary": {"findings_recomputed": 0, "discrepancies_found": 0},
            },
            FindingsValidatorPayload,
        ),
        (
            "communication-agent",
            {
                "output_mode": "descriptive-summary",
                "rendered_output_markdown": "## Quiet week",
                "action_cards": [],
                "descriptive_summary": {"conclusion": "All clear."},
            },
            CommunicationAgentPayload,
        ),
        (
            "opportunity-identifier",
            {
                "performance_gaps": [],
                "opportunity_areas": [],
                "intervention_recommendations": [],
                "predictive_readiness_assessment": {"candidates": []},
                "sensitivity_analysis": [],
            },
            OpportunityIdentifierPayload,
        ),
    ]
    for name, raw, expected_cls in schema_tests:
        try:
            result = validate_payload(name, raw)
            ok = isinstance(result, expected_cls)
            print(f"  {name:30} {'OK' if ok else 'FAIL — wrong dispatch class'}")
        except Exception as e:
            print(f"  {name:30} FAIL: {type(e).__name__}: {e}")
            return 1

    # ---------- 5. Write dry-run report ----------
    print("\n[5/5] Writing dry-run report...")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.output_dir / f"dry-run-{make_run_id()}.md"
    report_lines = [
        f"# Dry-run report — {report_path.stem}",
        "",
        f"- Data file: `{dataset.source_path}`",
        f"- Rows: {dataset.row_count}",
        f"- Columns: {len(dataset.column_metadata)}",
        f"- Free-text columns sanitized: {dataset.free_text_columns_sanitized}",
        f"- Total sanitized cells: {sum(dataset.sanitization_counts.values())}",
        f"- Load warnings: {len(dataset.load_warnings)}",
        "",
        f"## Domain context",
        f"- Domain requested: `{args.domain or '(none)'}`",
        f"- Missing context flag fired: {missing_context_flagged}",
        "",
        f"## Estimated prompt sizes per agent (~tokens)",
        "",
        "| Agent | Skills loaded | Files | ~Tokens |",
        "|---|---|---|---|",
    ]
    for agent, _legacy_skills in _DRY_RUN_AGENT_SKILLS.items():
        prompt = assemble_prompt(agent_name=agent, domain=args.domain)
        canonical_count = len(DEFAULT_SKILLS_BY_AGENT.get(agent, []))
        report_lines.append(
            f"| {agent} | {canonical_count} | {len(prompt.sections_loaded)} | {_estimate_tokens(prompt.system_prompt):,} |"
        )
    report_lines.extend(
        [
            "",
            f"**Total estimated prompt tokens across all 10 agents:** ~{total_prompt_tokens:,}",
            "",
            f"## Schema dispatch test",
            "All representative empty-arrays-valid payloads validated successfully.",
            "",
            f"## Next step",
            f"Plumbing is sound. To run the real pipeline:",
            "",
            "```bash",
            f"python -m src.main \\",
            f"  --question \"<your question>\" \\",
            f"  --data {args.data} \\",
        ]
    )
    if args.domain:
        report_lines.append(f"  --domain {args.domain} \\")
    report_lines.append("  # (remove --dry-run)")
    report_lines.append("```")
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"  report written: {report_path}")

    print("\n" + "=" * 72)
    print("[DRY-RUN] Plumbing verification PASSED.")
    print(f"Report: {report_path}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
