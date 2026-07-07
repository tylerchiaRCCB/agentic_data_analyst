# Instructions for AI coding assistants — webapp/

You are working on **Analyst Web**, the web frontend for the agentic data analyst
pipeline in the enclosing repo. It is a deliberately boring, self-contained
Python web app: FastAPI + Jinja2 + SQLite + htmx. This file is your orientation
for everything under `webapp/`; the repo root `CLAUDE.md` covers the pipeline itself.

Auto-loaded by Claude Code when working in this directory. Everything below is
also human-readable documentation — keep it accurate when you change behavior.

---

## What it is

A two-process app that lets users ask business questions, manage semantic-model
YAMLs, schedule recurring analyses, and read the pipeline's markdown reports:

- **web** — `uvicorn app.main:app`. Server-rendered pages; htmx polls fragments
  for live run status and log tailing. Never spawns pipeline subprocesses.
- **worker** — `python -m app.worker`. A poll loop that fires due schedules,
  claims queued runs (the `runs` DB table IS the queue — no Redis/celery),
  launches the pipeline as a subprocess per run, and reaps/cancels/times-out
  children. It is the only scheduler process, which makes double-firing impossible.

Both processes share one SQLite database (`data/app.db`, WAL mode) and one data
directory (`data/`). Config comes from `ANALYST_*` env vars / `.env`
(pydantic-settings, see `app/config.py`).

**Hard constraint: no npm, no CDNs, no external requests.** The only JS/CSS are
single vendored files in `app/static/vendor/` (htmx 2.0.4, Pico CSS 2.0.6). The
CSP is `default-src 'self'` — inline `<script>` is blocked; all JS lives in
static files. Do not introduce a build step.

---

## How to run it

```bash
cd webapp
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env                       # set ANALYST_SECRET_KEY
.venv/bin/alembic upgrade head             # create/migrate SQLite schema
.venv/bin/python -m app.create_admin admin # seed or reset an admin (prompts)
.venv/bin/uvicorn app.main:app --reload    # terminal 1
.venv/bin/python -m app.worker             # terminal 2
```

- Full-flow testing **without credentials**: set
  `ANALYST_PIPELINE_CMD=python tests/fake_pipeline.py` (this is the built-in
  default when the var is unset). The fake pipeline implements the whole contract.
- First test against the **real pipeline** without spending tokens: set
  `PIPELINE_EXTRA_ARGS=--dry-run`.
- `GET /healthz` reports DB reachability and worker-heartbeat freshness.
- Tests: `.venv/bin/python -m pytest tests/` (run from `webapp/`, ~38 tests).

---

## Layout — what lives where

```
app/
  main.py            · app factory; session middleware; security headers/CSP; /healthz
  config.py          · Settings (env prefix ANALYST_); data-dir path helpers
  models.py          · SQLAlchemy models: User, Session, LoginAttempt, SemanticView,
                       SemanticViewVersion, Schedule, Run (+ ROLES, RUN_STATUSES)
  db.py              · engine/SessionLocal; SQLite WAL + foreign_keys pragmas
  templating.py      · Jinja2 setup, render() helper, |dt and |duration filters
  create_admin.py    · CLI: seed or reset an admin user (python -m app.create_admin)
  routers/
    auth.py          · login/logout (rate-limited), account page, change password
    dashboard.py     · home page: ask-a-question, recent runs, upcoming schedules
    semantic_views.py· CRUD + versioning + YAML editing + diff/rollback/download
    runs.py          · run list/detail/create/cancel/rerun; report/log/artifact
                       downloads; htmx fragments for live status + log tail
    schedules.py     · schedule CRUD, cron preview fragment, run-now, toggle
    admin.py         · user management (admin only)
  security/
    sessions.py      · opaque token sessions, sha256-hashed in DB, idle+absolute TTL
    csrf.py          · HMAC(cookie) double-submit token; verify_csrf dependency
    passwords.py     · argon2id hashing, new-password policy
    deps.py          · get_current_user, require_role(min), can_manage(user, owner)
  services/          · business logic kept out of routers
    semantic_views.py· YAML validation (safe_load + shape warnings), versioned file
                       storage, pygments highlight, unified diff
    runs.py          · enqueue_run, run-dir layout, log tailing, artifact listing
    schedules.py     · croniter validation, next-fire computation, previews
    markdown.py      · mistune render + nh3 sanitize of pipeline reports
  worker/
    loop.py          · the entire scheduler/executor loop (claim, fire, reap,
                       timeout, cancel, orphan recovery, heartbeat file)
    pipeline_adapter.py · builds the pipeline argv/env; the decoupling seam.
                       Forwards only SNOWFLAKE_*/ANTHROPIC_*/PIPELINE_*/AZURE_* env
  templates/         · Jinja2; base.html is the app shell (topbar, theme toggle)
  static/
    app.css          · the whole design system (theme tokens, light/dark, components)
    app.js           · log auto-scroll, theme toggle, menu close; theme.js = pre-paint
    vendor/          · htmx + Pico CSS, committed verbatim — do not edit
adapters/
  agentic_pipeline.py· bridges the worker contract to THIS repo's pipeline CLI
                       (see "Pipeline integration" below). Stdlib-only on purpose.
alembic/             · migrations; alembic.ini at webapp root
tests/               · pytest suite; conftest isolates data into tests/_data;
                       fake_pipeline.py implements the pipeline contract
data/                · runtime state (SQLite DB, semantic_views/, runs/) — git-ignored
```

