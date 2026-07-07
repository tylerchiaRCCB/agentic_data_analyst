#!/usr/bin/env python3
"""Adapter: analyst-web worker contract  ->  agentic_data_analyst CLI.

The worker invokes (see app/worker/pipeline_adapter.py):
    <this script> --question-file <run_dir>/question.txt \
                  --semantic-view <run_dir>/input.yaml \
                  --output-dir <run_dir>

The pipeline (github.com/tylerchiaRCCB/agentic_data_analyst) instead wants:
    python -m src.main --question "<text>" --source cortex_analyst \
        [--semantic-view DB.SCHEMA.VIEW | --domain <name>] --output-dir <dir>
run from its own repo root, and it writes <timestamp>-<slug>.md, not report.md.

This script bridges the two. Stdlib only — safe to run with any Python 3.11+.

How the run's input.yaml is interpreted (top-level keys, all optional):
    semantic_view: DB.SCHEMA.VIEW   -> passed as --semantic-view; YAML body unused
                                       by Cortex (it prefers the view reference)
    domain: <name>                  -> passed as --domain (loads the pipeline's
                                       context/domains/<name>.md, and names the
                                       semantic model)
If no semantic_view key is present, the YAML itself IS the semantic model: it is
copied into the pipeline's context/semantic_models/ — as <domain>.yaml when a
domain is declared (the web-managed YAML wins over the repo copy), otherwise
under a unique per-run name that is cleaned up afterwards.

Environment (forwarded by the worker because of the PIPELINE_ prefix):
    PIPELINE_REPO        path to the agentic_data_analyst checkout. Optional when
                         this webapp lives inside that repo (webapp/adapters/...):
                         the enclosing repo root is auto-detected.
    PIPELINE_PYTHON      python interpreter to use (default: uv run inside repo)
    PIPELINE_BACKEND     --backend value (anthropic|foundry|foundry-dev|azure-openai)
    PIPELINE_EXTRA_ARGS  extra CLI args appended verbatim, e.g. "--dry-run"

Snowflake/Anthropic/Azure credentials: the pipeline calls load_dotenv() itself,
so its own <repo>/.env is honored; SNOWFLAKE_*/ANTHROPIC_* forwarded by the
worker take precedence over .env values.
"""

from __future__ import annotations

import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

_TOP_LEVEL_KEY = re.compile(r"^(semantic_view|domain):\s*[\"']?([^\"'#\n]+?)[\"']?\s*$", re.M)


def _fail(msg: str, code: int = 2) -> None:
    print(f"[adapter] ERROR: {msg}", flush=True)
    raise SystemExit(code)


def _parse_directives(yaml_text: str) -> dict[str, str]:
    """Cheap scan for top-level `semantic_view:` / `domain:` scalar keys.

    Deliberately not a YAML parser: keeps this script dependency-free, and only
    top-level scalars are meaningful here (an indented key never matches ^)."""
    return {m.group(1): m.group(2).strip() for m in _TOP_LEVEL_KEY.finditer(yaml_text)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--question-file", type=Path, required=True)
    ap.add_argument("--semantic-view", type=Path, required=True,
                    help="Path to the run's input.yaml (analyst-web contract)")
    ap.add_argument("--output-dir", type=Path, required=True)
    args = ap.parse_args()

    repo_env = os.environ.get("PIPELINE_REPO", "").strip()
    if repo_env:
        repo = Path(repo_env).expanduser()
    else:
        # webapp/ lives inside the pipeline repo: <repo>/webapp/adapters/<this file>
        repo = Path(__file__).resolve().parents[2]
    if not repo.is_dir() or not (repo / "src" / "main.py").exists():
        _fail("PIPELINE_REPO is not set and auto-detection failed — this script is not "
              f"inside an agentic_data_analyst checkout (looked at: {repo})")

    question = args.question_file.read_text(encoding="utf-8").strip()
    if not question:
        _fail("question.txt is empty")
    yaml_text = args.semantic_view.read_text(encoding="utf-8")
    directives = _parse_directives(yaml_text)

    out_dir = args.output_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- interpreter -------------------------------------------------------
    pipeline_python = os.environ.get("PIPELINE_PYTHON", "").strip()
    if pipeline_python:
        cmd = [pipeline_python, "-m", "src.main"]
    else:
        cmd = ["uv", "run", "--project", str(repo), "python", "-m", "src.main"]

    cmd += ["--question", question, "--source", "cortex_analyst", "--output-dir", str(out_dir)]

    # --- semantic model routing -------------------------------------------
    temp_model: Path | None = None
    if "semantic_view" in directives:
        cmd += ["--semantic-view", directives["semantic_view"]]
        if "domain" in directives:
            cmd += ["--domain", directives["domain"]]
    else:
        models_dir = repo / "context" / "semantic_models"
        models_dir.mkdir(parents=True, exist_ok=True)
        if "domain" in directives:
            # Web-managed YAML is the source of truth for this domain's model.
            model_name = directives["domain"]
        else:
            model_name = f"webrun-{out_dir.name}"
            temp_model = models_dir / f"{model_name}.yaml"
        (models_dir / f"{model_name}.yaml").write_text(yaml_text, encoding="utf-8")
        cmd += ["--domain", model_name]

    if backend := os.environ.get("PIPELINE_BACKEND", "").strip():
        cmd += ["--backend", backend]
    if extra := os.environ.get("PIPELINE_EXTRA_ARGS", "").strip():
        cmd += shlex.split(extra)

    # --- run ---------------------------------------------------------------
    started = time.time()
    print(f"[adapter] exec (cwd={repo}): {' '.join(shlex.quote(c) for c in cmd)}", flush=True)
    try:
        rc = subprocess.run(cmd, cwd=str(repo)).returncode
    finally:
        if temp_model is not None:
            temp_model.unlink(missing_ok=True)

    if rc != 0:
        print(f"[adapter] pipeline exited with {rc}", flush=True)
        return rc

    # --- normalize output: newest markdown -> report.md ---------------------
    candidates = [p for p in out_dir.glob("*.md") if p.name != "report.md"]
    if not candidates:
        _fail(f"pipeline exited 0 but wrote no .md into {out_dir}", code=3)
    newest = max(candidates, key=lambda p: p.stat().st_mtime)
    shutil.copyfile(newest, out_dir / "report.md")
    print(f"[adapter] report.md <- {newest.name}", flush=True)

    # --- best-effort: copy this run's pipeline artifacts --------------------
    artifacts_out = out_dir / "artifacts"
    runs_root = repo / "runs"
    if runs_root.is_dir():
        for run_dir in runs_root.iterdir():
            if run_dir.is_dir() and run_dir.stat().st_mtime >= started:
                artifacts_out.mkdir(exist_ok=True)
                for f in list(run_dir.glob("artifacts/*")) + list(run_dir.glob("run.jsonl")):
                    if f.is_file():
                        shutil.copyfile(f, artifacts_out / f.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
