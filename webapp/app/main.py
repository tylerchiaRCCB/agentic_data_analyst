from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db import SessionLocal
from app.routers import admin, auth, dashboard, runs, schedules, semantic_views
from app.security.deps import LoginRequired, login_redirect
from app.security.sessions import resolve_session


def create_app() -> FastAPI:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.semantic_views_dir.mkdir(parents=True, exist_ok=True)
    settings.runs_dir.mkdir(parents=True, exist_ok=True)

    app = FastAPI(title="Data Analyst", docs_url=None, redoc_url=None, openapi_url=None)

    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    @app.middleware("http")
    async def attach_user_and_headers(request: Request, call_next):
        request.state.user = None
        cookie = request.cookies.get(settings.session_cookie)
        if cookie:
            db = SessionLocal()
            try:
                request.state.user = resolve_session(db, cookie)
            finally:
                db.close()
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:",
        )
        return response

    @app.exception_handler(LoginRequired)
    async def _login_required(request: Request, _exc: LoginRequired):
        return login_redirect(request)

    app.include_router(auth.router)
    app.include_router(dashboard.router)
    app.include_router(semantic_views.router)
    app.include_router(runs.router)
    app.include_router(schedules.router)
    app.include_router(admin.router)

    @app.get("/healthz")
    def healthz():
        from sqlalchemy import text

        from app.models import utcnow

        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()
        hb = settings.worker_heartbeat_file
        worker_ok = False
        if hb.exists():
            age = utcnow().timestamp() - hb.stat().st_mtime
            worker_ok = age < 60
        return {"db": "ok", "worker": "ok" if worker_ok else "stale"}

    @app.get("/favicon.ico")
    def favicon():
        return Response(status_code=204)

    return app


app = create_app()
