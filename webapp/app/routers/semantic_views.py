from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.db import get_db
from app.models import SemanticView, SemanticViewVersion, User
from app.security.csrf import verify_csrf
from app.security.deps import can_manage, require_role
from app.services.semantic_views import (
    YamlValidationError,
    add_version,
    highlight_yaml,
    read_version_bytes,
    unified_diff_html,
    validate_yaml,
)
from app.templating import render

router = APIRouter()


def _get_view(db: DbSession, view_id: int, user: User) -> SemanticView:
    """Semantic views are per-user: only the owner (or an admin) can see one."""
    view = db.get(SemanticView, view_id)
    if view is None or not can_manage(user, view.created_by):
        raise HTTPException(status_code=404)
    return view


def _get_version(db: DbSession, view: SemanticView, version_id: int) -> SemanticViewVersion:
    version = db.get(SemanticViewVersion, version_id)
    if version is None or version.semantic_view_id != view.id:
        raise HTTPException(status_code=404)
    return version


async def _read_yaml_input(file: UploadFile | None, pasted: str) -> bytes:
    if file is not None and file.filename:
        return await file.read()
    if pasted.strip():
        return pasted.encode("utf-8")
    raise YamlValidationError("Provide a YAML file or paste YAML content.")


@router.get("/semantic-views")
def list_views(
    request: Request,
    user: User = Depends(require_role("viewer")),
    db: DbSession = Depends(get_db),
):
    q = select(SemanticView).order_by(SemanticView.name)
    if user.role != "admin":
        q = q.where(SemanticView.created_by == user.id)
    views = db.scalars(q).all()
    return render(request, "semantic_views/list.html", views=views)


@router.get("/semantic-views/new")
def new_view_page(request: Request, user: User = Depends(require_role("analyst"))):
    return render(request, "semantic_views/new.html")


@router.post("/semantic-views", dependencies=[Depends(verify_csrf)])
async def create_view(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    yaml_text: str = Form(""),
    yaml_file: UploadFile | None = None,
    user: User = Depends(require_role("analyst")),
    db: DbSession = Depends(get_db),
):
    name = name.strip()
    if not name:
        return render(request, "semantic_views/new.html", status_code=400,
                      flash="Name is required.", flash_kind="error")
    if db.scalar(select(SemanticView).where(SemanticView.name == name)):
        return render(request, "semantic_views/new.html", status_code=400,
                      flash=f"A semantic view named {name!r} already exists.", flash_kind="error")
    try:
        raw = await _read_yaml_input(yaml_file, yaml_text)
        validate_yaml(raw)
    except YamlValidationError as e:
        return render(request, "semantic_views/new.html", status_code=400,
                      flash=str(e), flash_kind="error")

    view = SemanticView(name=name, description=description.strip(), created_by=user.id)
    db.add(view)
    db.flush()
    add_version(db, view, raw, change_note="Initial version", user=user)
    return RedirectResponse(f"/semantic-views/{view.id}", status_code=303)


@router.get("/semantic-views/{view_id}")
def view_detail(
    request: Request,
    view_id: int,
    user: User = Depends(require_role("viewer")),
    db: DbSession = Depends(get_db),
):
    view = _get_view(db, view_id, user)
    preview_html = ""
    current_yaml = ""
    if view.current_version:
        raw = read_version_bytes(view.current_version)
        preview_html = highlight_yaml(raw)
        current_yaml = raw.decode("utf-8", errors="replace")
    return render(request, "semantic_views/detail.html", view=view,
                  preview_html=preview_html, current_yaml=current_yaml)


@router.post("/semantic-views/{view_id}/versions", dependencies=[Depends(verify_csrf)])
async def upload_version(
    request: Request,
    view_id: int,
    change_note: str = Form(""),
    yaml_text: str = Form(""),
    yaml_file: UploadFile | None = None,
    user: User = Depends(require_role("analyst")),
    db: DbSession = Depends(get_db),
):
    view = _get_view(db, view_id, user)
    try:
        raw = await _read_yaml_input(yaml_file, yaml_text)
        version = add_version(db, view, raw, change_note, user)
    except YamlValidationError as e:
        return render(request, "fragments/upload_result.html", status_code=400,
                      error=str(e), version=None)
    return render(request, "fragments/upload_result.html", error=None, version=version,
                  view=view)


@router.post("/semantic-views/{view_id}/rollback/{version_id}", dependencies=[Depends(verify_csrf)])
def rollback(
    view_id: int,
    version_id: int,
    user: User = Depends(require_role("analyst")),
    db: DbSession = Depends(get_db),
):
    view = _get_view(db, view_id, user)
    version = _get_version(db, view, version_id)
    view.current_version_id = version.id
    db.commit()
    return RedirectResponse(f"/semantic-views/{view.id}", status_code=303)


@router.post("/semantic-views/{view_id}/archive", dependencies=[Depends(verify_csrf)])
def archive(
    view_id: int,
    user: User = Depends(require_role("admin")),
    db: DbSession = Depends(get_db),
):
    view = _get_view(db, view_id, user)
    view.is_archived = not view.is_archived
    db.commit()
    return RedirectResponse(f"/semantic-views/{view.id}", status_code=303)


@router.get("/semantic-views/{view_id}/versions/{version_id}/download")
def download_version(
    view_id: int,
    version_id: int,
    user: User = Depends(require_role("viewer")),
    db: DbSession = Depends(get_db),
):
    view = _get_view(db, view_id, user)
    version = _get_version(db, view, version_id)
    raw = read_version_bytes(version)
    filename = f"{view.name}-v{version.version_number}.yaml"
    return Response(
        content=raw,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/fragments/semantic-views/{view_id}/diff")
def diff_fragment(
    request: Request,
    view_id: int,
    old: int,
    new: int,
    user: User = Depends(require_role("viewer")),
    db: DbSession = Depends(get_db),
):
    view = _get_view(db, view_id, user)
    old_v = _get_version(db, view, old)
    new_v = _get_version(db, view, new)
    diff = unified_diff_html(
        read_version_bytes(old_v),
        read_version_bytes(new_v),
        f"v{old_v.version_number}",
        f"v{new_v.version_number}",
    )
    return render(request, "fragments/diff.html", diff=diff)
