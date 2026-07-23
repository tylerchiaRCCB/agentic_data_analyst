from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.db import get_db
from app.models import Run, Schedule, SemanticView, User
from app.security.deps import require_role
from app.services.repo_sync import sync_repo_to_db
from app.templating import render

router = APIRouter()


def _dashboard_ctx(db: DbSession, user: User) -> dict:
    sync_repo_to_db(db)
    recent_runs = db.scalars(select(Run).order_by(Run.created_at.desc()).limit(10)).all()
    upcoming = db.scalars(
        select(Schedule)
        .where(Schedule.enabled == True)  # noqa: E712
        .order_by(Schedule.next_run_at)
        .limit(5)
    ).all()
    views_q = (
        select(SemanticView)
        .where(SemanticView.is_archived == False, SemanticView.current_version_id.is_not(None))  # noqa: E712
        .order_by(SemanticView.name)
    )
    # Auto-imported repo views have no owner — show them to everyone
    if user.role != "admin":
        views_q = views_q.where(
            (SemanticView.created_by == user.id) | (SemanticView.created_by.is_(None))
        )
    views = db.scalars(views_q).all()
    return dict(recent_runs=recent_runs, upcoming=upcoming, views=views)


@router.get("/")
def dashboard(
    request: Request,
    user: User = Depends(require_role("viewer")),
    db: DbSession = Depends(get_db),
):
    return render(request, "dashboard/index.html", **_dashboard_ctx(db, user))


@router.get("/fragments/dashboard/recent-runs")
def recent_runs_fragment(
    request: Request,
    user: User = Depends(require_role("viewer")),
    db: DbSession = Depends(get_db),
):
    runs = db.scalars(select(Run).order_by(Run.created_at.desc()).limit(10)).all()
    return render(request, "fragments/runs_table.html", runs=runs)
