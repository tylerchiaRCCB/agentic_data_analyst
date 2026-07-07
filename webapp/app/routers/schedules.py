from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.config import settings
from app.db import get_db
from app.models import Run, Schedule, SemanticView, User
from app.security.csrf import verify_csrf
from app.security.deps import can_manage, require_role
from app.services.runs import enqueue_run
from app.services.schedules import (
    CronValidationError,
    next_fire_utc,
    preview_fire_times,
    validate_cron,
)
from app.templating import render

router = APIRouter()


def _get_schedule(db: DbSession, schedule_id: int) -> Schedule:
    sched = db.get(Schedule, schedule_id)
    if sched is None:
        raise HTTPException(status_code=404)
    return sched


def _require_manage(user: User, sched: Schedule) -> None:
    if not can_manage(user, sched.created_by):
        raise HTTPException(status_code=403, detail="You can only manage your own schedules")


def _active_views(db: DbSession, user: User) -> list[SemanticView]:
    """Schedulable semantic views owned by the user (admins see all)."""
    q = (
        select(SemanticView)
        .where(SemanticView.is_archived == False, SemanticView.current_version_id.is_not(None))  # noqa: E712
        .order_by(SemanticView.name)
    )
    if user.role != "admin":
        q = q.where(SemanticView.created_by == user.id)
    return db.scalars(q).all()


def _form_ctx(db: DbSession, user: User, sched: Schedule | None = None) -> dict:
    return dict(views=_active_views(db, user), sched=sched, default_tz=settings.default_timezone)


@router.get("/schedules")
def list_schedules(
    request: Request,
    user: User = Depends(require_role("viewer")),
    db: DbSession = Depends(get_db),
):
    schedules = db.scalars(select(Schedule).order_by(Schedule.name)).all()
    return render(request, "schedules/list.html", schedules=schedules)


@router.get("/schedules/new")
def new_schedule_page(
    request: Request,
    user: User = Depends(require_role("analyst")),
    db: DbSession = Depends(get_db),
):
    return render(request, "schedules/form.html", **_form_ctx(db, user))


@router.post("/schedules", dependencies=[Depends(verify_csrf)])
def create_schedule(
    request: Request,
    name: str = Form(...),
    question: str = Form(...),
    semantic_view_id: int = Form(...),
    cron_expr: str = Form(...),
    timezone: str = Form(...),
    overlap_policy: str = Form("skip"),
    user: User = Depends(require_role("analyst")),
    db: DbSession = Depends(get_db),
):
    view = db.get(SemanticView, semantic_view_id)
    if view is None or view.is_archived or not can_manage(user, view.created_by):
        raise HTTPException(status_code=400, detail="Invalid semantic view")
    try:
        validate_cron(cron_expr.strip(), timezone.strip())
    except CronValidationError as e:
        return render(request, "schedules/form.html", status_code=400,
                      flash=str(e), flash_kind="error", **_form_ctx(db, user))
    sched = Schedule(
        name=name.strip(),
        question=question.strip(),
        semantic_view_id=view.id,
        cron_expr=cron_expr.strip(),
        timezone=timezone.strip(),
        overlap_policy=overlap_policy if overlap_policy in ("skip", "queue") else "skip",
        created_by=user.id,
    )
    sched.next_run_at = next_fire_utc(sched.cron_expr, sched.timezone)
    db.add(sched)
    db.commit()
    return RedirectResponse(f"/schedules/{sched.id}", status_code=303)


@router.get("/schedules/{schedule_id}")
def schedule_detail(
    request: Request,
    schedule_id: int,
    user: User = Depends(require_role("viewer")),
    db: DbSession = Depends(get_db),
):
    sched = _get_schedule(db, schedule_id)
    runs = db.scalars(
        select(Run).where(Run.schedule_id == sched.id).order_by(Run.created_at.desc()).limit(50)
    ).all()
    return render(request, "schedules/detail.html", sched=sched, runs=runs,
                  can_edit=can_manage(user, sched.created_by))


