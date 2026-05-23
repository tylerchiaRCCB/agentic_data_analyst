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

import concurrent.futures
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
from src.api.llm_client import (
    LLMClient,
    get_llm_client,
    parse_model_id,
    resolve_model_for_call as _resolve_model_for_call,
)
from src.observability.run_logger import RunLogger
from src.observability.tracer import Tracer
from src.orchestrator.budget_tracker import BudgetExceeded, BudgetTracker
from src.orchestrator.lineage_tracker import LineageTracker
from src.orchestrator.prompt_assembler import AssembledPrompt, assemble_prompt
from src.orchestrator.schemas import (
    agent_output_tool,
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
        # `client` is the *primary* / Anthropic-native client. When per-agent
        # model config selects a non-Anthropic provider (e.g. `openai/gpt-5`),
        # _client_for_model dispatches via factory; cached so we don't recreate
        # per-call.
        self.client = client
        self.config = config
        self.run_logger = run_logger
        self.tracer = tracer
        self.budget = budget
        self.lineage = lineage
        self.domain = domain
        self._client_cache: dict[str, LLMClient] = {}

    def _client_for_model(self, model: str) -> LLMClient:
        """Return the LLMClient that handles this model id.

        Anthropic models (bare or prefixed) → the injected self.client.
        Other providers → cached LiteLLM client via factory.
        """
        provider, _ = parse_model_id(model)
        if provider == "anthropic":
            return self.client  # type: ignore[return-value]
        if provider not in self._client_cache:
            self._client_cache[provider] = get_llm_client(model)
        return self._client_cache[provider]

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

        try:
            for i, stage in enumerate(framer.pipeline_composition, start=1):
                stages_to_run = stage.parallel if hasattr(stage, "parallel") else [stage]
                # Snapshot of upstream artifacts at this group's start — every sub-stage
                # sees the same upstream view. They are independent by spec (otherwise
                # the framer would not have grouped them).
                upstream_snapshot = dict(run.artifacts_by_agent)
                stage_results = self._execute_stage_group(
                    stage_index=i,
                    sub_stages=stages_to_run,
                    upstream_artifacts=upstream_snapshot,
                    dataset_file_id=dataset_file_id,
                )
                for result in stage_results:
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
        except BudgetExceeded as e:
            # Hard cost cap hit. Preserve the most recent stage's artifact (already
            # appended to stage_results); mark the run aborted with a high-severity
            # caveat the Communication Agent will not see — the pipeline is over.
            self.run_logger.error(
                "Pipeline aborted: cost cap exceeded",
                total_cost_usd=round(e.total_cost_usd, 4),
                max_cost_usd=e.max_cost_usd,
                stage_index=e.stage_index,
                agent=e.agent,
            )
            run.status = "failed"
            run.run_caveats.append(
                {
                    "text": (
                        f"Pipeline aborted: cumulative cost ${e.total_cost_usd:.4f} exceeded "
                        f"configured cap ${e.max_cost_usd:.2f} after stage {e.stage_index} ({e.agent})."
                    ),
                    "severity": "high",
                    "reason": "budget_exceeded",
                }
            )
            # Write failure report so the operator sees the abort with full context
            failure_result = StageResult(
                stage_index=e.stage_index,
                agent=e.agent,
                status="failed",
                error=f"Budget cap exceeded (${e.total_cost_usd:.4f} > ${e.max_cost_usd:.2f})",
                artifact={},
                duration_ms=0,
            )
            self._write_failure_report(run, failure_result)

        return run

    # ---------- Stage-group execution (handles serial + parallel sub-stages) ----------

    def _execute_stage_group(
        self,
        *,
        stage_index: int,
        sub_stages: list[Any],
        upstream_artifacts: dict[str, dict[str, Any]],
        dataset_file_id: str | None,
    ) -> list[StageResult]:
        """Execute one stage of the framer's pipeline_composition.

        A "stage" can be a single agent (serial) or a parallel group of independent
        agents. For parallel groups, sub-stages run concurrently in a thread pool —
        their upstream snapshot is identical and they have no dependencies on each
        other's outputs (the framer guarantees this by construction).

        BudgetExceeded from any sub-stage cancels in-flight siblings and bubbles up.
        """
        if len(sub_stages) == 1:
            return [
                self._execute_stage(
                    stage_index=stage_index,
                    agent=sub_stages[0].agent,
                    skills=sub_stages[0].skills,
                    upstream_artifacts=upstream_artifacts,
                    dataset_file_id=dataset_file_id,
                )
            ]

        # Parallel sub-stages
        max_workers = min(len(sub_stages), 4)
        self.run_logger.info(
            "Parallel stage group starting",
            stage_index=stage_index,
            agents=[s.agent for s in sub_stages],
            workers=max_workers,
        )
        results: list[StageResult] = [None] * len(sub_stages)  # type: ignore[list-item]
        budget_error: BudgetExceeded | None = None
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            future_to_idx = {
                pool.submit(
                    self._execute_stage,
                    stage_index=stage_index,
                    agent=sub.agent,
                    skills=sub.skills,
                    upstream_artifacts=upstream_artifacts,
                    dataset_file_id=dataset_file_id,
                ): idx
                for idx, sub in enumerate(sub_stages)
            }
            for fut in concurrent.futures.as_completed(future_to_idx):
                idx = future_to_idx[fut]
                try:
                    results[idx] = fut.result()
                except BudgetExceeded as e:
                    # Latch the first budget error; cancel the rest. The error
                    # bubbles up to execute_pipeline's handler after the pool drains.
                    if budget_error is None:
                        budget_error = e
                    # Best-effort cancel of pending futures (those not yet running
                    # will be cancellable; in-flight ones cannot be).
                    for other in future_to_idx:
                        other.cancel()
                # Other exceptions are returned as StageResult(status="failed") by
                # _execute_stage already; no need to handle here.

        if budget_error is not None:
            raise budget_error
        # Order results by original sub-stage order (we filled by index)
        return [r for r in results if r is not None]

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
        self.run_logger.info(
            f"Stage starting: {agent}",
            stage_index=stage_index,
            skills=skills,
        )
        t0 = time.perf_counter()
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
                stage_duration_ms = int((time.perf_counter() - t0) * 1000)
                self.run_logger.info(
                    f"Stage done: {agent}",
                    stage_index=stage_index,
                    duration_ms=stage_duration_ms,
                    status=artifact.get("status", "ok"),
                )
                return StageResult(
                    stage_index=stage_index,
                    agent=agent,
                    artifact=artifact,
                    status=artifact.get("status", "ok"),
                    duration_ms=artifact.get("duration_ms", 0),
                    skill_paths_loaded=prompt.sections_loaded,
                )
            except BudgetExceeded:
                # Let the cost-cap abort bubble up to execute_pipeline's handler,
                # which writes a clean failure report and marks the run failed.
                # If we swallow it here, the stage becomes just another failed
                # stage and the cap doesn't actually stop the pipeline.
                raise
            except Exception as e:
                stage_duration_ms = int((time.perf_counter() - t0) * 1000)
                self.run_logger.error(
                    f"Stage failed: {agent}",
                    stage_index=stage_index,
                    duration_ms=stage_duration_ms,
                    error=f"{type(e).__name__}: {e}",
                )
                logger.exception("Stage %s failed", agent)
                return StageResult(
                    stage_index=stage_index,
                    agent=agent,
                    artifact={},
                    status="failed",
                    duration_ms=stage_duration_ms,
                    error=f"{type(e).__name__}: {e}",
                )

    # ---------- API call + schema validation ----------

    def _call_and_validate(
        self,
        *,
        agent: AgentName,
        stage_index: int,
        prompt: AssembledPrompt,
        user_message: list[dict[str, Any]],
    ) -> dict[str, Any]:
        model = self.config.model_per_agent.get(agent)
        if not model:
            raise ValueError(f"No model configured for agent: {agent}")

        attempt = 0
        last_error: str | None = None
        clarification: dict[str, Any] | None = None
        while attempt <= self.config.max_retries_per_stage:
            attempt += 1
            # On retry: append the clarification block to the original user content
            content_blocks = list(user_message)
            if clarification is not None:
                content_blocks.append(clarification)
            messages = [{"role": "user", "content": content_blocks}]
            t0 = time.perf_counter()
            # Structured-output enforcement: pass the agent's artifact schema as
            # an Anthropic tool. Claude is expected to emit the final artifact
            # via tool_use rather than free-form JSON. Code execution still works
            # mid-stream — both tools are available. The strong prompt-level
            # instruction (in each agent.md) is that the final emit_*_artifact
            # call is required.
            #
            # Provider dispatch: when the configured model is prefixed (e.g.
            # `openai/gpt-5`, `google/gemini-3-pro`), route via the factory so
            # the right client handles the call. Bare or `anthropic/...` model
            # names use the injected self.client (the existing primary path).
            call_client = self._client_for_model(model)
            response = call_client.call(
                model=_resolve_model_for_call(model),
                system=prompt.system_blocks,  # structured form enables prompt caching
                messages=messages,
                max_tokens=self.config.max_tokens_per_call,
                enable_code_execution=True,
                output_tool=agent_output_tool(agent),
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

            # Prefer the structured tool_output (the canonical path post-enforcement).
            # Fall back to text-extraction parsing only if the model emitted free-form
            # JSON instead of using the tool — this is rare with the tool defined
            # but covers cases where Claude bails out via plain text.
            parsed = response.tool_output
            if parsed is None:
                parsed = self._extract_json_payload(response.text)
            if parsed is None:
                last_error = "No structured artifact emitted (neither tool_use nor JSON in text)"
                clarification = {"type": "text", "text": self._clarification_for(agent, last_error)}
                continue

            try:
                validate_payload(agent, parsed)
            except ValidationError as e:
                last_error = f"Schema validation failed: {e.errors()[:3]}"
                clarification = {"type": "text", "text": self._clarification_for(agent, last_error)}
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
                # Pin the prompt that produced this artifact. If any skill file
                # changes after this run, the SHA still records the bytes that
                # generated the payload — reproducibility / audit guarantee.
                "prompt_sha256": prompt.prompt_sha256,
                "skill_hashes": {
                    "universal": prompt.universal_skills_sha256,
                    "agent_block": prompt.agent_block_sha256,
                },
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
    ) -> list[dict[str, Any]]:
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
        return [{"type": "text", "text": "\n\n".join(parts)}]

    def _build_user_message(
        self,
        *,
        agent: str,
        upstream_artifacts: dict[str, dict[str, Any]] | None = None,
        dataset_file_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """For non-framer stages, the orchestrator gives the agent the upstream artifacts
        (computed summaries — not raw rows) and an instruction to produce its own typed
        payload.

        Returns a list of content blocks suitable for the messages API's
        `content` field. When `dataset_file_id` is set, prepends a `container_upload`
        block so the file is mounted in the code-execution sandbox at $INPUT_DIR.
        """
        blocks: list[dict[str, Any]] = []

        # Mount the uploaded file into the sandbox via container_upload block
        if dataset_file_id:
            blocks.append({"type": "container_upload", "file_id": dataset_file_id})

        parts: list[str] = [
            f"# Stage role\nYou are running as the **{agent}** agent."
        ]
        if dataset_file_id:
            parts.append(
                "# Dataset access\n"
                "The dataset is mounted in the code-execution sandbox. Locate it via the "
                "`INPUT_DIR` environment variable — files appear at "
                "`$INPUT_DIR/<original-filename>`. Example:\n"
                "```python\n"
                "import os, pandas as pd\n"
                "input_dir = os.environ['INPUT_DIR']\n"
                "files = os.listdir(input_dir)\n"
                "df = pd.read_csv(os.path.join(input_dir, files[0]))\n"
                "```\n"
                "NEVER print or return raw rows; emit summaries only "
                "(per pipeline-definitions.md §10)."
            )
        if upstream_artifacts:
            parts.append("# Upstream artifacts (computed summaries — NOT raw rows)")
            payloads = {
                name: art.get("payload", {}) for name, art in upstream_artifacts.items()
            }
            parts.append("```json\n" + json.dumps(payloads, indent=2, default=str) + "\n```")
        parts.append(
            "# Your task\nProduce your output as a single JSON object matching the schema "
            "specified in your role. No prose outside the JSON. Use the code_execution "
            "tool for every numeric claim."
        )

        blocks.append({"type": "text", "text": "\n\n".join(parts)})
        return blocks
