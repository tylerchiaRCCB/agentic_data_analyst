"""Pipeline executor — the orchestrator's main loop.

Reads the Question Framer's brief, executes each stage in the specified order with the
specified skills loaded, validates each artifact against its Pydantic schema, and passes
results to the next stage.

Failure handling follows orchestration/failure-recovery.md:
- Schema validation failures: retry once with a clarifying instruction. If retry fails,
  treat as agent total failure.
- Agent total failure: non-critical agents skip-and-flag; critical agents (Question
  Framer, Data Retrieval, Communication Agent) hard-fail.
- Findings Validator failure: special path — does NOT silently proceed. See §6.

MVP scope: serial execution per stage (no parallel-group execution yet — the
PipelineStageParallel schema accepts the shape, but this executor processes parallel
stages sequentially for now). Parallelism is a tractable extension once the serial flow
is proven.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from src.api.claude_client import ClaudeClient, ClaudeResponse
from src.observability.run_logger import RunLogger
from src.observability.tracer import Tracer
from src.orchestrator.budget_tracker import BudgetTracker
from src.orchestrator.lineage_tracker import LineageTracker
from src.orchestrator.prompt_assembler import AssembledPrompt, assemble_prompt
from src.orchestrator.schemas import (
    Artifact,
    PAYLOAD_BY_AGENT,
    AgentName,
    QuestionFramerPayload,
    TokenUsage,
    validate_payload,
)

logger = logging.getLogger(__name__)

CRITICAL_AGENTS: set[str] = {"question-framer", "data-retrieval-agent", "communication-agent"}


@dataclass
class PipelineConfig:
    """Subset of pipeline_config.yaml the executor needs at runtime."""

    model_per_agent: dict[str, str]
    max_tokens_per_call: int = 8192
    max_retries_per_stage: int = 1  # the "one retry" rule from failure-recovery §1


@dataclass
class StageResult:
    stage_index: int
    agent: AgentName
    artifact: dict[str, Any]
    status: str  # "ok" | "degraded" | "failed"
    duration_ms: int
    skill_paths_loaded: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class PipelineRun:
    run_id: str
    artifacts_by_agent: dict[str, dict[str, Any]] = field(default_factory=dict)
    stage_results: list[StageResult] = field(default_factory=list)
    run_caveats: list[dict[str, str]] = field(default_factory=list)
    status: str = "ok"
    final_output_path: Path | None = None


class PipelineExecutor:
    def __init__(
        self,
        *,
        client: ClaudeClient,
        config: PipelineConfig,
        run_logger: RunLogger,
        tracer: Tracer,
        budget: BudgetTracker,
        lineage: LineageTracker,
        domain: str | None = None,
    ) -> None:
        self.client = client
        self.config = config
        self.run_logger = run_logger
        self.tracer = tracer
        self.budget = budget
        self.lineage = lineage
        self.domain = domain

    # ---------- Question Framer entry point ----------

    def invoke_framer(
        self,
        *,
        user_question: str,
        proactive_prompt: str | None = None,
        data_summary: dict[str, Any] | None = None,
    ) -> QuestionFramerPayload:
        """Run the Question Framer alone to produce the pipeline brief.

        The framer's output drives every subsequent stage.
        """
        self.run_logger.info("Invoking Question Framer", question=user_question[:100])
        agent: AgentName = "question-framer"
        # `analysis-design-spec` is a universal skill and auto-loads; only on-demand
        # skills appear in this list.
        prompt = assemble_prompt(
            agent_name=agent,
            skills=["hypothesis-generation-from-data"],
            domain=self.domain,
        )

        if prompt.missing_domain_context:
            self._record_missing_context(prompt)

        user_message_text = self._framer_user_message(
            user_question=user_question,
            proactive_prompt=proactive_prompt,
            data_summary=data_summary,
        )
        artifact = self._call_and_validate(
            agent=agent,
            stage_index=0,
            prompt=prompt,
            user_message=user_message_text,
        )
        return QuestionFramerPayload.model_validate(artifact["payload"])

    # ---------- Main pipeline loop ----------

    def execute_pipeline(
        self,
        framer: QuestionFramerPayload,
        *,
        dataset_file_id: str | None = None,
    ) -> PipelineRun:
        """Execute the pipeline composed by the Question Framer.

        The framer artifact is already stored as stage 0.
        """
        run = PipelineRun(run_id=self.run_logger.run_id)
        run.run_caveats = list(getattr(self, "_pending_run_caveats", []))

        for i, stage in enumerate(framer.pipeline_composition, start=1):
            # MVP: process parallel groups sequentially. Parallel execution is a future
            # extension; the schema accepts the shape.
            stages_to_run = stage.parallel if hasattr(stage, "parallel") else [stage]
            for sub_stage in stages_to_run:
                result = self._execute_stage(
                    stage_index=i,
                    agent=sub_stage.agent,
                    skills=sub_stage.skills,
                    upstream_artifacts=dict(run.artifacts_by_agent),
                    dataset_file_id=dataset_file_id,
                )
                run.stage_results.append(result)

                if result.status == "ok":
                    run.artifacts_by_agent[result.agent] = result.artifact
                    self.lineage.add_artifact_statistics(
                        agent=result.agent,
                        stage_index=result.stage_index,
                        payload=result.artifact.get("payload", {}),
                    )
                elif result.status == "degraded":
                    run.artifacts_by_agent[result.agent] = result.artifact
                    run.run_caveats.append(
                        {
                            "text": f"Stage {result.agent} degraded: {result.error}",
                            "severity": "high",
                            "reason": "stage degradation",
                        }
                    )
                    run.status = "degraded"
                else:  # failed
                    if result.agent in CRITICAL_AGENTS:
                        run.status = "failed"
                        self._write_failure_report(run, result)
                        return run
                    # Non-critical: skip-and-flag
                    run.run_caveats.append(
                        {
                            "text": f"Stage {result.agent} failed and was skipped. Analytical depth in this area is reduced.",
                            "severity": "high",
                            "reason": "agent total failure",
                        }
                    )
                    run.status = "degraded"

        return run

    # ---------- Per-stage execution ----------

    def _execute_stage(
        self,
        *,
        stage_index: int,
        agent: AgentName,
        skills: list[str],
        upstream_artifacts: dict[str, dict[str, Any]] | None = None,
        dataset_file_id: str | None = None,
    ) -> StageResult:
        with self.tracer.span(f"stage.{agent}", stage_index=stage_index) as span:
            prompt = assemble_prompt(agent_name=agent, skills=skills, domain=self.domain)
            span.attributes["skills_loaded"] = prompt.sections_loaded

            if prompt.missing_domain_context and not getattr(self, "_missing_context_recorded", False):
                self._record_missing_context(prompt)

            user_message_text = self._build_user_message(
                agent=agent,
                upstream_artifacts=upstream_artifacts,
                dataset_file_id=dataset_file_id,
            )
            try:
                artifact = self._call_and_validate(
                    agent=agent,
                    stage_index=stage_index,
                    prompt=prompt,
                    user_message=user_message_text,
                )
                return StageResult(
                    stage_index=stage_index,
                    agent=agent,
                    artifact=artifact,
                    status=artifact.get("status", "ok"),
                    duration_ms=artifact.get("duration_ms", 0),
                    skill_paths_loaded=prompt.sections_loaded,
                )
            except Exception as e:
                logger.exception("Stage %s failed", agent)
                return StageResult(
                    stage_index=stage_index,
                    agent=agent,
                    artifact={},
                    status="failed",
                    duration_ms=0,
                    error=f"{type(e).__name__}: {e}",
                )

    # ---------- API call + schema validation ----------

    def _call_and_validate(
        self,
        *,
        agent: AgentName,
        stage_index: int,
        prompt: AssembledPrompt,
        user_message: str,
    ) -> dict[str, Any]:
        model = self.config.model_per_agent.get(agent)
        if not model:
            raise ValueError(f"No model configured for agent: {agent}")

        attempt = 0
        last_error: str | None = None
        clarification = ""
        while attempt <= self.config.max_retries_per_stage:
            attempt += 1
            messages = [{"role": "user", "content": user_message + clarification}]
            t0 = time.perf_counter()
            response: ClaudeResponse = self.client.call(
                model=model,
                system=prompt.system_blocks,  # structured form enables prompt caching
                messages=messages,
                max_tokens=self.config.max_tokens_per_call,
                enable_code_execution=True,
            )
            duration_ms = int((time.perf_counter() - t0) * 1000)

            self.budget.record(
                stage_index=stage_index,
                agent=agent,
                model=model,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                cache_read_tokens=response.cache_read_tokens,
                cache_write_tokens=response.cache_write_tokens,
            )

            parsed = self._extract_json_payload(response.text)
            if parsed is None:
                last_error = "No JSON payload found in agent response"
                clarification = self._clarification_for(agent, last_error)
                continue

            try:
                validate_payload(agent, parsed)
            except ValidationError as e:
                last_error = f"Schema validation failed: {e.errors()[:3]}"
                clarification = self._clarification_for(agent, last_error)
                continue

            artifact = {
                "schema_version": "1.0",
                "agent": agent,
                "run_id": self.run_logger.run_id,
                "stage_index": stage_index,
                "produced_at": datetime.now(tz=timezone.utc).isoformat(),
                "duration_ms": duration_ms,
                "token_usage": TokenUsage(
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                    cache_read_tokens=response.cache_read_tokens,
                    cache_write_tokens=response.cache_write_tokens,
                ).model_dump(),
                "status": "ok",
                "payload": parsed,
            }
            self.run_logger.write_artifact(stage_index, agent, artifact)
            return artifact

        raise RuntimeError(f"Agent {agent} failed after {attempt} attempt(s): {last_error}")

    def _write_failure_report(self, run: PipelineRun, failed: StageResult) -> None:
        """Persist a markdown failure report for hard-failed runs (failure-recovery §10)."""
        lines = [
            f"# Pipeline run failed — {run.run_id}",
            "",
            f"**Failed stage:** {failed.agent} (stage_index={failed.stage_index})",
            f"**Error:** {failed.error}",
            "",
            "## Stages completed before failure",
            *(f"- stage {s.stage_index}: {s.agent} → {s.status}" for s in run.stage_results),
            "",
            "## Run caveats accumulated",
            *(f"- [{c['severity']}] {c['text']}" for c in run.run_caveats),
        ]
        self.run_logger.write_failure_report("\n".join(lines))

    # ---------- Helpers ----------

    @staticmethod
    def _extract_json_payload(text: str) -> dict[str, Any] | None:
        """Best-effort: find the JSON object in the agent's response.

        Agents are instructed to emit their payload as a JSON object in the response.
        Handles common patterns: bare JSON, fenced code block, or JSON inline.
        """
        text = text.strip()
        # Try direct parse
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass

        # Try fenced ```json blocks
        for fence in ("```json", "```JSON", "```"):
            if fence in text:
                start = text.find(fence) + len(fence)
                end = text.find("```", start)
                if end > start:
                    block = text[start:end].strip()
                    try:
                        obj = json.loads(block)
                        if isinstance(obj, dict):
                            return obj
                    except json.JSONDecodeError:
                        continue

        # Last resort: find first { ... } balanced block
        first = text.find("{")
        last = text.rfind("}")
        if first != -1 and last > first:
            candidate = text[first : last + 1]
            try:
                obj = json.loads(candidate)
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                return None
        return None

    @staticmethod
    def _clarification_for(agent: str, error: str) -> str:
        return (
            f"\n\n[Retry guidance — your previous response could not be parsed/validated]\n"
            f"Error: {error}\n"
            f"Please re-emit your response as a single JSON object matching the schema for the {agent} agent "
            f"specified in your role. The JSON must be syntactically valid and contain all required fields. "
            f"No prose outside the JSON object."
        )

    def _record_missing_context(self, prompt: AssembledPrompt) -> None:
        msg = (
            f"No domain context document was found for '{prompt.domain_attempted}'. "
            "Analysis proceeded without business-meaning context: metric definitions, "
            "guardrail pairings, known data quirks, and investigation hypothesis libraries "
            "were not available. Findings should be read as data-shape observations, "
            "not domain-grounded conclusions. The Findings Validator's guardrail-pairing "
            "check produced reduced coverage as a result."
        )
        self.run_logger.warning("Missing domain context", domain=prompt.domain_attempted)
        if not hasattr(self, "_pending_run_caveats"):
            self._pending_run_caveats = []
        self._pending_run_caveats.append(
            {"text": msg, "severity": "high", "reason": "missing domain context"}
        )
        self._missing_context_recorded = True

    def _framer_user_message(
        self,
        *,
        user_question: str,
        proactive_prompt: str | None,
        data_summary: dict[str, Any] | None,
    ) -> str:
        parts: list[str] = []
        if proactive_prompt:
            parts.append(f"# Scheduled prompt\n{proactive_prompt}")
        if user_question:
            parts.append(f"# User question\n{user_question}")
        if data_summary:
            parts.append(
                "# Available data (summary — actual data lives in code execution sandbox)\n"
                + json.dumps(data_summary, indent=2)
            )
        parts.append(
            "\n# Your task\nProduce a `QuestionFramerPayload` as a single JSON object. "
            "Follow the schema from your role. No prose outside the JSON. Use the "
            "code execution tool only if you need to compute something to verify a premise."
        )
        return "\n\n".join(parts)

    def _build_user_message(
        self,
        *,
        agent: str,
        upstream_artifacts: dict[str, dict[str, Any]] | None = None,
        dataset_file_id: str | None = None,
    ) -> str:
        """For non-framer stages, the orchestrator gives the agent the upstream artifacts
        (computed summaries — not raw rows) and an instruction to produce its own typed
        payload.
        """
        parts: list[str] = [
            f"# Stage role\nYou are running as the **{agent}** agent."
        ]
        if dataset_file_id:
            parts.append(
                f"# Dataset access\nThe dataset is available in the code execution sandbox "
                f"via Anthropic Files API as file_id `{dataset_file_id}`. Load it with "
                f"`import pandas as pd; df = pd.read_csv(f'/mnt/user-data/{dataset_file_id}')` "
                f"or analogous. NEVER print or return raw rows; emit summaries only "
                "(per pipeline-definitions.md §10)."
            )
        if upstream_artifacts:
            parts.append("# Upstream artifacts (computed summaries — NOT raw rows)")
            # We only include the payloads, since the envelope metadata is noise here.
            payloads = {
                name: art.get("payload", {}) for name, art in upstream_artifacts.items()
            }
            parts.append("```json\n" + json.dumps(payloads, indent=2, default=str) + "\n```")
        parts.append(
            "# Your task\nProduce your output as a single JSON object matching the schema "
            "specified in your role. No prose outside the JSON. Use the code_execution "
            "tool for every numeric claim."
        )
        return "\n\n".join(parts)
