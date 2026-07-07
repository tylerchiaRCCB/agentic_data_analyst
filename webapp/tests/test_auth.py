from tests.conftest import PASSWORD, csrf_for, login, make_user


def test_login_logout_flow(client, db):
    make_user(db, "alice", "analyst")
    # bad password
    resp = client.post("/login", data={"username": "alice", "password": "wrong"})
    assert resp.status_code == 401
    # good password
    resp = client.post("/login", data={"username": "alice", "password": PASSWORD})
    assert resp.status_code == 303
    # dashboard now accessible
    assert client.get("/").status_code == 200
    # logout
    resp = client.post("/logout", data={"csrf_token": csrf_for(client)})
    assert resp.status_code == 303
    assert client.get("/").status_code == 303  # redirected to login


def test_login_rate_limit(client, db):
    make_user(db, "alice", "analyst")
    for _ in range(5):
        client.post("/login", data={"username": "alice", "password": "wrong"})
    resp = client.post("/login", data={"username": "alice", "password": PASSWORD})
    assert resp.status_code == 429


def test_viewer_cannot_reach_analyst_routes(client, db):
    login(client, db, "vera", role="viewer")
    assert client.get("/runs/new").status_code == 403
    assert client.get("/semantic-views/new").status_code == 403
    assert client.get("/schedules/new").status_code == 403
    assert client.get("/admin/users").status_code == 403
    # but can view lists
    assert client.get("/runs").status_code == 200
    assert client.get("/semantic-views").status_code == 200


def test_analyst_cannot_reach_admin(client, db):
    login(client, db, "alice", role="analyst")
    assert client.get("/admin/users").status_code == 403


def test_csrf_required_on_posts(client, db):
    login(client, db, "alice", role="analyst")
    resp = client.post("/logout")  # no token
    assert resp.status_code == 403


def test_deactivated_user_session_revoked(client, db):
    user = login(client, db, "alice", role="analyst")
    user.is_active = False
    db.commit()
    assert client.get("/").status_code == 303  # back to login
