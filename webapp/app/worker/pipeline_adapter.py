"""The decoupling seam between this app and the analyst pipeline.

Contract with the pipeline entrypoint (PIPELINE_CMD):
    <PIPELINE_CMD> --question-file <run_dir>/question.txt \
                   --semantic-view <run_dir>/input.yaml \
                   --output-dir <run_dir>

The pipeline must write report.md into --output-dir (extra files go in
<run_dir>/artifacts/). stdout/stderr are captured to run.log. Exit code 0 = success.

The question is passed via file, never argv: avoids shell injection, flag-lookalike
questions, ps-visible leakage, and argv length limits.
"""

import os
import shlex
import subprocess
from pathlib import Path

from app.config import settings

# Env vars forwarded from the worker's environment to the pipeline subprocess.
# AZURE_ covers the agentic pipeline's foundry/azure-openai backends.
FORWARDED_ENV_PREFIXES = ("SNOWFLAKE_", "ANTHROPIC_", "PIPELINE_", "AZURE_")
FORWARDED_ENV_VARS = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "VIRTUAL_ENV")


def _absolutize(token: str) -> str:
    """The subprocess runs with cwd=<run_dir>, so resolve PIPELINE_CMD paths that
    are relative to the app root (e.g. the dev default 'tests/fake_pipeline.py')."""
    p = Path(token)
    if not p.is_absolute() and (Path.cwd() / p).exists():
        return str((Path.cwd() / p).resolve())
    return token


def build_command(run_dir: Path) -> list[str]:
    return [
        *(_absolutize(t) for t in shlex.split(settings.pipeline_cmd)),
        "--question-file", str(run_dir / "question.txt"),
        "--semantic-view", str(run_dir / "input.yaml"),
        "--output-dir", str(run_dir),
    ]


def build_env() -> dict[str, str]:
    env = {}
    for key, value in os.environ.items():
        if key in FORWARDED_ENV_VARS or key.startswith(FORWARDED_ENV_PREFIXES):
            env[key] = value
    return env


def launch(run_dir: Path) -> subprocess.Popen:
    run_dir = run_dir.resolve()  # argv paths must survive cwd=run_dir
    log_file = (run_dir / "run.log").open("ab")
    try:
        return subprocess.Popen(
            build_command(run_dir),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            env=build_env(),
            cwd=str(run_dir),
            start_new_session=True,  # own process group -> clean kill of children
        )
    finally:
        log_file.close()  # Popen holds its own reference
