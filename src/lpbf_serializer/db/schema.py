"""SQLAlchemy ORM schema.

The schema intentionally has no server-side defaults for business fields
(``build_code``, ``serial_id``). Those values are *always* issued by the
application sequencer inside a transaction, so that nothing can persist a
row with a fabricated or missing identifier.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class BuildCounterRow(Base):
    """Single-row table holding the next build number to allocate."""

    __tablename__ = "build_counter"
    __table_args__ = (CheckConstraint("id = 1", name="ck_build_counter_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    next_value: Mapped[int] = mapped_column(Integer, nullable=False)


class BuildRow(Base):
    __tablename__ = "builds"
    __table_args__ = (UniqueConstraint("build_code", name="uq_builds_build_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    build_code: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    mtt_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    mtt_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_build_file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_build_file_sha256: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    source_build_file_format: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")

    parts: Mapped[list[PartRow]] = relationship(
        back_populates="build",
        cascade="all, delete-orphan",
        order_by="PartRow.part_number",
    )


class PartRow(Base):
    __tablename__ = "parts"
    __table_args__ = (
        UniqueConstraint("serial_id", name="uq_parts_serial_id"),
        UniqueConstraint("build_id", "part_number", name="uq_parts_build_number"),
        CheckConstraint("part_number >= 1", name="ck_parts_part_number_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    build_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("builds.id", ondelete="CASCADE"), nullable=False
    )
    part_number: Mapped[int] = mapped_column(Integer, nullable=False)
    serial_id: Mapped[str] = mapped_column(String(64), nullable=False)
    part_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    pos_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    pos_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    stl_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    mesh_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    qa_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")

    build: Mapped[BuildRow] = relationship(back_populates="parts")


class AuditEventRow(Base):
    """Append-only audit events. No row may be updated or deleted."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    build_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
