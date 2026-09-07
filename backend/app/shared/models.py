from datetime import UTC, datetime
from uuid import uuid4

from app.core.database import Base
from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column


def uid():
    return uuid4().hex


def now():
    return datetime.now(UTC)


class FileRecord(Base):
    __tablename__ = "files"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    original_name: Mapped[str]
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    size: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    module: Mapped[str]
    role: Mapped[str | None]
    path: Mapped[str]


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    module: Mapped[str]
    title: Mapped[str]
    status: Mapped[str] = mapped_column(default="queued", index=True)
    progress: Mapped[int] = mapped_column(default=0)
    message: Mapped[str] = mapped_column(default="В очереди")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    file_ids: Mapped[list] = mapped_column(JSON)
    options: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[dict | None] = mapped_column(JSON)
    result: Mapped[dict | None] = mapped_column(JSON)
    output_path: Mapped[str | None]
    output_name: Mapped[str | None]


class Setting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)


class RunRow(Base):
    __tablename__ = "analysis_rows"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    section: Mapped[str] = mapped_column(index=True)
    item_key: Mapped[str] = mapped_column(index=True)
    data: Mapped[dict] = mapped_column(JSON)


class WeeklyValue(Base):
    __tablename__ = "merchandise_weekly"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"), index=True)
    article: Mapped[str] = mapped_column(index=True)
    week_start: Mapped[str]
    kind: Mapped[str]
    quantity: Mapped[float | None]


class TnvedCache(Base):
    __tablename__ = "tnved_cache"
    signature: Mapped[str] = mapped_column(String(64), primary_key=True)
    code: Mapped[str] = mapped_column(String(10))
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    evidence: Mapped[dict] = mapped_column(JSON)
    description: Mapped[str] = mapped_column(Text)
