from fastapi import Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session as DbSession

from app.config import settings
from app.db import get_db
from app.models import ROLES, User
from app.security.sessions import resolve_session


class LoginRequired(HTTPException):
    """Raised when there is no valid session; handled by redirecting to /login."""

    def __init__(self):
        super().__init__(status_code=401, detail="Login required")


def login_redirect(request: Request) -> RedirectResponse:
    # htmx requests can't follow a 303 into a full-page swap; tell htmx to redirect
    if request.headers.get("HX-Request"):
        resp = RedirectResponse("/login", status_code=204)
        resp.headers["HX-Redirect"] = "/login"
        return resp
    return RedirectResponse("/login", status_code=303)


def get_current_user(request: Request, db: DbSession = Depends(get_db)) -> User:
    cookie = request.cookies.get(settings.session_cookie)
    if not cookie:
        raise LoginRequired()
    user = resolve_session(db, cookie)
    if user is None:
        raise LoginRequired()
    return user


def require_role(minimum: str):
    """Roles form a strict ladder: viewer < analyst < admin."""
    min_rank = ROLES.index(minimum)

    def checker(user: User = Depends(get_current_user)) -> User:
        if ROLES.index(user.role) < min_rank:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return checker


def can_manage(user: User, owner_id: int | None) -> bool:
    """Analysts manage their own objects; admins manage anything."""
    return user.role == "admin" or (owner_id is not None and owner_id == user.id)
