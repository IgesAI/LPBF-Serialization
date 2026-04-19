"""Initial schema: builds, parts, build_counter, audit_events.

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "build_counter",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("next_value", sa.Integer(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_build_counter_singleton"),
    )
    op.bulk_insert(
        sa.table(
            "build_counter",
            sa.column("id", sa.Integer()),
            sa.column("next_value", sa.Integer()),
        ),
        [{"id": 1, "next_value": 1}],
    )

    op.create_table(
        "builds",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("build_code", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("mtt_path", sa.Text(), nullable=True),
        sa.Column("mtt_sha256", sa.String(length=64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.UniqueConstraint("build_code", name="uq_builds_build_code"),
    )
    op.create_index("ix_builds_created_at", "builds", ["created_at"])

    op.create_table(
        "parts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("build_id", sa.Integer(), nullable=False),
        sa.Column("part_number", sa.Integer(), nullable=False),
        sa.Column("serial_id", sa.String(length=64), nullable=False),
        sa.Column("pos_x", sa.Float(), nullable=False),
        sa.Column("pos_y", sa.Float(), nullable=False),
        sa.Column("stl_path", sa.Text(), nullable=False),
        sa.Column("mesh_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "qa_status", sa.String(length=16), nullable=False, server_default="pending"
        ),
        sa.ForeignKeyConstraint(
            ["build_id"],
            ["builds.id"],
            ondelete="CASCADE",
            name="fk_parts_build_id",
        ),
        sa.UniqueConstraint("serial_id", name="uq_parts_serial_id"),
        sa.UniqueConstraint("build_id", "part_number", name="uq_parts_build_number"),
        sa.CheckConstraint("part_number >= 1", name="ck_parts_part_number_positive"),
    )
    op.create_index("ix_parts_build_id", "parts", ["build_id"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("build_code", sa.String(length=32), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_audit_events_occurred_at", "audit_events", ["occurred_at"]
    )
    op.create_index(
        "ix_audit_events_build_code", "audit_events", ["build_code"]
    )


def downgrade() -> None:
    op.drop_index("ix_audit_events_build_code", table_name="audit_events")
    op.drop_index("ix_audit_events_occurred_at", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_parts_build_id", table_name="parts")
    op.drop_table("parts")
    op.drop_index("ix_builds_created_at", table_name="builds")
    op.drop_table("builds")
    op.drop_table("build_counter")
