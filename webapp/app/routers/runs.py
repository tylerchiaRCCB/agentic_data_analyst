from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.config import settings
from app.db import get_db
from app.models import ACTIVE_RUN_STATUSES, RUN_STATUSES, Run, SemanticView, User
from app.security.csrf import verify_csrf
from app.security.deps import can_manage, require_role
from app.services.markdown import render_report
from app.services.runs import (
    artifact_path,
    enqueue_run,
    list_artifacts,
    report_text,
    tail_log,
)
from app.templating import render

router = APIRouter()


def _get_run(db: DbSession, run_id: str) -> Run:
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404)
    return run


def _active_views(db: DbSession, user: User) -> list[SemanticView]:
    """Runnable semantic views owned by the user (admins see all)."""
    q = (
        select(SemanticView)
        .where(SemanticView.is_archived == False, SemanticView.current_version_id.is_not(None))  # noqa: E712
        .order_by(SemanticView.name)
    )
    if user.role != "admin":
        q = q.where(
            (SemanticView.created_by == user.id) | (SemanticView.created_by.is_(None))
        )
    return db.scalars(q).all()


@router.get("/runs")
def list_runs(
    request: Request,
    status: str = "",
    view: int | None = None,
    page: int = 1,
    user: User = Depends(require_role("viewer")),
    db: DbSession = Depends(get_db),
):
    per_page = 10
    if page < 1:
        page = 1
    q_base = select(Run)
    if status in RUN_STATUSES:
        q_base = q_base.where(Run.status == status)
    if view:
        q_base = q_base.where(Run.semantic_view_id == view)
    total = db.scalar(select(func.count()).select_from(q_base.subquery()))
    runs = db.scalars(q_base.order_by(Run.created_at.desc()).limit(per_page).offset((page - 1) * per_page)).all()
    total_pages = max(1, (total + per_page - 1) // per_page)
    ctx = dict(runs=runs, views=_active_views(db, user), statuses=RUN_STATUSES,
               sel_status=status, sel_view=view,
               page=page, total_pages=total_pages)
    if request.headers.get("HX-Request"):
        return render(request, "fragments/runs_table.html", **ctx)
    return render(request, "runs/list.html", **ctx)


@router.get("/runs/new")
def new_run_page(
    request: Request,
    view: int | None = None,
    user: User = Depends(require_role("analyst")),
    db: DbSession = Depends(get_db),
):
    return render(request, "runs/new.html", views=_active_views(db, user), sel_view=view)


@router.post("/runs", dependencies=[Depends(verify_csrf)])
def create_run(
    request: Request,
    question: str = Form(...),
    semantic_view_id: int = Form(...),
    backend: str = Form(""),
    user: User = Depends(require_role("analyst")),
    db: DbSession = Depends(get_db),
):
    view = db.get(SemanticView, semantic_view_id)
    if view is None or view.is_archived or view.current_version is None \
            or (view.created_by is not None and not can_manage(user, view.created_by)):
        raise HTTPException(status_code=400, detail="Invalid semantic view")
    if not question.strip():
        return render(request, "runs/new.html", status_code=400, views=_active_views(db, user),
                      sel_view=semantic_view_id, flash="Question is required.", flash_kind="error")
    run = enqueue_run(db, question, view, view.current_version, user=user, backend=backend)
    return RedirectResponse(f"/runs/{run.id}", status_code=303)


@router.get("/runs/{run_id}")
def run_detail(
    request: Request,
    run_id: str,
    user: User = Depends(require_role("viewer")),
    db: DbSession = Depends(get_db),
):
    run = _get_run(db, run_id)
    report_html = None
    if run.status == "succeeded":
        text = report_text(run)
        if text is not None:
            report_html = render_report(text)
    log_text, log_offset = tail_log(run, 0)
    return render(
        request,
        "runs/detail.html",
        run=run,
        report_html=report_html,
        log_text=log_text,
        log_offset=log_offset,
        artifacts=list_artifacts(run),
        is_active=run.status in ACTIVE_RUN_STATUSES,
        can_cancel=run.status in ACTIVE_RUN_STATUSES
        and (user.role == "admin" or can_manage(user, run.triggered_by)),
        can_rerun=user.role in ("analyst", "admin"),
    )


@router.get("/fragments/runs/{run_id}/status")
def run_status_fragment(
    request: Request,
    run_id: str,
    user: User = Depends(require_role("viewer")),
    db: DbSession = Depends(get_db),
):
    run = _get_run(db, run_id)
    resp = render(
        request,
        "fragments/run_status.html",
        run=run,
        is_active=run.status in ACTIVE_RUN_STATUSES,
    )
    # The page only polls this fragment while it believes the run is active, so a
    # finished status here means the run just completed: reload to show the report.
    if run.status not in ACTIVE_RUN_STATUSES and request.headers.get("HX-Request"):
        resp.headers["HX-Refresh"] = "true"
    return resp


@router.get("/fragments/runs/{run_id}/log")
def run_log_fragment(
    request: Request,
    run_id: str,
    offset: int = 0,
    user: User = Depends(require_role("viewer")),
    db: DbSession = Depends(get_db),
):
    run = _get_run(db, run_id)
    text, new_offset = tail_log(run, max(0, offset))
    return render(
        request,
        "fragments/run_log.html",
        run=run,
        chunk=text,
        offset=new_offset,
        is_active=run.status in ACTIVE_RUN_STATUSES,
    )


@router.get("/runs/{run_id}/report")
def run_report(
    request: Request,
    run_id: str,
    user: User = Depends(require_role("viewer")),
    db: DbSession = Depends(get_db),
):
    run = _get_run(db, run_id)
    text = report_text(run)
    if text is None:
        raise HTTPException(status_code=404, detail="No report yet")
    return render(request, "runs/report.html", run=run, report_html=render_report(text))


@router.get("/runs/{run_id}/report/download")
def download_report(
    run_id: str,
    user: User = Depends(require_role("viewer")),
    db: DbSession = Depends(get_db),
):
    run = _get_run(db, run_id)
    path = settings.data_dir / run.report_path
    if not run.report_path or not path.exists():
        raise HTTPException(status_code=404)
    return FileResponse(
        path,
        media_type="text/markdown; charset=utf-8",
        filename=f"report-{run.id[:8]}.md",
    )


@router.get("/runs/{run_id}/log/download")
def download_log(
    run_id: str,
    user: User = Depends(require_role("viewer")),
    db: DbSession = Depends(get_db),
):
    run = _get_run(db, run_id)
    path = settings.data_dir / run.log_path
    if not run.log_path or not path.exists():
        raise HTTPException(status_code=404)
    return FileResponse(path, media_type="text/plain; charset=utf-8", filename=f"run-{run.id[:8]}.log")


@router.get("/runs/{run_id}/artifacts/{filename}")
def download_artifact(
    run_id: str,
    filename: str,
    user: User = Depends(require_role("viewer")),
    db: DbSession = Depends(get_db),
):
    run = _get_run(db, run_id)
    path = artifact_path(run, filename)
    if path is None:
        raise HTTPException(status_code=404)
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=filename,
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.post("/runs/{run_id}/cancel", dependencies=[Depends(verify_csrf)])
def cancel_run(
    run_id: str,
    user: User = Depends(require_role("analyst")),
    db: DbSession = Depends(get_db),
):
    run = _get_run(db, run_id)
    if not can_manage(user, run.triggered_by):
        raise HTTPException(status_code=403, detail="You can only cancel your own runs")
    if run.status in ACTIVE_RUN_STATUSES:
        run.cancel_requested = True
        db.commit()
    return RedirectResponse(f"/runs/{run.id}", status_code=303)


@router.post("/runs/{run_id}/rerun", dependencies=[Depends(verify_csrf)])
def rerun(
    run_id: str,
    user: User = Depends(require_role("analyst")),
    db: DbSession = Depends(get_db),
):
    old = _get_run(db, run_id)
    if not can_manage(user, old.view.created_by):
        raise HTTPException(status_code=403, detail="You can only re-run your own semantic views")
    new = enqueue_run(db, old.question, old.view, old.version, user=user)
    return RedirectResponse(f"/runs/{new.id}", status_code=303)
