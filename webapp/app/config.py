import sys
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ANALYST_", env_file=".env", extra="ignore")

    secret_key: str = "dev-only-change-me"
    data_dir: Path = Path("data")
    database_url: str = ""  # derived from data_dir when empty
    # Pipeline repo root — auto-detected when webapp lives inside the repo
    repo_root: Path = Path(__file__).resolve().parents[2]

    # Sessions
    session_cookie: str = "analyst_session"
    session_idle_hours: int = 12
    session_absolute_days: int = 7
    cookie_secure: bool = False  # set true behind TLS

    # Uploads / runs
    max_yaml_bytes: int = 1_000_000
    max_concurrent_runs: int = 2
    run_timeout_minutes: int = 60
    worker_poll_seconds: float = 2.0

    # Pipeline invocation, e.g. "python /srv/pipeline/main.py"
    pipeline_cmd: str = f"{sys.executable} tests/fake_pipeline.py"

    default_timezone: str = "America/Los_Angeles"

    # Login rate limiting
    login_max_failures: int = 5
    login_window_minutes: int = 15

    @property
    def db_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{self.data_dir / 'app.db'}"

    @property
    def semantic_views_dir(self) -> Path:
        return self.data_dir / "semantic_views"

    @property
    def semantic_models_dir(self) -> Path:
        return self.repo_root / "context" / "semantic_models"

    @property
    def domains_dir(self) -> Path:
        return self.repo_root / "context" / "domains"

    @property
    def runs_dir(self) -> Path:
        return self.data_dir / "runs"

    @property
    def worker_heartbeat_file(self) -> Path:
        return self.data_dir / "worker.heartbeat"


settings = Settings()