---

## Domain rules you must preserve

**Roles** are a strict ladder: `viewer` (read runs/reports) < `analyst` (run,
manage own semantic views + schedules) < `admin` (everything). Enforced by
`require_role(min)` on every route; ownership checks via `can_manage(user, owner_id)`.

**Semantic views are per-user.** A view belongs to `created_by`; non-admins get
404 for views they don't own — in list, detail, versions, downloads, diffs, and
every run/schedule picker (server-side validated on POST too, not just filtered
in the UI). Admins see all. Runs and reports are intentionally global (that is
what viewers exist for). If you add a new route that touches a view, it must go
through `_get_view(db, view_id, user)`.

**YAML editing = versioning.** There is no in-place edit. The detail page's
editor posts to the same versions endpoint as uploads; every save is validated
(`services/semantic_views.validate_yaml`) and stored as a new immutable version
file under `data/semantic_views/<view_id>/v<n>.yaml`, then becomes current.
Rollback just repoints `current_version_id`.

**The worker owns all subprocess lifecycle.** The web process must never spawn,
signal, or wait on pipeline processes. Runs move: queued → running →
succeeded/failed/cancelled/timed_out. The question is passed to the pipeline via
file, never argv (injection/ps-leak/length reasons).

**Security invariants:** CSRF token on every mutating form (htmx sends it via
the `hx-headers` on `<body>`); argon2id passwords; sessions are opaque tokens
hashed in the DB; report markdown is sanitized with nh3 before rendering;
artifact/report downloads resolve paths defensively (no traversal); login is
rate-limited per username+IP.

---

## Pipeline integration (the part most likely to confuse you)

Two layers, two contracts:

**1. Worker → generic pipeline contract** (`app/worker/pipeline_adapter.py`):

```
<ANALYST_PIPELINE_CMD> --question-file <run_dir>/question.txt \
                       --semantic-view <run_dir>/input.yaml \
                       --output-dir <run_dir>
```

Must write `report.md` into `--output-dir`, exit 0 on success; stdout/stderr
become the live log. `input.yaml` is the run's pinned semantic-view version.

**2. Adapter → this repo's actual CLI** (`adapters/agentic_pipeline.py`): the
pipeline (`python -m src.main`) wants `--question` as inline text, runs from the
repo root (relative `config/`, `agents/`, `context/`, `runs/`, `.env` via
load_dotenv), takes data routing as `--source cortex_analyst` plus either a
Snowflake view reference or a named semantic model, and writes
`<timestamp>-<slug>.md`, not `report.md`. The adapter translates: reads
question.txt, auto-detects the repo root (it is `../..` from the adapter file;
`PIPELINE_REPO` env overrides), routes the YAML, renames the newest output
markdown to `report.md`, copies `runs/<id>/artifacts/*` back, and propagates the
exit code.

**YAML routing directives** — optional top-level keys in the web-managed YAML:

| YAML contains                  | Adapter passes                                      |
|--------------------------------|-----------------------------------------------------|
| `semantic_view: DB.SCHEMA.VIEW`| `--semantic-view DB.SCHEMA.VIEW` (body unused)      |
| `domain: <name>` (no s_v key)  | YAML is copied to `context/semantic_models/<name>.yaml` (web copy wins) + `--domain <name>` |
| neither                        | YAML shipped under a temp per-run model name, cleaned up after |

**Env knobs** (all forwarded by the worker because of the `PIPELINE_` prefix):
`PIPELINE_REPO`, `PIPELINE_PYTHON` (default: `uv run --project <repo>`),
`PIPELINE_BACKEND` (anthropic | foundry | foundry-dev | azure-openai),
`PIPELINE_EXTRA_ARGS` (e.g. `--dry-run`). Credentials can live in the repo-root
`.env` (the pipeline loads it itself) or the worker's environment.

---

## Gotchas

- **Test isolation from the pipeline repo:** the repo root has a top-level
  `tests` *package* which shadows imports. `webapp/pytest.ini` anchors rootdir
  here and `webapp/tests/__init__.py` makes the suite a regular package. Run
  pytest from `webapp/`, never from the repo root. The root `pyproject.toml`
  `testpaths = ["tests"]` keeps the pipeline's pytest away from webapp tests.
- **Schema changes** go through alembic (`alembic revision -m ... && alembic
  upgrade head`), and models double as the source of truth for fresh test DBs
  (`Base.metadata.create_all` in conftest).
- **Theming:** light/dark is driven by `data-theme` on `<html>` (set pre-paint
  by `static/theme.js` from localStorage) with `prefers-color-scheme` as the
  auto fallback. New CSS must style both (see the token blocks at the top of
  `app.css`).
- The worker heartbeat file (`data/worker.heartbeat`) is how `/healthz` knows
  the worker is alive; the worker touches it every poll tick.
- SQLite is fine here (WAL + short transactions + single worker). To move to
  Postgres set `ANALYST_DATABASE_URL` and run alembic — don't add DB-specific SQL.
