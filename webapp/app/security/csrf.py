import hashlib
import hmac

from fastapi import HTTPException, Request

from app.config import settings


def csrf_token_for(cookie_value: str) -> str:
    """Derive a CSRF token from the session cookie (double-submit, keyed)."""
    return hmac.new(
        settings.secret_key.encode(), b"csrf:" + cookie_value.encode(), hashlib.sha256
    ).hexdigest()


async def verify_csrf(request: Request) -> None:
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    cookie = request.cookies.get(settings.session_cookie, "")
    expected = csrf_token_for(cookie)
    supplied = request.headers.get("X-CSRF-Token", "")
    if not supplied:
        form = await request.form()
        supplied = str(form.get("csrf_token", ""))
    if not hmac.compare_digest(expected, supplied):
        raise HTTPException(status_code=403, detail="CSRF token missing or invalid")
