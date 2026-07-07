"""Single-process job dispatcher: the `runs` table is the queue.

Exactly one worker process runs this loop, which makes double-firing schedules
impossible by construction. Web workers only ever INSERT queued runs.
"""

import logging
import os
import signal
import subprocess
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from app.config import settings
from app.db import SessionLocal
from app.models import ACTIVE_RUN_STATUSES, LoginAttempt, Run, Schedule, Session, utcnow
from app.services.runs import enqueue_run, run_dir
from app.services.schedules import reschedule
from app.worker import pipeline_adapter

log = logging.getLogger("worker")

# run_id -> Popen, for children launched by this worker process
_children: dict[str, subprocess.Popen] = {}

_GRACE_SECONDS = 10


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    return True


def _killpg(pid: int, sig: int) -> None:
    try:
        os.killpg(os.getpgid(pid), sig)
    except (ProcessLookupError, PermissionError):
        pass


def _append_log(run: Run, message: str) -> None:
    if run.log_path:
        path = settings.data_dir / run.log_path
        with path.open("a", encoding="utf-8") as f:
            f.write(f"\n[worker] {message}\n")


def recover_orphans(db) -> None:
    """Mark runs 'running' under a previous worker instance as failed if their pid is gone."""
    for run in db.scalars(select(Run).where(Run.status == "running")).all():
        if run.id in _children:
            continue
        if run.pid is None or not _pid_alive(run.pid):
            run.status = "failed"
            run.finished_at = utcnow()
            run.error_summary = "Orphaned by worker restart."
            _append_log(run, "orphaned by worker restart; marked failed")
            log.warning("recovered orphan run %s", run.id)
    db.commit()


def dispatch_schedules(db) -> None:
    now = utcnow()
    due = db.scalars(
        select(Schedule).where(Schedule.enabled == True, Schedule.next_run_at <= now)  # noqa: E712
    ).all()
    for sched in due:
        view = sched.view
        version = None
        if sched.pin_version_id is not None:
            from app.models import SemanticViewVersion

            version = db.get(SemanticViewVersion, sched.pin_version_id)
        else:
            version = view.current_version
        if version is None or view.is_archived:
            log.warning("schedule %s skipped: view archived or no version", sched.id)
            reschedule(sched)
            db.commit()
            continue

        if sched.overlap_policy == "skip":
            active = db.scalar(
                select(Run.id).where(
                    Run.schedule_id == sched.id, Run.status.in_(ACTIVE_RUN_STATUSES)
                )
            )
            if active:
                log.info("schedule %s skipped: previous run still active", sched.id)
                reschedule(sched)
                db.commit()
                continue

        run = enqueue_run(
            db, sched.question, view, version, user=None, schedule_id=sched.id
        )
        reschedule(sched)
        db.commit()
        log.info("schedule %s fired -> run %s", sched.id, run.id)


def launch_queued(db) -> None:
    while len(_children) < settings.max_concurrent_runs:
        run = db.scalars(
            select(Run).where(Run.status == "queued").order_by(Run.created_at).limit(1)
        ).first()
        if run is None:
            return
        if run.cancel_requested:
            run.status = "cancelled"
            run.finished_at = utcnow()
            db.commit()
            continue
        rdir = run_dir(run.id)
        try:
            proc = pipeline_adapter.launch(rdir)
        except (OSError, ValueError) as e:
            run.status = "failed"
            run.finished_at = utcnow()
            run.error_summary = f"Failed to launch pipeline: {e}"
            db.commit()
            log.error("run %s failed to launch: %s", run.id, e)
            continue
        run.status = "running"
        run.started_at = utcnow()
        run.pid = proc.pid
        db.commit()
        _children[run.id] = proc
        log.info("run %s started (pid %s)", run.id, proc.pid)


def reap_children(db) -> None:
    for run_id, proc in list(_children.items()):
        run = db.get(Run, run_id)
        if run is None:
            _killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            del _children[run_id]
            continue

        code = proc.poll()
        if code is not None:
            del _children[run_id]
            run.exit_code = code
            run.finished_at = utcnow()
            if run.cancel_requested:
                run.status = "cancelled"
            elif code == 0:
                report = settings.data_dir / run.report_path
                if report.exists():
                    run.status = "succeeded"
                else:
                    run.status = "failed"
                    run.error_summary = "Pipeline exited 0 but produced no report.md."
            else:
                run.status = "failed"
                run.error_summary = f"Pipeline exited with code {code}."
            db.commit()
            log.info("run %s finished: %s", run_id, run.status)
            continue

        # Still running: cancellation and timeout
        if run.cancel_requested:
            _append_log(run, "cancellation requested; sending SIGTERM")
            _killpg(proc.pid, signal.SIGTERM)
            _await_or_kill(proc)
            continue  # next tick reaps it

        started = _aware(run.started_at)
        if started and utcnow() - started > timedelta(minutes=settings.run_timeout_minutes):
            _append_log(run, f"timeout after {settings.run_timeout_minutes}m; sending SIGTERM")
            _killpg(proc.pid, signal.SIGTERM)
            _await_or_kill(proc)
            run.status = "timed_out"
            run.finished_at = utcnow()
            run.exit_code = proc.poll()
            run.error_summary = f"Run exceeded {settings.run_timeout_minutes} minute timeout."
            db.commit()
            del _children[run_id]
            log.warning("run %s timed out", run_id)


def _await_or_kill(proc: subprocess.Popen) -> None:
    try:
        proc.wait(timeout=_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        _killpg(proc.pid, signal.SIGKILL)
        proc.wait()


def housekeeping(db) -> None:
    now = utcnow()
    db.execute(delete(Session).where(Session.expires_at < now))
    db.execute(
        delete(LoginAttempt).where(LoginAttempt.created_at < now - timedelta(hours=24))
    )
    db.commit()


def heartbeat() -> None:
    settings.worker_heartbeat_file.touch()


def tick(db) -> None:
    dispatch_schedules(db)
    launch_queued(db)
    reap_children(db)
    heartbeat()


def run_forever() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log.info("worker starting (max_concurrent=%s)", settings.max_concurrent_runs)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.runs_dir.mkdir(parents=True, exist_ok=True)

    db = SessionLocal()
    try:
        recover_orphans(db)
    finally:
        db.close()

    last_housekeeping = 0.0
    while True:
        db = SessionLocal()
        try:
            tick(db)
            if time.monotonic() - last_housekeeping > 300:
                housekeeping(db)
                last_housekeeping = time.monotonic()
        except Exception:
            log.exception("worker tick failed")
        finally:
            db.close()
        time.sleep(settings.worker_poll_seconds)
