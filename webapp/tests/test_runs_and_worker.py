import time

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Run
from app.worker.loop import _children, recover_orphans, tick
from tests.conftest import csrf_for, login

GOOD_YAML = "name: sales_model\ntables:\n  - name: orders\n"


def _create_view(client, token) -> str:
    resp = client.post("/semantic-views", data={
        "csrf_token": token, "name": "sales", "yaml_text": GOOD_YAML,
    })
    assert resp.status_code == 303
    return resp.headers["location"]


def _enqueue(client, db, token, question: str) -> str:
    from app.models import SemanticView
    view = db.query(SemanticView).first()
    resp = client.post("/runs", data={
        "csrf_token": token, "question": question, "semantic_view_id": view.id,
    })
    assert resp.status_code == 303
    return resp.headers["location"].split("/runs/")[1]


def _worker_until(predicate, timeout=30.0):
    """Drive worker ticks until predicate(run rows) is true."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        wdb = SessionLocal()
        try:
            tick(wdb)
            runs = wdb.scalars(select(Run)).all()
            if predicate(runs):
                return runs
        finally:
            wdb.close()
        time.sleep(0.2)
    raise AssertionError("worker did not reach expected state in time")


def test_run_lifecycle_success(client, db):
    login(client, db, "alice", role="analyst")
    token = csrf_for(client)
    _create_view(client, token)
    run_id = _enqueue(client, db, token, "How did revenue trend?")

    _worker_until(lambda runs: runs[0].status == "succeeded")

    # detail page shows the rendered, sanitized report
    page = client.get(f"/runs/{run_id}")
    assert page.status_code == 200
    assert "Key Findings" in page.text
    # log tail endpoint works from offset 0
    frag = client.get(f"/fragments/runs/{run_id}/log?offset=0")
    assert "fake-pipeline" in frag.text
    # artifact download + traversal protection
    assert client.get(f"/runs/{run_id}/artifacts/data_summary.csv").status_code == 200
    assert client.get(f"/runs/{run_id}/artifacts/..%2Frun.log").status_code == 404
    # report download
    assert client.get(f"/runs/{run_id}/report/download").status_code == 200


def test_run_failure_marks_failed(client, db):
    login(client, db, "alice", role="analyst")
    token = csrf_for(client)
    _create_view(client, token)
    _enqueue(client, db, token, "Please FAIL this run")

    runs = _worker_until(lambda runs: runs[0].status not in ("queued", "running"))
    assert runs[0].status == "failed"
    assert runs[0].exit_code == 1


def test_cancel_running_run(client, db):
    login(client, db, "alice", role="analyst")
    token = csrf_for(client)
    _create_view(client, token)
    run_id = _enqueue(client, db, token, "HANG forever please")

    _worker_until(lambda runs: runs[0].status == "running")
    resp = client.post(f"/runs/{run_id}/cancel", data={"csrf_token": token})
    assert resp.status_code == 303
    runs = _worker_until(lambda runs: runs[0].status not in ("queued", "running"))
    assert runs[0].status == "cancelled"


def test_orphan_recovery(client, db):
    login(client, db, "alice", role="analyst")
    token = csrf_for(client)
    _create_view(client, token)
    run_id = _enqueue(client, db, token, "anything")

    # Simulate a dead worker: mark running with a bogus pid, no tracked child
    run = db.get(Run, run_id)
    run.status = "running"
    run.pid = 99999999
    db.commit()
    _children.clear()

    wdb = SessionLocal()
    try:
        recover_orphans(wdb)
        assert wdb.get(Run, run_id).status == "failed"
    finally:
        wdb.close()


def test_viewer_cannot_enqueue_or_cancel(client, db):
    login(client, db, "vera", role="viewer")
    token = csrf_for(client)
    resp = client.post("/runs", data={
        "csrf_token": token, "question": "q", "semantic_view_id": 1,
    })
    assert resp.status_code == 403
