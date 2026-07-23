import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> str:
    return uuid.uuid4().hex


ROLES = ("viewer", "analyst", "admin")
RUN_STATUSES = ("queued", "running", "succeeded", "failed", "cancelled", "timed_out")
ACTIVE_RUN_STATUSES = ("queued", "running")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(16), default="viewer")
    display_name: Mapped[str] = mapped_column(String(128), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Session(Base):
    __tablename__ = "sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ip: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(256), default="")

    user: Mapped[User] = relationship()


class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), index=True)
    ip: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SemanticView(Base):
    __tablename__ = "semantic_views"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    snowflake_ref: Mapped[str] = mapped_column(String(256), default="")  # e.g. DB.SCHEMA.SEMANTIC_VIEW
    current_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("semantic_view_versions.id", use_alter=True), nullable=True
    )
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)

    current_version: Mapped["SemanticViewVersion | None"] = relationship(
        foreign_keys=[current_version_id]
    )
    versions: Mapped[list["SemanticViewVersion"]] = relationship(
        back_populates="view",
        foreign_keys="SemanticViewVersion.semantic_view_id",
        order_by="SemanticViewVersion.version_number.desc()",
    )
    creator: Mapped[User | None] = relationship(foreign_keys=[created_by])


class SemanticViewVersion(Base):
    __tablename__ = "semantic_view_versions"
    __table_args__ = (UniqueConstraint("semantic_view_id", "version_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    semantic_view_id: Mapped[int] = mapped_column(ForeignKey("semantic_views.id"))
    version_number: Mapped[int] = mapped_column(Integer)
    file_path: Mapped[str] = mapped_column(String(512))  # relative to data_dir
    content_sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    change_note: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    validation_status: Mapped[str] = mapped_column(String(16), default="valid")  # valid|warnings
    validation_messages: Mapped[list] = mapped_column(JSON, default=list)

    view: Mapped[SemanticView] = relationship(
        back_populates="versions", foreign_keys=[semantic_view_id]
    )
    creator: Mapped[User | None] = relationship(foreign_keys=[created_by])


class Schedule(Base):
    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    question: Mapped[str] = mapped_column(Text)
    semantic_view_id: Mapped[int] = mapped_column(ForeignKey("semantic_views.id"))
    pin_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("semantic_view_versions.id"), nullable=True
    )
    cron_expr: Mapped[str] = mapped_column(String(64))
    timezone: Mapped[str] = mapped_column(String(64))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    overlap_policy: Mapped[str] = mapped_column(String(8), default="skip")  # skip|queue
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    view: Mapped[SemanticView] = relationship()
    creator: Mapped[User | None] = relationship(foreign_keys=[created_by])


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (Index("ix_runs_status_created", "status", "created_at"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    question: Mapped[str] = mapped_column(Text)
    semantic_view_id: Mapped[int] = mapped_column(ForeignKey("semantic_views.id"))
    semantic_view_version_id: Mapped[int] = mapped_column(
        ForeignKey("semantic_view_versions.id")
    )
    schedule_id: Mapped[int | None] = mapped_column(
        ForeignKey("schedules.id", ondelete="SET NULL"), nullable=True, index=True
    )
    triggered_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    error_summary: Mapped[str] = mapped_column(Text, default="")
    report_path: Mapped[str] = mapped_column(String(512), default="")  # relative to data_dir
    log_path: Mapped[str] = mapped_column(String(512), default="")

    view: Mapped[SemanticView] = relationship()
    version: Mapped[SemanticViewVersion] = relationship()
    schedule: Mapped[Schedule | None] = relationship()
    user: Mapped[User | None] = relationship(foreign_keys=[triggered_by])
