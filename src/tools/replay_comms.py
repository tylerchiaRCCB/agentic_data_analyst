"""Replay only the Communication Agent against an existing run's artifacts.

Use when the full pipeline ran but the comms-agent stage failed or wedged.
Loads the saved artifacts from `runs/<run_id>/artifacts/`, hands them to a
fresh Communication Agent call, and writes the final markdown.

Far cheaper than a full re-run (~$1-2 vs $10+) and produces the same final
markdown that a successful comms-agent stage would have written.

Usage:
    python -m src.tools.replay_comms --run-id 20260520T223548Z-89dba6ec

Output:
    output/<run_id>-replay.md
    runs/<run_id>/artifacts/05-communication-agent-replay.json
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
from src.orchestrator.prompt_assembler import assemble_prompt
from src.orchestrator.schemas import (
    CommunicationAgentPayload,
    QuestionFramerPayload,
    validate_payload,
)

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger(__name__)


REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_artifacts(run_dir: Path) -> tuple[QuestionFramerPayload, dict[str, dict[str, Any]]]:
    """Load all stage artifacts from a run directory.

    Returns (framer_payload, upstream_artifacts_by_agent).
    """
    artifacts_dir = run_dir / "artifacts"
    framer_path = artifacts_dir / "00-question-framer.json"
    if not framer_path.exists():
        raise FileNotFoundError(f"Missing framer artifact: {framer_path}")

    with framer_path.open() as f:
        framer_artifact = json.load(f)
    framer_payload = QuestionFramerPayload.model_validate(framer_artifact["payload"])

    upstream: dict[str, dict[str, Any]] = {}
    for path in sorted(artifacts_dir.glob("*.json")):
        if path.name.startswith("00-"):
            continue  # framer goes separately
        with path.open() as f:
            art = json.load(f)
        agent = art.get("agent")
        if agent and agent != "communication-agent":
            upstream[agent] = art

    return framer_payload, upstream


def _build_user_message(
    *,
    upstream_artifacts: dict[str, dict[str, Any]],
    framer_payload: QuestionFramerPayload,
) -> list[dict[str, Any]]:
    """Build the Communication Agent's user message from upstream artifacts."""
    payloads = {name: art.get("payload", {}) for name, art in upstream_artifacts.items()}
    parts = [
        "# Stage role\nYou are running as the **communication-agent** agent.",
        "# Question Framer's brief (this was the run's analytical plan)",
        "```json\n" + json.dumps(framer_payload.model_dump(), indent=2, default=str) + "\n```",
        "# Upstream analytical artifacts (computed summaries — NOT raw rows)",
        "```json\n" + json.dumps(payloads, indent=2, default=str) + "\n```",
        "# Your task\nProduce your output as a single JSON object matching the schema "
        "specified in your role. No prose outside the JSON. Include `rendered_output_markdown` "
        "as the final recipient-facing markdown that combines action cards (if any), the "
        "descriptive summary, and all carried caveats — formatted per your skills.",
    ]
    return [{"type": "text", "text": "\n\n".join(parts)}]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--run-id",
        type=str,
        required=True,
        help="Run ID (the directory name under runs/, e.g. 20260520T223548Z-89dba6ec)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/pipeline_config.yaml"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output"),
    )
    args = parser.parse_args()

    # ---- Azure Key Vault: load ANTHROPIC_API_KEY if not already set ----
    import os
    if not os.getenv("ANTHROPIC_API_KEY"):
        try:
            from azure.identity import AzureCliCredential, DefaultAzureCredential
            from azure.keyvault.secrets import SecretClient

            vault_url = "https://glccbdsdevkv.vault.azure.net/"
            secret_name = "chris-anderson-anthropic"
            try:
                credential = DefaultAzureCredential()
                client = SecretClient(vault_url=vault_url, credential=credential)
                secret = client.get_secret(secret_name)
                cred_name = "DefaultAzureCredential"
            except Exception:
                credential = AzureCliCredential()
                client = SecretClient(vault_url=vault_url, credential=credential)
                secret = client.get_secret(secret_name)
                cred_name = "AzureCliCredential"
            os.environ["ANTHROPIC_API_KEY"] = secret.value
            logger.info(f"Loaded ANTHROPIC_API_KEY from Azure Key Vault ({cred_name})")
        except Exception as e:
            logger.error(f"Failed to load ANTHROPIC_API_KEY from Azure Key Vault: {e}")

    run_dir = REPO_ROOT / "runs" / args.run_id
    if not run_dir.is_dir():
        logger.error("Run directory not found: %s", run_dir)
        return 1

    with args.config.open() as f:
        cfg = yaml.safe_load(f)
    model = cfg["model_per_agent"]["communication-agent"]
    max_tokens = cfg.get("max_tokens_per_call", 16384)

    logger.info("Loading artifacts from %s", run_dir)
    framer_payload, upstream = _load_artifacts(run_dir)
    logger.info("Loaded %d upstream artifacts: %s", len(upstream), list(upstream.keys()))

    prompt = assemble_prompt(
        agent_name="communication-agent",
        skills=[
            "proactive-action-card",
            "descriptive-summary-format",
            "insight-first-formatting",
            "confidence-language",
            "stakeholder-communication",
            "visualization-recommendations",
        ],
        domain=None,
    )
    logger.info("System prompt: %d chars, %d sections", len(prompt.system_prompt), len(prompt.sections_loaded))

    user_message = _build_user_message(upstream_artifacts=upstream, framer_payload=framer_payload)

    client = ClaudeClient()
    logger.info("Calling Communication Agent (model=%s)...", model)
    t0 = time.perf_counter()
    response = client.call(
        model=model,
        system=prompt.system_blocks,
        messages=[{"role": "user", "content": user_message}],
        max_tokens=max_tokens,
        enable_code_execution=False,  # comms doesn't typically need code execution
        enable_files_api=False,
        timeout_seconds=900.0,
    )
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    logger.info(
        "Call returned in %d ms. Tokens: in=%d out=%d (cache_read=%d cache_write=%d)",
        elapsed_ms,
        response.input_tokens,
        response.output_tokens,
        response.cache_read_tokens,
        response.cache_write_tokens,
    )

    # Extract JSON payload from response text
    text = response.text.strip()
    parsed: dict[str, Any] | None = None
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
            first = text.find("{")
            last = text.rfind("}")
            if first != -1 and last > first:
                try:
                    parsed = json.loads(text[first : last + 1])
                except json.JSONDecodeError:
                    pass

    if parsed is None:
        logger.error("No JSON payload found in response. Raw text saved to runs/<id>/replay-raw.txt")
        (run_dir / "replay-raw.txt").write_text(text, encoding="utf-8")
        return 2

    try:
        comms_payload = validate_payload("communication-agent", parsed)
        assert isinstance(comms_payload, CommunicationAgentPayload)
    except Exception as e:
        logger.error("Schema validation failed: %s", e)
        (run_dir / "replay-failed-payload.json").write_text(json.dumps(parsed, indent=2), encoding="utf-8")
        return 3

    # Persist the artifact
    artifact = {
        "schema_version": "1.0",
        "agent": "communication-agent",
        "run_id": args.run_id,
        "stage_index": 99,
        "produced_at": datetime.now(tz=timezone.utc).isoformat(),
        "duration_ms": elapsed_ms,
        "token_usage": {
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "cache_read_tokens": response.cache_read_tokens,
            "cache_write_tokens": response.cache_write_tokens,
            "total_cost_usd": 0.0,
        },
        "status": "ok",
        "payload": parsed,
        "replayed": True,
    }
    artifact_path = run_dir / "artifacts" / "05-communication-agent-replay.json"
    artifact_path.write_text(json.dumps(artifact, indent=2, default=str), encoding="utf-8")
    logger.info("Artifact written: %s", artifact_path)

    # Write the recipient markdown
    args.output_dir.mkdir(parents=True, exist_ok=True)
    md_path = args.output_dir / f"{args.run_id}-replay.md"
    md_path.write_text(comms_payload.rendered_output_markdown, encoding="utf-8")
    logger.info("Final markdown written: %s", md_path)

    print()
    print("=" * 72)
    print(f"REPLAY SUCCEEDED — final markdown at: {md_path}")
    print(f"  action_cards rendered: {len(comms_payload.action_cards)}")
    print(f"  output_mode: {comms_payload.output_mode}")
    print(f"  total tokens: in={response.input_tokens}, out={response.output_tokens}")
    print("=" * 72)

    return 0


if __name__ == "__main__":
    sys.exit(main())
