from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    slots: Mapped[list["MovementSlot"]] = relationship(cascade="all, delete-orphan")
    assignments: Mapped[list["BoardAssignment"]] = relationship(cascade="all, delete-orphan")
    results: Mapped[list["BoardResult"]] = relationship(cascade="all, delete-orphan")


class Pair(Base):
    __tablename__ = "pairs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    __table_args__ = (UniqueConstraint("event_id", "code", name="uq_pair_event_code"),)


class MovementSlot(Base):
    __tablename__ = "movement_slots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    round_no: Mapped[int] = mapped_column(Integer, nullable=False)
    table_no: Mapped[int] = mapped_column(Integer, nullable=False)
    ns_pair_code: Mapped[str] = mapped_column(String(20), nullable=False)
    ew_pair_code: Mapped[str] = mapped_column(String(20), nullable=False)

    __table_args__ = (
        UniqueConstraint("event_id", "round_no", "table_no", name="uq_movement_slot"),
        CheckConstraint("ns_pair_code <> ew_pair_code", name="ck_movement_distinct_pairs"),
        CheckConstraint("round_no > 0 AND table_no > 0", name="ck_movement_positive"),
    )


class BoardAssignment(Base):
    __tablename__ = "board_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    round_no: Mapped[int] = mapped_column(Integer, nullable=False)
    table_no: Mapped[int] = mapped_column(Integer, nullable=False)
    board_no: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("event_id", "round_no", "table_no", "board_no", name="uq_board_assignment"),
        CheckConstraint("board_no > 0", name="ck_board_no_positive"),
    )


class BoardResult(Base):
    __tablename__ = "board_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    board_no: Mapped[int] = mapped_column(Integer, nullable=False)
    table_no: Mapped[int] = mapped_column(Integer, nullable=False)
    round_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ns_pair_code: Mapped[str] = mapped_column(String(20), nullable=False)
    ew_pair_code: Mapped[str] = mapped_column(String(20), nullable=False)

    # passout is an explicit result; a board with no BoardResult row is missing
    # and must remain excluded from the matchpoint comparison.
    is_passout: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    declarer: Mapped[str | None] = mapped_column(String(1), nullable=True)
    level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    denomination: Mapped[str | None] = mapped_column(String(2), nullable=True)
    penalty: Mapped[str] = mapped_column(String(2), default="NONE", nullable=False)
    overtricks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    undertricks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    vulnerability_code: Mapped[str] = mapped_column(String(4), nullable=False)
    contract_label: Mapped[str | None] = mapped_column(String(20), nullable=True)
    score_ns: Mapped[int] = mapped_column(Integer, nullable=False)
    score_ew: Mapped[int] = mapped_column(Integer, nullable=False)

    source_ref: Mapped[str] = mapped_column(String(120), nullable=False)
    entered_by: Mapped[str] = mapped_column(String(120), nullable=False)
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", nullable=False)
    superseded_by_id: Mapped[int | None] = mapped_column(ForeignKey("board_results.id"), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    __table_args__ = (
        Index(
            "uq_result_one_active_per_board_table",
            "event_id",
            "board_no",
            "table_no",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
            sqlite_where=text("status = 'ACTIVE'"),
        ),
        CheckConstraint("overtricks = 0 OR undertricks = 0", name="ck_trick_delta"),
        CheckConstraint("overtricks >= 0 AND undertricks >= 0", name="ck_tricks_non_negative"),
    )


class Publication(Base):
    __tablename__ = "publications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    board_count: Mapped[int] = mapped_column(Integer, nullable=False)
    result_count: Mapped[int] = mapped_column(Integer, nullable=False)
    comparison: Mapped[dict] = mapped_column(JSON, nullable=False)
    rankings: Mapped[dict] = mapped_column(JSON, nullable=False)

    board_scores: Mapped[list["PublicationBoardScore"]] = relationship(cascade="all, delete-orphan")


class PublicationBoardScore(Base):
    __tablename__ = "publication_board_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    publication_id: Mapped[int] = mapped_column(ForeignKey("publications.id", ondelete="CASCADE"), nullable=False)
    board_no: Mapped[int] = mapped_column(Integer, nullable=False)
    table_no: Mapped[int] = mapped_column(Integer, nullable=False)
    ns_pair_code: Mapped[str] = mapped_column(String(20), nullable=False)
    ew_pair_code: Mapped[str] = mapped_column(String(20), nullable=False)
    contract_label: Mapped[str | None] = mapped_column(String(20), nullable=True)
    score_ns: Mapped[int] = mapped_column(Integer, nullable=False)
    score_ew: Mapped[int] = mapped_column(Integer, nullable=False)
    ns_matchpoints: Mapped[float] = mapped_column(Float, nullable=False)
    ew_matchpoints: Mapped[float] = mapped_column(Float, nullable=False)
    comparison_set_size: Mapped[int] = mapped_column(Integer, nullable=False)
    source_result_id: Mapped[int] = mapped_column(ForeignKey("board_results.id"), nullable=False)

    __table_args__ = (UniqueConstraint("publication_id", "board_no", "table_no"),)
