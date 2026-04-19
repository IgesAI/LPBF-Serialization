"""Repository layer: narrow, typed access to the ORM.

Repositories never commit. The caller controls the transaction boundary so
that build persistence + audit logging + QuantAM export status all share a
single atomic unit.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from lpbf_serializer.db.schema import BuildRow, PartRow
from lpbf_serializer.domain.ids import BuildCode, PartSerial
from lpbf_serializer.domain.models import BuildRecord, PartRecord


class DuplicateBuildCodeError(Exception):
    """Raised when an attempt is made to insert an existing build code."""


class BuildNotFoundError(Exception):
    """Raised when a lookup by build code finds nothing."""


class BuildRepository:
    def __init__(self, session: Session, *, prefix: str, digits: int) -> None:
        self._session = session
        self._prefix = prefix
        self._digits = digits

    def insert(self, record: BuildRecord) -> BuildRow:
        existing = self._session.execute(
            select(BuildRow).where(BuildRow.build_code == str(record.build_code))
        ).scalar_one_or_none()
        if existing is not None:
            raise DuplicateBuildCodeError(str(record.build_code))

        row = BuildRow(
            build_code=str(record.build_code),
            created_at=record.created_at,
            mtt_path=str(record.mtt_path) if record.mtt_path is not None else None,
            mtt_sha256=record.mtt_sha256,
            source_build_file_path=(
                str(record.source_build_file_path)
                if record.source_build_file_path is not None
                else None
            ),
            source_build_file_sha256=record.source_build_file_sha256,
            source_build_file_format=(
                record.source_build_file_format.value
                if record.source_build_file_format is not None
                else None
            ),
            notes=record.notes,
        )
        row.parts = [self._part_row(p) for p in record.parts]
        self._session.add(row)
        self._session.flush()
        return row

    def update_mtt(self, build_code: BuildCode, *, path: str, sha256: str) -> None:
        row = self._require_row(build_code)
        row.mtt_path = path
        row.mtt_sha256 = sha256
        self._session.flush()

    def get(self, build_code: BuildCode) -> BuildRow:
        return self._require_row(build_code)

    def list_recent(self, limit: int = 50) -> Sequence[BuildRow]:
        stmt = select(BuildRow).order_by(BuildRow.created_at.desc()).limit(limit)
        return self._session.execute(stmt).scalars().all()

    def _require_row(self, build_code: BuildCode) -> BuildRow:
        row = self._session.execute(
            select(BuildRow).where(BuildRow.build_code == str(build_code))
        ).scalar_one_or_none()
        if row is None:
            raise BuildNotFoundError(str(build_code))
        return row

    @staticmethod
    def _part_row(p: PartRecord) -> PartRow:
        return PartRow(
            part_number=p.part_number,
            serial_id=str(p.serial),
            part_name=p.part_name,
            pos_x=p.position.x_mm if p.position is not None else None,
            pos_y=p.position.y_mm if p.position is not None else None,
            stl_path=(
                str(p.source_stl_path) if p.source_stl_path is not None else None
            ),
            mesh_sha256=p.mesh_sha256,
            qa_status=p.qa_status.value,
        )


class PartRepository:
    def __init__(self, session: Session, *, prefix: str, digits: int) -> None:
        self._session = session
        self._prefix = prefix
        self._digits = digits

    def find_by_serial(self, serial: PartSerial) -> PartRow:
        row = self._session.execute(
            select(PartRow).where(PartRow.serial_id == str(serial))
        ).scalar_one_or_none()
        if row is None:
            raise BuildNotFoundError(str(serial))
        return row

    def list_for_build(self, build_code: BuildCode) -> Sequence[PartRow]:
        stmt = (
            select(PartRow)
            .join(BuildRow, PartRow.build_id == BuildRow.id)
            .where(BuildRow.build_code == str(build_code))
            .order_by(PartRow.part_number)
        )
        return self._session.execute(stmt).scalars().all()

    def replace_for_build(self, build_row: BuildRow, parts: Iterable[PartRecord]) -> None:
        build_row.parts = [BuildRepository._part_row(p) for p in parts]
        self._session.flush()
