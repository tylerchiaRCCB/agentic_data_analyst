import os
import sys
from pathlib import Path

# Isolate test data before app modules import settings
_TEST_DATA = Path(__file__).parent / "_data"
os.environ.setdefault("ANALYST_DATA_DIR", str(_TEST_DATA))
os.environ.setdefault("ANALYST_SECRET_KEY", "test-secret")
os.environ.setdefault(
    "ANALYST_PIPELINE_CMD", f"{sys.executable} {Path(__file__).parent / 'fake_pipeline.py'}"
)
os.environ.setdefault("ANALYST_WORKER_POLL_SECONDS", "0.1")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402
from app.security.passwords import hash_password  # noqa: E402

PASSWORD = "correct-horse-battery"


@pytest.fixture(autouse=True)
def fresh_db():
    _TEST_DATA.mkdir(exist_ok=True)
    # semantic_views <-> semantic_view_versions have a circular FK; drop with FKs off
    with engine.begin() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
        Base.metadata.drop_all(bind=conn)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.close()


def make_user(db, username: str, role: str) -> User:
    user = User(
        username=username,
        role=role,
        display_name=username,
        password_hash=hash_password(PASSWORD),
    )
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def client():
    return TestClient(app, follow_redirects=False)


def login(client: TestClient, db, username: str = "alice", role: str = "analyst") -> User:
    user = make_user(db, username, role)
    resp = client.post("/login", data={"username": username, "password": PASSWORD})
    assert resp.status_code == 303, resp.text
    return user


def csrf_for(client: TestClient) -> str:
    from app.config import settings
    from app.security.csrf import csrf_token_for

    return csrf_token_for(client.cookies.get(settings.session_cookie, ""))
