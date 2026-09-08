from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.db import Base
from app.retention import validate_retention_overrides


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    retention_overrides: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, default=None
    )

    talks: Mapped[list[Talk]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )

    @validates("retention_overrides")
    def _validate_retention_overrides(self, key: str, value: Any) -> Any:
        return validate_retention_overrides(value)


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    hashed_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    event_ids: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=list)


class Talk(Base):
    __tablename__ = "talks"
    __table_args__ = (
        UniqueConstraint(
            "event_id", "title", "start", name="uq_talks_event_id_title_start"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    room: Mapped[str | None] = mapped_column(String(255))
    start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="waiting_for_files"
    )
    raw_duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    cut_start: Mapped[float | None] = mapped_column(Float, nullable=True)
    cut_end: Mapped[float | None] = mapped_column(Float, nullable=True)
    include_intro: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    include_outro: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    intro_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    outro_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    custom_intro_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    custom_outro_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    event: Mapped[Event] = relationship(back_populates="talks")
    jobs: Mapped[list[Job]] = relationship(
        back_populates="talk", cascade="all, delete-orphan"
    )
    reviews: Mapped[list[Review]] = relationship(
        back_populates="talk", cascade="all, delete-orphan"
    )


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    talk_id: Mapped[int] = mapped_column(ForeignKey("talks.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    log_path: Mapped[str | None] = mapped_column(Text)
    progress_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    talk: Mapped[Talk] = relationship(back_populates="jobs")


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    talk_id: Mapped[int] = mapped_column(ForeignKey("talks.id"), nullable=False)
    decision: Mapped[str] = mapped_column(String(50), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    talk: Mapped[Talk] = relationship(back_populates="reviews")
