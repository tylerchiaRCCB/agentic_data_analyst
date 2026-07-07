"""Tests for adapters/agentic_pipeline.py against a stub pipeline repo.

The real pipeline needs Snowflake/AKV credentials, so these tests fake it with
a minimal src/main.py that records its argv and writes a timestamped .md —
verifying the adapter's contract translation without any external calls.
"""

import json
import subprocess
import sys
from pathlib import Path

ADAPTER = Path(__file__).parent.parent / "adapters" / "agentic_pipeline.py"

STUB_MAIN = """
import json, sys
from pathlib import Path

args = sys.argv[1:]
Path("argv.json").write_text(json.dumps(args))
out = Path(args[args.index("--output-dir") + 1])
(out / "20260101T000000-stub-report.md").write_text("# Stub finding\\n")
run_dir = Path("runs/20260101T000000Z-deadbeef/artifacts")
run_dir.mkdir(parents=True, exist_ok=True)
(run_dir / "01-question-framer.json").write_text("{}")
sys.exit(0)
"""


def _make_stub_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "pipeline_repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "main.py").write_text(STUB_MAIN)
    (repo / "src" / "__init__.py").write_text("")
    return repo


def _make_run_dir(tmp_path: Path, yaml_text: str, question: str = "Why did sales dip?") -> Path:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "question.txt").write_text(question)
    (run_dir / "input.yaml").write_text(yaml_text)
    return run_dir


def _invoke(repo: Path, run_dir: Path, extra_env: dict | None = None):
    env = {
        "PIPELINE_REPO": str(repo),
        "PIPELINE_PYTHON": sys.executable,
        "PATH": "/usr/bin:/bin",
        **(extra_env or {}),
    }
    return subprocess.run(
        [sys.executable, str(ADAPTER),
         "--question-file", str(run_dir / "question.txt"),
         "--semantic-view", str(run_dir / "input.yaml"),
         "--output-dir", str(run_dir)],
        env=env, capture_output=True, text=True,
    )


def _stub_argv(repo: Path) -> list[str]:
    return json.loads((repo / "argv.json").read_text())


def test_adapter_inline_yaml_mode(tmp_path):
    repo = _make_stub_repo(tmp_path)
    run_dir = _make_run_dir(tmp_path, "name: sales_model\ntables:\n  - name: orders\n")
    proc = _invoke(repo, run_dir)
    assert proc.returncode == 0, proc.stdout + proc.stderr

    argv = _stub_argv(repo)
    assert argv[argv.index("--question") + 1] == "Why did sales dip?"
    assert argv[argv.index("--source") + 1] == "cortex_analyst"
    # YAML copied into the repo under a per-run model name, passed as --domain
    domain = argv[argv.index("--domain") + 1]
    assert domain == f"webrun-{run_dir.name}"
    # ... and the temp copy is cleaned up afterwards
    assert not (repo / "context" / "semantic_models" / f"{domain}.yaml").exists()

    # newest markdown normalized to report.md, artifacts copied back
    assert (run_dir / "report.md").read_text() == "# Stub finding\n"
    assert (run_dir / "artifacts" / "01-question-framer.json").exists()


def test_adapter_semantic_view_reference_mode(tmp_path):
    repo = _make_stub_repo(tmp_path)
    run_dir = _make_run_dir(
        tmp_path, 'semantic_view: "PROD.ANALYTICS.SALES_SV"\ndomain: commercial-sales\n'
    )
    proc = _invoke(repo, run_dir)
    assert proc.returncode == 0, proc.stdout + proc.stderr

    argv = _stub_argv(repo)
    assert argv[argv.index("--semantic-view") + 1] == "PROD.ANALYTICS.SALES_SV"
    assert argv[argv.index("--domain") + 1] == "commercial-sales"
    # nothing written into the repo's semantic model dir in this mode
    assert not (repo / "context" / "semantic_models").exists()
    assert (run_dir / "report.md").exists()


def test_adapter_declared_domain_owns_model_yaml(tmp_path):
    repo = _make_stub_repo(tmp_path)
    yaml_text = "domain: walmart-opd\nname: opd_model\ntables:\n  - name: deliveries\n"
    run_dir = _make_run_dir(tmp_path, yaml_text)
    proc = _invoke(repo, run_dir)
    assert proc.returncode == 0, proc.stdout + proc.stderr

    argv = _stub_argv(repo)
    assert argv[argv.index("--domain") + 1] == "walmart-opd"
    # the web-managed YAML replaces the repo's model for that domain, and persists
    persisted = repo / "context" / "semantic_models" / "walmart-opd.yaml"
    assert persisted.read_text() == yaml_text


def test_adapter_backend_and_extra_args(tmp_path):
    repo = _make_stub_repo(tmp_path)
    run_dir = _make_run_dir(tmp_path, "name: m\n")
    proc = _invoke(repo, run_dir, extra_env={
        "PIPELINE_BACKEND": "anthropic",
        "PIPELINE_EXTRA_ARGS": "--dry-run --no-upload",
    })
    assert proc.returncode == 0, proc.stdout + proc.stderr
    argv = _stub_argv(repo)
    assert argv[argv.index("--backend") + 1] == "anthropic"
    assert "--dry-run" in argv and "--no-upload" in argv


def test_adapter_propagates_pipeline_failure(tmp_path):
    repo = _make_stub_repo(tmp_path)
    (repo / "src" / "main.py").write_text("import sys; sys.exit(7)")
    run_dir = _make_run_dir(tmp_path, "name: m\n")
    proc = _invoke(repo, run_dir)
    assert proc.returncode == 7
    assert not (run_dir / "report.md").exists()


def test_adapter_fails_when_no_markdown_produced(tmp_path):
    repo = _make_stub_repo(tmp_path)
    (repo / "src" / "main.py").write_text("import sys; sys.exit(0)")
    run_dir = _make_run_dir(tmp_path, "name: m\n")
    proc = _invoke(repo, run_dir)
    assert proc.returncode == 3
    assert "no .md" in proc.stdout
