from datetime import datetime, timezone

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.security.csrf import csrf_token_for

templates = Jinja2Templates(directory="app/templates")


def _fmt_dt(value: datetime | None, fmt: str = "%Y-%m-%d %H:%M") -> str:
    if value is None:
        return "—"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone().strftime(fmt)


def _duration(start: datetime | None, end: datetime | None) -> str:
    if start is None:
        return "—"
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end is None:
        end = datetime.now(timezone.utc)
    elif end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    secs = int((end - start).total_seconds())
    if secs < 60:
        return f"{secs}s"
    return f"{secs // 60}m {secs % 60}s"


templates.env.filters["dt"] = _fmt_dt
templates.env.filters["duration"] = _duration


def render(request: Request, name: str, status_code: int = 200, **context):
    user = getattr(request.state, "user", None)
    cookie = request.cookies.get(settings.session_cookie, "")
    context.setdefault("user", user)
    context.setdefault("csrf_token", csrf_token_for(cookie))
    return templates.TemplateResponse(
        request=request, name=name, context=context, status_code=status_code
    )
