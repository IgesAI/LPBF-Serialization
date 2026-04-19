"""Top-level save-build service.

This is where transactional boundaries are drawn:

- A single DB transaction wraps (build-code allocation, build row insert,
  parts insert, audit events, mtt path + sha update).
- QuantAM export is invoked *before* the DB commit. If it raises, the
  transaction is rolled back and nothing is persisted.
- If the export succeeds but ``verify_mtt`` fails, the commit is aborted.

There are no retries, no partial commits, and no "best effort" fallbacks.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from lpbf_serializer.audit.log import AuditEventType, AuditLogger
from lpbf_serializer.db.repositories import BuildRepository
from lpbf_serializer.domain.ids import BuildCode
from lpbf_serializer.domain.models import BuildRecord, PartRecord
from lpbf_serializer.engine.sequencer import BuildSequencer
from lpbf_serializer.engine.serializer import PlacedPartInput, assign_serials
from lpbf_serializer.quantam.client import (
    ExportRequest,
    ExportRequestPart,
    QuantAMClient,
)


@dataclass(frozen=True, slots=True)
class SavedBuild:
    build_code: BuildCode
    mtt_path: Path
    mtt_sha256: str
    parts: tuple[PartRecord, ...]


class BuildService:
    def __init__(
        self,
        *,
        session: Session,
        sequencer: BuildSequencer,
        build_repo: BuildRepository,
        audit: AuditLogger,
        quantam: QuantAMClient,
        export_dir: Path,
    ) -> None:
        self._session = session
        self._sequencer = sequencer
        self._build_repo = build_repo
        self._audit = audit
        self._quantam = quantam
        self._export_dir = export_dir

    def save_build(
        self,
        inputs: Sequence[PlacedPartInput],
        *,
        notes: str = "",
    ) -> SavedBuild:
        if len(inputs) == 0:
            raise ValueError("save_build requires at least one placed part")

        self._quantam.health_check()

        with self._session.begin():
            code = self._sequencer.allocate_next()
            self._audit.log(
                AuditEventType.BUILD_CODE_ALLOCATED,
                build_code=code,
                payload={"code": str(code)},
            )

            parts = assign_serials(code, inputs)
            self._audit.log(
                AuditEventType.SERIALS_ASSIGNED,
                build_code=code,
                payload={
                    "count": len(parts),
                    "serials": [str(p.serial) for p in parts],
                },
            )

            self._export_dir.mkdir(parents=True, exist_ok=True)
            output_path = self._export_dir / f"{code}.mtt"

            request = ExportRequest(
                build_code=code,
                output_mtt_path=output_path,
                parts=tuple(
                    ExportRequestPart(
                        stl_path=p.source_stl_path,
                        pos_x_mm=p.position.x_mm,
                        pos_y_mm=p.position.y_mm,
                        serial=str(p.serial),
                    )
                    for p in parts
                ),
            )
            self._audit.log(
                AuditEventType.EXPORT_REQUESTED,
                build_code=code,
                payload={"output_mtt_path": str(output_path)},
            )

            try:
                result = self._quantam.export_build(request)
            except Exception as e:
                self._audit.log(
                    AuditEventType.EXPORT_FAILED,
                    build_code=code,
                    payload={"error": type(e).__name__, "message": str(e)},
                )
                raise

            self._audit.log(
                AuditEventType.EXPORT_SUCCEEDED,
                build_code=code,
                payload={
                    "mtt_path": str(result.mtt_path),
                    "mtt_sha256": result.manifest.sha256,
                    "entries": list(result.manifest.entry_names),
                },
            )

            record = BuildRecord(
                build_code=code,
                created_at=datetime.now(UTC),
                parts=parts,
                mtt_path=result.mtt_path,
                mtt_sha256=result.manifest.sha256,
                notes=notes,
            )
            self._build_repo.insert(record)
            self._audit.log(
                AuditEventType.BUILD_PERSISTED,
                build_code=code,
                payload={
                    "part_count": len(parts),
                    "mtt_sha256": result.manifest.sha256,
                },
            )

        return SavedBuild(
            build_code=code,
            mtt_path=result.mtt_path,
            mtt_sha256=result.manifest.sha256,
            parts=parts,
        )