@router.get("/schedules/{schedule_id}/edit")
def edit_schedule_page(
    request: Request,
    schedule_id: int,
    user: User = Depends(require_role("analyst")),
    db: DbSession = Depends(get_db),
):
    sched = _get_schedule(db, schedule_id)
    _require_manage(user, sched)
    return render(request, "schedules/form.html", **_form_ctx(db, user, sched))


@router.post("/schedules/{schedule_id}", dependencies=[Depends(verify_csrf)])
def update_schedule(
    request: Request,
    schedule_id: int,
    name: str = Form(...),
    question: str = Form(...),
    semantic_view_id: int = Form(...),
    cron_expr: str = Form(...),
    timezone: str = Form(...),
    overlap_policy: str = Form("skip"),
    user: User = Depends(require_role("analyst")),
    db: DbSession = Depends(get_db),
):
    sched = _get_schedule(db, schedule_id)
    _require_manage(user, sched)
    view = db.get(SemanticView, semantic_view_id)
    if view is None or view.is_archived or not can_manage(user, view.created_by):
        raise HTTPException(status_code=400, detail="Invalid semantic view")
    try:
        validate_cron(cron_expr.strip(), timezone.strip())
    except CronValidationError as e:
        return render(request, "schedules/form.html", status_code=400,
                      flash=str(e), flash_kind="error", **_form_ctx(db, user, sched))
    sched.name = name.strip()
    sched.question = question.strip()
    sched.semantic_view_id = view.id
    sched.cron_expr = cron_expr.strip()
    sched.timezone = timezone.strip()
    sched.overlap_policy = overlap_policy if overlap_policy in ("skip", "queue") else "skip"
    sched.next_run_at = next_fire_utc(sched.cron_expr, sched.timezone)
    db.commit()
    return RedirectResponse(f"/schedules/{sched.id}", status_code=303)


@router.post("/schedules/{schedule_id}/toggle", dependencies=[Depends(verify_csrf)])
def toggle_schedule(
    schedule_id: int,
    user: User = Depends(require_role("analyst")),
    db: DbSession = Depends(get_db),
):
    sched = _get_schedule(db, schedule_id)
    _require_manage(user, sched)
    sched.enabled = not sched.enabled
    if sched.enabled:
        sched.next_run_at = next_fire_utc(sched.cron_expr, sched.timezone)
    db.commit()
    return RedirectResponse("/schedules", status_code=303)


@router.post("/schedules/{schedule_id}/run-now", dependencies=[Depends(verify_csrf)])
def run_now(
    schedule_id: int,
    user: User = Depends(require_role("analyst")),
    db: DbSession = Depends(get_db),
):
    sched = _get_schedule(db, schedule_id)
    _require_manage(user, sched)
    view = sched.view
    version = view.current_version
    if sched.pin_version_id is not None:
        from app.models import SemanticViewVersion

        version = db.get(SemanticViewVersion, sched.pin_version_id)
    if version is None:
        raise HTTPException(status_code=400, detail="Schedule has no usable semantic view version")
    run = enqueue_run(db, sched.question, view, version, user=user, schedule_id=sched.id)
    return RedirectResponse(f"/runs/{run.id}", status_code=303)


@router.post("/schedules/{schedule_id}/delete", dependencies=[Depends(verify_csrf)])
def delete_schedule(
    schedule_id: int,
    user: User = Depends(require_role("analyst")),
    db: DbSession = Depends(get_db),
):
    sched = _get_schedule(db, schedule_id)
    _require_manage(user, sched)
    db.delete(sched)
    db.commit()
    return RedirectResponse("/schedules", status_code=303)


@router.get("/fragments/schedules/preview")
def cron_preview(
    request: Request,
    cron_expr: str = "",
    timezone: str = "",
    user: User = Depends(require_role("analyst")),
):
    tz = timezone.strip() or settings.default_timezone
    try:
        validate_cron(cron_expr.strip(), tz)
        times = preview_fire_times(cron_expr.strip(), tz)
        return render(request, "fragments/cron_preview.html", times=times, tz=tz, error=None)
    except CronValidationError as e:
        return render(request, "fragments/cron_preview.html", times=[], tz=tz, error=str(e))
