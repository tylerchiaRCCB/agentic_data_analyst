import secrets

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DbSession

from app.db import get_db
from app.models import ROLES, Session, User
from app.security.csrf import verify_csrf
from app.security.deps import require_role
from app.security.passwords import hash_password, validate_new_password
from app.templating import render

router = APIRouter(prefix="/admin")


def _users_page(request: Request, db: DbSession, status_code: int = 200, **ctx):
    users = db.scalars(select(User).order_by(User.username)).all()
    return render(request, "admin/users.html", status_code=status_code,
                  users=users, roles=ROLES, **ctx)


@router.get("/users")
def list_users(
    request: Request,
    user: User = Depends(require_role("admin")),
    db: DbSession = Depends(get_db),
):
    return _users_page(request, db)


@router.post("/users", dependencies=[Depends(verify_csrf)])
def create_user(
    request: Request,
    username: str = Form(...),
    display_name: str = Form(""),
    role: str = Form("viewer"),
    password: str = Form(...),
    admin: User = Depends(require_role("admin")),
    db: DbSession = Depends(get_db),
):
    username = username.strip().lower()
    if not username:
        return _users_page(request, db, 400, flash="Username is required.", flash_kind="error")
    if role not in ROLES:
        return _users_page(request, db, 400, flash="Invalid role.", flash_kind="error")
    if err := validate_new_password(password):
        return _users_page(request, db, 400, flash=err, flash_kind="error")
    if db.scalar(select(User).where(User.username == username)):
        return _users_page(request, db, 400,
                           flash=f"User {username!r} already exists.", flash_kind="error")
    db.add(User(
        username=username,
        display_name=display_name.strip() or username,
        role=role,
        password_hash=hash_password(password),
    ))
    db.commit()
    return _users_page(request, db, flash=f"User {username!r} created.", flash_kind="success")


@router.post("/users/{user_id}", dependencies=[Depends(verify_csrf)])
def update_user(
    request: Request,
    user_id: int,
    role: str = Form(...),
    is_active: str = Form("off"),
    admin: User = Depends(require_role("admin")),
    db: DbSession = Depends(get_db),
):
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404)
    if role not in ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")
    if target.id == admin.id and (role != "admin" or is_active != "on"):
        return _users_page(request, db, 400,
                           flash="You cannot demote or deactivate yourself.", flash_kind="error")
    target.role = role
    target.is_active = is_active == "on"
    if not target.is_active:
        db.execute(delete(Session).where(Session.user_id == target.id))
    db.commit()
    return _users_page(request, db, flash=f"User {target.username!r} updated.", flash_kind="success")


@router.post("/users/{user_id}/reset-password", dependencies=[Depends(verify_csrf)])
def reset_password(
    request: Request,
    user_id: int,
    admin: User = Depends(require_role("admin")),
    db: DbSession = Depends(get_db),
):
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404)
    new_password = secrets.token_urlsafe(12)
    target.password_hash = hash_password(new_password)
    db.execute(delete(Session).where(Session.user_id == target.id))
    db.commit()
    return _users_page(
        request, db,
        flash=f"Temporary password for {target.username!r}: {new_password} — share it securely; "
              "they should change it under Account.",
        flash_kind="success",
    )
