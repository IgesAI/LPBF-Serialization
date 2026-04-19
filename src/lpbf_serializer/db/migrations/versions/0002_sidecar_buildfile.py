"""Support sidecar-registered builds (no STL drag-place required).

Adds:
- builds.source_build_file_path, source_build_file_sha256, source_build_file_format
- parts.part_name
And relaxes the NOT NULL on parts.pos_x, parts.pos_y, parts.stl_path,
parts.mesh_sha256 because a sidecar-registered build derives parts from
an external binary we do not crack open.

Revision ID: 0002_sidecar_buildfile
Revises: 0001_initial
Create Date: 2026-04-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_sidecar_buildfile"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("builds") as batch:
        batch.add_column(
            sa.Column("source_build_file_path", sa.Text(), nullable=True)
        )
        batch.add_column(
            sa.Column("source_build_file_sha256", sa.String(length=64), nullable=True)
        )
        batch.add_column(
            sa.Column("source_build_file_format", sa.String(length=16), nullable=True)
        )

    with op.batch_alter_table("parts") as batch:
        batch.add_column(sa.Column("part_name", sa.Text(), nullable=True))
        batch.alter_column("pos_x", existing_type=sa.Float(), nullable=True)
        batch.alter_column("pos_y", existing_type=sa.Float(), nullable=True)
        batch.alter_column("stl_path", existing_type=sa.Text(), nullable=True)
        batch.alter_column(
            "mesh_sha256", existing_type=sa.String(length=64), nullable=True
        )


def downgrade() -> None:
    with op.batch_alter_table("parts") as batch:
        batch.alter_column(
            "mesh_sha256",
            existing_type=sa.String(length=64),
            nullable=False,
        )
        batch.alter_column("stl_path", existing_type=sa.Text(), nullable=False)
        batch.alter_column("pos_y", existing_type=sa.Float(), nullable=False)
        batch.alter_column("pos_x", existing_type=sa.Float(), nullable=False)
        batch.drop_column("part_name")

    with op.batch_alter_table("builds") as batch:
        batch.drop_column("source_build_file_format")
        batch.drop_column("source_build_file_sha256")
        batch.drop_column("source_build_file_path")
