# Analyst Web

Web frontend for the agentic data analyst pipeline: user accounts and role-based
permissions, semantic-view YAML management with versioning, one-time analysis runs
with live logs, cron-style recurring runs, and browsable markdown reports.

This directory is self-contained inside the pipeline repo: it has its own venv,
requirements, SQLite database (`webapp/data/`), and tests. Run everything below
from `webapp/`. The bundled adapter auto-detects the enclosing repo, so no
pipeline path configuration is needed.

**No npm anywhere.** Pure-Python stack (FastAPI + Jinja2 + SQLite); the only
JavaScript/CSS are single files vendored into `app/static/vendor/` (htmx 2.0.4,
Pico CSS 2.0.6, downloaded once from their GitHub releases and committed).

## Architecture

Two long-lived processes sharing one SQLite database and one data directory:

- **web** — uvicorn/FastAPI. Server-rendered pages; htmx polls fragments for live
  run status and log tailing. Never spawns pipeline subprocesses.
- **worker** — `python -m app.worker`. A poll loop that fires due schedules,
  claims queued runs (the `runs` table is the queue), launches the pipeline as a
  subprocess per run, and reaps/cancels/times-out children. Being the only
  scheduler process makes double-firing impossible.

Roles are a strict ladder: **viewer** (read runs and reports) < **analyst** (run,
manage own semantic views and schedules) < **admin** (manage users, anything).

Semantic views are per-user: each view belongs to the analyst who created it and
is invisible to other non-admin users — in the list, detail, downloads, and every
run/schedule picker. Admins see and manage all views. The current YAML is editable
in the browser; each save is validated and stored as a new version (with diff and
rollback), same as an upload.

## Pipeline contract

The worker invokes your pipeline (`ANALYST_PIPELINE_CMD`) as:

```
<PIPELINE_CMD> --question-file <run_dir>/question.txt \
               --semantic-view <run_dir>/input.yaml \
               --output-dir <run_dir>
```

It must write `report.md` into `--output-dir` (extra files go in
`<run_dir>/artifacts/`) and exit 0 on success. stdout/stderr are captured to the
live log. `SNOWFLAKE_*`, `ANTHROPIC_*`, `PIPELINE_*`, and `AZURE_*` env vars are
forwarded. `tests/fake_pipeline.py` implements this contract for local development.

### agentic_data_analyst integration

`adapters/agentic_pipeline.py` bridges this contract to the
[agentic_data_analyst](https://github.com/tylerchiaRCCB/agentic_data_analyst)
CLI: it reads `question.txt` into `--question`, runs the pipeline from its own
repo root with `--source cortex_analyst`, renames the pipeline's
`<timestamp>-<slug>.md` output to `report.md`, and copies the run's JSON
artifacts back. The run's YAML controls data routing via optional top-level keys:
`semantic_view: DB.SCHEMA.VIEW` sends a Snowflake view reference;
`domain: <name>` names the pipeline domain/model; with neither, the YAML itself
is shipped as the inline semantic model. Configure via `ANALYST_PIPELINE_CMD`,
`PIPELINE_PYTHON`, `PIPELINE_BACKEND`, `PIPELINE_EXTRA_ARGS` (see `.env.example`;
`PIPELINE_REPO` is only needed if the webapp is moved outside this repo). Use
`PIPELINE_EXTRA_ARGS=--dry-run` for a token-free end-to-end plumbing test.

## Local development

```bash
cd webapp
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env          # set ANALYST_SECRET_KEY at minimum
.venv/bin/alembic upgrade head
.venv/bin/python -m app.create_admin admin        # prompts for password
.venv/bin/uvicorn app.main:app --reload           # terminal 1: web
.venv/bin/python -m app.worker                    # terminal 2: worker
```

Visit http://localhost:8000. To exercise the full flow without touching the real
pipeline, set `ANALYST_PIPELINE_CMD=python tests/fake_pipeline.py` (the built-in
default when no `.env` is present); the checked-in `.env.example` points at the
real pipeline via the adapter instead.

## Tests

```bash
.venv/bin/python -m pytest tests/
```

Covers auth/roles/CSRF/rate-limiting, YAML validation and versioning, the full
run lifecycle against the fake pipeline (success, failure, cancel, orphan
recovery), scheduling (cron validation, firing, overlap policy), markdown
sanitization, and path-traversal protection.

## Deployment

```bash
cp .env.example .env   # fill in secret key + pipeline creds
docker compose up -d --build
docker compose exec web python -m app.create_admin admin
```

Serve behind your internal TLS proxy and set `ANALYST_COOKIE_SECURE=true`.
Backups: `sqlite3 data/app.db ".backup backup.db"` (WAL-safe) plus a tar of the
data volume. To move to Postgres later, set `ANALYST_DATABASE_URL`, run
`alembic upgrade head`, and copy rows.
