import shutil
from pathlib import Path

from sqlalchemy.orm import Session as DbSession

from app.config import settings
from app.models import Run, SemanticView, SemanticViewVersion, User


def run_dir(run_id: str) -> Path:
    return settings.runs_dir / run_id


def enqueue_run(
    db: DbSession,
    question: str,
    view: SemanticView,
    version: SemanticViewVersion,
    user: User | None = None,
    schedule_id: int | None = None,
) -> Run:
    """Create a queued run with a self-contained run directory. The worker picks it up."""
    run = Run(
        question=question.strip(),
        semantic_view_id=view.id,
        semantic_view_version_id=version.id,
        schedule_id=schedule_id,
        triggered_by=user.id if user else None,
    )
    db.add(run)
    db.flush()

    rdir = run_dir(run.id)
    rdir.mkdir(parents=True, exist_ok=True)
    (rdir / "artifacts").mkdir(exist_ok=True)
    # Copy the pinned semantic view so the run is reproducible even if versions change
    shutil.copyfile(settings.data_dir / version.file_path, rdir / "input.yaml")
    (rdir / "question.txt").write_text(run.question, encoding="utf-8")

    run.log_path = f"runs/{run.id}/run.log"
    run.report_path = f"runs/{run.id}/report.md"
    db.commit()
    return run


def tail_log(run: Run, offset: int) -> tuple[str, int]:
    """Read the run log from byte offset; returns (new_text, new_offset)."""
    path = settings.data_dir / run.log_path if run.log_path else None
    if path is None or not path.exists():
        return "", offset
    size = path.stat().st_size
    if offset >= size:
        return "", size
    with path.open("rb") as f:
        f.seek(offset)
        chunk = f.read()
    return chunk.decode("utf-8", errors="replace"), size


def report_text(run: Run) -> str | None:
    path = settings.data_dir / run.report_path if run.report_path else None
    if path is None or not path.exists():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def artifact_path(run: Run, filename: str) -> Path | None:
    """Resolve an artifact download safely (no traversal)."""
    if "/" in filename or "\\" in filename or filename.startswith("."):
        return None
    base = (run_dir(run.id) / "artifacts").resolve()
    p = (base / filename).resolve()
    if not p.is_relative_to(base) or not p.is_file():
        return None
    return p


def list_artifacts(run: Run) -> list[str]:
    base = run_dir(run.id) / "artifacts"
    if not base.is_dir():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_file())
