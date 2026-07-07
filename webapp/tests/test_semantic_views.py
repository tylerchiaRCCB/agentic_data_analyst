import pytest

from app.services.semantic_views import YamlValidationError, validate_yaml
from tests.conftest import csrf_for, login

GOOD_YAML = "name: sales_model\ntables:\n  - name: orders\n"


def test_validate_yaml_accepts_semantic_model():
    status, warnings = validate_yaml(GOOD_YAML.encode())
    assert status == "valid" and warnings == []


def test_validate_yaml_warns_on_missing_keys():
    status, warnings = validate_yaml(b"foo: bar")
    assert status == "warnings" and len(warnings) == 2


@pytest.mark.parametrize(
    "raw",
    [
        b"- just\n- a\n- list",
        b"key: [unclosed",
        b"\xff\xfe binary",
    ],
)
def test_validate_yaml_rejects_bad_input(raw):
    with pytest.raises(YamlValidationError):
        validate_yaml(raw)


def test_validate_yaml_rejects_oversize():
    with pytest.raises(YamlValidationError):
        validate_yaml(b"a: " + b"x" * 2_000_000)


def test_create_view_and_version_lifecycle(client, db):
    login(client, db, "alice", role="analyst")
    token = csrf_for(client)

    resp = client.post("/semantic-views", data={
        "csrf_token": token, "name": "sales", "description": "Sales warehouse",
        "yaml_text": GOOD_YAML,
    })
    assert resp.status_code == 303
    view_url = resp.headers["location"]

    # upload v2
    resp = client.post(f"{view_url}/versions", data={
        "csrf_token": token, "change_note": "add customers",
        "yaml_text": GOOD_YAML + "  - name: customers\n",
    })
    assert resp.status_code == 200 and "v2" in resp.text

    # invalid upload rejected
    resp = client.post(f"{view_url}/versions", data={
        "csrf_token": token, "yaml_text": "key: [broken",
    })
    assert resp.status_code == 400

    # download current
    from app.models import SemanticView
    view = db.query(SemanticView).first()
    resp = client.get(f"{view_url}/versions/{view.current_version_id}/download")
    assert resp.status_code == 200 and "customers" in resp.text

    # rollback to v1
    v1 = [v for v in view.versions if v.version_number == 1][0]
    resp = client.post(f"{view_url}/rollback/{v1.id}", data={"csrf_token": token})
    assert resp.status_code == 303
    db.expire_all()
    assert view.current_version_id == v1.id


def test_duplicate_view_name_rejected(client, db):
    login(client, db, "alice", role="analyst")
    token = csrf_for(client)
    data = {"csrf_token": token, "name": "sales", "yaml_text": GOOD_YAML}
    assert client.post("/semantic-views", data=data).status_code == 303
    assert client.post("/semantic-views", data=data).status_code == 400


def test_views_are_user_specific(client, db):
    login(client, db, "alice", role="analyst")
    token = csrf_for(client)
    resp = client.post("/semantic-views", data={
        "csrf_token": token, "name": "alice-private", "yaml_text": GOOD_YAML,
    })
    view_url = resp.headers["location"]
    view_id = int(view_url.rsplit("/", 1)[1])

    from app.models import SemanticView
    view = db.get(SemanticView, view_id)
    version_id = view.current_version_id

    # another analyst can't see or touch alice's view
    login(client, db, "bob", role="analyst")
    bob_token = csrf_for(client)
    assert "alice-private" not in client.get("/semantic-views").text
    assert client.get(view_url).status_code == 404
    assert client.get(f"{view_url}/versions/{version_id}/download").status_code == 404
    assert client.post(f"{view_url}/versions", data={
        "csrf_token": bob_token, "yaml_text": GOOD_YAML,
    }).status_code == 404
    assert client.post("/runs", data={
        "csrf_token": bob_token, "question": "q?", "semantic_view_id": view_id,
    }).status_code == 400
    # and it's absent from bob's pickers
    assert "alice-private" not in client.get("/runs/new").text
    assert "alice-private" not in client.get("/schedules/new").text

    # admins see and manage everything
    login(client, db, "root", role="admin")
    admin_token = csrf_for(client)
    assert "alice-private" in client.get("/semantic-views").text
    assert client.get(view_url).status_code == 200
    assert client.post(f"{view_url}/versions", data={
        "csrf_token": admin_token, "yaml_text": GOOD_YAML + "  - name: extra\n",
    }).status_code == 200


def test_detail_page_prefills_yaml_editor(client, db):
    login(client, db, "alice", role="analyst")
    token = csrf_for(client)
    resp = client.post("/semantic-views", data={
        "csrf_token": token, "name": "sales", "yaml_text": GOOD_YAML,
    })
    page = client.get(resp.headers["location"]).text
    assert "yaml-editor" in page and "name: sales_model" in page

    # editing via the textarea saves a new version through the same endpoint
    resp = client.post(f"{resp.headers['location']}/versions", data={
        "csrf_token": token, "change_note": "edited inline",
        "yaml_text": GOOD_YAML + "  - name: edited\n",
    })
    assert resp.status_code == 200 and "v2" in resp.text
