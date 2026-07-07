from datetime import timedelta

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Run, Schedule, utcnow
from app.services.schedules import CronValidationError, next_fire_utc, validate_cron
from app.worker.loop import dispatch_schedules
from tests.conftest import csrf_for, login

GOOD_YAML = "name: sales_model\ntables:\n  - name: orders\n"


def test_cron_validation():
    validate_cron("0 8 * * 1", "America/Los_Angeles")
    with pytest.raises(CronValidationError):
        validate_cron("not a cron", "America/Los_Angeles")
    with pytest.raises(CronValidationError):
        validate_cron("0 8 * * 1", "Mars/Olympus_Mons")


def test_next_fire_is_future_utc():
    nxt = next_fire_utc("*/5 * * * *", "America/New_York")
    assert nxt > utcnow()
    assert nxt.tzinfo is not None


def _setup_schedule(client, db, question="scheduled question") -> Schedule:
    login(client, db, "alice", role="analyst")
    token = csrf_for(client)
    resp = client.post("/semantic-views", data={
        "csrf_token": token, "name": "sales", "yaml_text": GOOD_YAML,
    })
    assert resp.status_code == 303
    from app.models import SemanticView
    view = db.query(SemanticView).first()
    resp = client.post("/schedules", data={
        "csrf_token": token, "name": "weekly", "question": question,
        "semantic_view_id": view.id, "cron_expr": "0 8 * * 1",
        "timezone": "America/Los_Angeles", "overlap_policy": "skip",
    })
    assert resp.status_code == 303
    return db.scalars(select(Schedule)).first()


def test_schedule_fires_when_due(client, db):
    sched = _setup_schedule(client, db)
    sched.next_run_at = utcnow() - timedelta(minutes=1)
    db.commit()

    wdb = SessionLocal()
    try:
        dispatch_schedules(wdb)
        runs = wdb.scalars(select(Run)).all()
        assert len(runs) == 1
        assert runs[0].schedule_id == sched.id
        assert runs[0].question == "scheduled question"
        refreshed = wdb.get(Schedule, sched.id)
        next_at = refreshed.next_run_at
        from datetime import timezone as _tz
        if next_at.tzinfo is None:
            next_at = next_at.replace(tzinfo=_tz.utc)
        assert next_at > utcnow()
    finally:
        wdb.close()


def test_overlap_skip_policy(client, db):
    sched = _setup_schedule(client, db)
    sched.next_run_at = utcnow() - timedelta(minutes=1)
    db.commit()

    wdb = SessionLocal()
    try:
        dispatch_schedules(wdb)  # fires -> 1 queued run
        s = wdb.get(Schedule, sched.id)
        s.next_run_at = utcnow() - timedelta(minutes=1)  # force due again
        wdb.commit()
        dispatch_schedules(wdb)  # previous run still queued -> skip
        assert len(wdb.scalars(select(Run)).all()) == 1
    finally:
        wdb.close()


def test_invalid_cron_rejected_by_form(client, db):
    _setup_schedule(client, db)
    token = csrf_for(client)
    from app.models import SemanticView
    view = db.query(SemanticView).first()
    resp = client.post("/schedules", data={
        "csrf_token": token, "name": "bad", "question": "q",
        "semantic_view_id": view.id, "cron_expr": "99 99 * * *",
        "timezone": "America/Los_Angeles",
    })
    assert resp.status_code == 400


def test_cron_preview_fragment(client, db):
    login(client, db, "alice", role="analyst")
    resp = client.get("/fragments/schedules/preview?cron_expr=0 8 * * 1&timezone=UTC")
    assert resp.status_code == 200 and "Next fires" in resp.text
