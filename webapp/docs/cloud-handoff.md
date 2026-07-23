# Analyst Web Cloud Handoff Guide

This document is the software handoff reference for Cloud and Applications teams.
It describes how to build, deploy, configure, validate, and operate the webapp.

## 1. System scope and architecture

The deployment consists of two long-running processes that must share the same database and data directory:

- web service: FastAPI + Jinja2 served by uvicorn
- worker service: schedule dispatcher + run executor (python -m app.worker)

The runs table is the queue. Only one worker process should be active per environment.

The worker launches the analytical pipeline through:

- app contract adapter: app/worker/pipeline_adapter.py
- repo adapter: adapters/agentic_pipeline.py

Pipeline run contract from worker:

- command: ANALYST_PIPELINE_CMD --question-file ... --semantic-view ... --output-dir ...
- expected output: report.md written to output-dir
- success criteria: process exit code 0 and report.md present

## 2. Build artifacts

Container image source:

- Dockerfile
- requirements.txt

Image includes:

- webapp Python runtime and dependencies
- application code under webapp/
- no node/npm build pipeline

Image does not include:

- pipeline repo dependencies outside webapp
- Snowflake credentials
- Anthropic/Azure credentials

## 3. Environment prerequisites

Required infrastructure:

- Linux container runtime
- Docker Compose or equivalent orchestrator
- persistent shared volume mounted at ANALYST_DATA_DIR for both web and worker (for run artifacts and semantic view files)
- PostgreSQL 14+ instance (recommended) OR persistent local storage that supports SQLite WAL
- connectivity to pipeline repo path (if running external pipeline code)

Runtime prerequisites:

- Python 3.12 (container baseline)
- psycopg2-binary (included in requirements.txt) when using Postgres
- access to pipeline repo root containing src/main.py
- database migration execution with alembic before services start

## 4. Configuration matrix

Application settings come from ANALYST_ prefixed env vars (app/config.py). Pipeline routing uses PIPELINE_* and credential prefixes.

Required variables:

- ANALYST_SECRET_KEY: long random secret for sessions/CSRF signing

Strongly recommended variables:

- ANALYST_COOKIE_SECURE=true in TLS environments
- ANALYST_DATA_DIR=/srv/app/data (or equivalent persistent mount)
- ANALYST_DATABASE_URL=postgresql://user:pass@host:5432/analyst_web (recommended over SQLite for production)
- PIPELINE_BACKEND=foundry-dev|foundry|anthropic|azure-openai

Common operational variables:

- ANALYST_DATABASE_URL: optional; when unset uses sqlite at ANALYST_DATA_DIR/app.db
- ANALYST_MAX_CONCURRENT_RUNS: concurrent run cap handled by worker
- ANALYST_RUN_TIMEOUT_MINUTES: per-run timeout
- ANALYST_DEFAULT_TIMEZONE: schedule timezone default
- ANALYST_WORKER_POLL_SECONDS: scheduler poll interval
- ANALYST_PIPELINE_CMD: command invoked by worker
- PIPELINE_REPO: required if webapp is deployed outside this repository structure
- PIPELINE_PYTHON: interpreter/launcher for pipeline execution
- PIPELINE_EXTRA_ARGS: extra args appended to pipeline call, for example --dry-run

Forwarded credential prefixes to pipeline subprocess:

- SNOWFLAKE_*
- ANTHROPIC_*
- AZURE_*
- PIPELINE_*

## 5. Deployment procedure (container)

1. Prepare environment file.

- copy .env.example to .env
- populate ANALYST_SECRET_KEY and runtime creds

2. Build and migrate.

- docker compose build
- docker compose run --rm migrate

3. Start services.

- docker compose up -d web worker

4. Seed admin user.

- docker compose exec web python -m app.create_admin <admin_username>

5. Validate health and login.

- GET /healthz must return db: ok
- worker field should become ok within one poll window
- log in and open dashboard

## 6. Critical deployment caveats

1. Single worker rule.

- Run exactly one worker instance per environment to avoid duplicate schedule firing.

2. Shared data path rule.

- web and worker must mount the same ANALYST_DATA_DIR path.

3. SQLite vs Postgres rule.

- SQLite is supported but NOT recommended for production deployments.
- SQLite requires WAL mode and does not work reliably on network filesystems.
- For production: set ANALYST_DATABASE_URL to a Postgres connection string.
- Postgres eliminates WAL lock issues, supports concurrent access, and persists across container restarts.
- ANALYST_DATA_DIR is still needed for run artifacts and semantic view files even with Postgres.

4. Pipeline launcher rule.

- If ANALYST_PIPELINE_CMD uses adapters/agentic_pipeline.py and PIPELINE_PYTHON is unset, adapter defaults to uv run --project <repo>.
- Ensure uv is available in runtime OR set PIPELINE_PYTHON explicitly to a valid interpreter/launcher.

5. Repo path rule.

- If deployed outside the monorepo layout, PIPELINE_REPO must point to a valid pipeline checkout containing src/main.py.

## 7. Build and release validation checklist

Before promoting to higher environment, verify:

- alembic upgrade head succeeds
- web starts and serves static assets
- worker starts and updates heartbeat
- /healthz returns db ok and worker ok
- create run from UI succeeds using fake or dry-run pipeline
- report rendering works (markdown, details, mermaid)
- role checks: viewer cannot mutate, analyst cannot admin
- semantic model save creates new version
- scheduled run fires at next cron boundary

Recommended command-level validation in webapp directory:

- python -m pytest tests/

## 8. Operations runbook

Routine operations:

- restart web: docker compose restart web
- restart worker: docker compose restart worker
- follow logs: docker compose logs -f web worker

Backup:

- Postgres (recommended): pg_dump analyst_web > /backup/path/analyst_web.sql
- SQLite (if used): sqlite3 /path/to/app.db ".backup /backup/path/app.db"
- include semantic views and run outputs under ANALYST_DATA_DIR

Restore:

- Postgres: psql analyst_web < /backup/path/analyst_web.sql
- SQLite: restore app.db file
- run alembic upgrade head after restore
- restart services and verify /healthz

## 9. Security baseline

Required controls:

- TLS termination at ingress/proxy
- ANALYST_COOKIE_SECURE=true in production
- secret management for ANALYST_SECRET_KEY and credentials
- restrict network egress to required upstreams only (Snowflake/Azure/Anthropic as used)

Built-in controls in app:

- session signing + hashed opaque session tokens
- CSRF validation for state-changing requests
- argon2id password hashing
- markdown sanitization for rendered report content
- CSP and security headers set in app middleware

## 10. Ownership boundaries

Cloud and Applications team responsibilities:

- container build/release pipeline
- secrets injection and rotation
- runtime scaling, uptime, alerting, backup/restore
- ingress, TLS, and network policy

Data Science / Pipeline team responsibilities:

- pipeline business logic and models
- semantic model/domain content quality
- backend credential validity for chosen PIPELINE_BACKEND

## 11. Source references

- webapp/README.md
- webapp/CLAUDE.md
- webapp/Dockerfile
- webapp/docker-compose.yml
- webapp/app/config.py
- webapp/app/worker/loop.py
- webapp/app/worker/pipeline_adapter.py
- webapp/adapters/agentic_pipeline.py
