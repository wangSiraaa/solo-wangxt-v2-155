from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    table_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    boards: Mapped[list[Board]] = relationship(back_populates="event", cascade="all, delete-orphan")
    rotations: Mapped[list[RotationAssignment]] = relationship(back_populates="event", cascade="all, delete-orphan")
    results: Mapped[list[ResultEntry]] = relationship(back_populates="event", cascade="all, delete-orphan")
    publications: Mapped[list[Publication]] = relationship(back_populates="event", cascade="all, delete-orphan")


class Board(Base):
    __tablename__ = "boards"
    __table_args__ = (UniqueConstraint("event_id", "board_number", name="uq_board_event_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), nullable=False)
    board_number: Mapped[int] = mapped_column(Integer, CheckConstraint("board_number BETWEEN 1 AND 32"), nullable=False)
    vulnerability: Mapped[str] = mapped_column(String(8), nullable=False)

    event: Mapped[Event] = relationship(back_populates="boards")


class RotationAssignment(Base):
    """Which NS/EW pairs are scheduled to play a board at a physical table."""

    __tablename__ = "rotation_assignments"
    __table_args__ = (
        UniqueConstraint("event_id", "board_number", "table_number", name="uq_rotation_board_table"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), nullable=False)
    board_number: Mapped[int] = mapped_column(Integer, nullable=False)
    table_number: Mapped[int] = mapped_column(Integer, nullable=False)
    ns_pair_number: Mapped[int] = mapped_column(Integer, nullable=False)
    ew_pair_number: Mapped[int] = mapped_column(Integer, nullable=False)

    event: Mapped[Event] = relationship(back_populates="rotations")


class ResultEntry(Base):
    """Accepted/raw traveller entry; original submitted payload is retained."""

    __tablename__ = "result_entries"
    __table_args__ = (
        UniqueConstraint("event_id", "board_number", "table_number", name="uq_result_board_table"),
        CheckConstraint("level IS NULL OR level BETWEEN 1 AND 7"),
        CheckConstraint("declarer IS NULL OR declarer IN ('N','E','S','W')"),
        CheckConstraint("doubled IN ('none','doubled','redoubled')"),
        CheckConstraint("denomination IS NULL OR denomination IN ('C','D','H','S','NT')"),
        CheckConstraint("(passed_out AND level IS NULL AND denomination IS NULL AND declarer IS NULL) OR (NOT passed_out AND level IS NOT NULL AND denomination IS NOT NULL AND declarer IS NOT NULL)"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), nullable=False)
    board_number: Mapped[int] = mapped_column(Integer, nullable=False)
    table_number: Mapped[int] = mapped_column(Integer, nullable=False)
    ns_pair_number: Mapped[int] = mapped_column(Integer, nullable=False)
    ew_pair_number: Mapped[int] = mapped_column(Integer, nullable=False)

    level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    denomination: Mapped[str | None] = mapped_column(String(2), nullable=True)
    declarer: Mapped[str | None] = mapped_column(String(1), nullable=True)
    doubled: Mapped[str] = mapped_column(String(10), default="none", nullable=False)
    overtricks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    undertricks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    passed_out: Mapped[bool] = mapped_column(default=False, nullable=False)

    ns_score: Mapped[int] = mapped_column(Integer, nullable=False)
    ew_score: Mapped[int] = mapped_column(Integer, nullable=False)
    score_breakdown: Mapped[dict] = mapped_column(JSON, nullable=False)
    source: Mapped[str] = mapped_column(String(200), nullable=False)
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    event: Mapped[Event] = relationship(back_populates="results")


class DuplicateReport(Base):
    """Every repeated table/board submission, including conflicting reports."""

    __tablename__ = "duplicate_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), nullable=False)
    board_number: Mapped[int] = mapped_column(Integer, nullable=False)
    table_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # identical/conflict
    existing_result_id: Mapped[int | None] = mapped_column(ForeignKey("result_entries.id"), nullable=True)
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class Publication(Base):
    """Immutable published ranking plus the exact comparison sets behind it."""

    __tablename__ = "publications"
    __table_args__ = (UniqueConstraint("event_id", "version", name="uq_publication_event_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    board_matchpoints: Mapped[list] = mapped_column(JSON, nullable=False)
    rankings: Mapped[list] = mapped_column(JSON, nullable=False)
    result_snapshot: Mapped[list] = mapped_column(JSON, nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    event: Mapped[Event] = relationship(back_populates="publications")
