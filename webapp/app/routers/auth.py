from datetime import timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.config import settings
from app.db import get_db
from app.models import LoginAttempt, User, utcnow
from app.security.csrf import verify_csrf
from app.security.deps import get_current_user
from app.security.passwords import hash_password, validate_new_password, verify_password
from app.security.sessions import create_session, destroy_session
from app.templating import render

router = APIRouter()


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else ""


def _too_many_failures(db: DbSession, username: str, ip: str) -> bool:
    cutoff = utcnow() - timedelta(minutes=settings.login_window_minutes)
    for field, value in ((LoginAttempt.username, username), (LoginAttempt.ip, ip)):
        count = db.scalar(
            select(func.count())
            .select_from(LoginAttempt)
            .where(field == value, LoginAttempt.created_at > cutoff)
        )
        if count is not None and count >= settings.login_max_failures:
            return True
    return False


@router.get("/login")
def login_page(request: Request):
    if request.state.user:
        return RedirectResponse("/", status_code=303)
    return render(request, "auth/login.html")


@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: DbSession = Depends(get_db),
):
    username = username.strip().lower()
    ip = _client_ip(request)
    if _too_many_failures(db, username, ip):
        return render(
            request,
            "auth/login.html",
            status_code=429,
            flash="Too many failed attempts. Try again later.",
            flash_kind="error",
        )
    user = db.scalar(select(User).where(User.username == username))
    if user is None or not user.is_active or not verify_password(user.password_hash, password):
        db.add(LoginAttempt(username=username, ip=ip))
        db.commit()
        return render(
            request,
            "auth/login.html",
            status_code=401,
            flash="Invalid username or password.",
            flash_kind="error",
        )
    user.last_login_at = utcnow()
    cookie_value = create_session(db, user, ip, request.headers.get("user-agent", ""))
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(
        settings.session_cookie,
        cookie_value,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.session_absolute_days * 86400,
    )
    return resp


@router.post("/logout", dependencies=[Depends(verify_csrf)])
def logout(request: Request, db: DbSession = Depends(get_db)):
    cookie = request.cookies.get(settings.session_cookie)
    if cookie:
        destroy_session(db, cookie)
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(settings.session_cookie)
    return resp


@router.get("/account")
def account_page(request: Request, user: User = Depends(get_current_user)):
    return render(request, "auth/account.html")


@router.post("/account/password", dependencies=[Depends(verify_csrf)])
def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    user: User = Depends(get_current_user),
    db: DbSession = Depends(get_db),
):
    def fail(msg: str):
        return render(request, "auth/account.html", status_code=400, flash=msg, flash_kind="error")

    if not verify_password(user.password_hash, current_password):
        return fail("Current password is incorrect.")
    if new_password != confirm_password:
        return fail("New passwords do not match.")
    if err := validate_new_password(new_password):
        return fail(err)
    managed = db.get(User, user.id)
    managed.password_hash = hash_password(new_password)
    db.commit()
    return render(request, "auth/account.html", flash="Password updated.", flash_kind="success")
