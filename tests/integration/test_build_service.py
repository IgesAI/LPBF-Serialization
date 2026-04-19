"""End-to-end test of BuildService with a stubbed QuantAM backend.

This validates the transactional contract: on export failure nothing is
persisted; on success the DB row, audit trail, and returned SavedBuild
agree byte-for-byte on the mtt hash.

Note: the stub here is a *test* double. Production code never selects it.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from lpbf_serializer.audit.log import AuditLogger
from lpbf_serializer.db.engine import create_engine_and_session, run_migrations
from lpbf_serializer.db.repositories import BuildRepository
from lpbf_serializer.db.schema import AuditEventRow, BuildRow
from lpbf_serializer.domain.models import PlatePosition
from lpbf_serializer.engine.sequencer import BuildSequencer
from lpbf_serializer.engine.serializer import PlacedPartInput
from lpbf_serializer.engine.service import BuildService
from lpbf_serializer.quantam.client import (
    ExportRequest,
    ExportResult,
    MttManifest,
    QuantAMInfo,
)
from lpbf_serializer.quantam.errors import QuantAMExportFailedError


class _FakeQuantAM:
    def __init__(self, *, fail_export: bool = False) -> None:
        self.fail_export = fail_export
        self.health_calls = 0

    def health_check(self) -> QuantAMInfo:
        self.health_calls += 1
        return QuantAMInfo(exe_path=Path("C:/fake/QuantAM.exe"), version="6.1.0.1")

    def export_build(self, request: ExportRequest) -> ExportResult:
        if self.fail_export:
            raise QuantAMExportFailedError("simulated QuantAM failure")
        payload = "|".join(
            f"{p.serial}@({p.pos_x_mm},{p.pos_y_mm})" for p in request.parts
        ).encode()
        request.output_mtt_path.parent.mkdir(parents=True, exist_ok=True)
        request.output_mtt_path.write_bytes(payload)
        sha = hashlib.sha256(payload).hexdigest()
        return ExportResult(
            mtt_path=request.output_mtt_path,
            manifest=MttManifest(
                mtt_path=request.output_mtt_path,
                sha256=sha,
                entry_names=tuple(str(p.stl_path) for p in request.parts),
            ),
        )

    def verify_mtt(self, path: Path) -> MttManifest:
        data = path.read_bytes()
        return MttManifest(
            mtt_path=path, sha256=hashlib.sha256(data).hexdigest(), entry_names=()
        )


@pytest.fixture
def session(tmp_path: Path) -> Session:
    url = f"sqlite:///{(tmp_path / 'svc.sqlite3').as_posix()}"
    run_migrations(url)
    _, factory = create_engine_and_session(url)
    return factory()


def _inputs(stl: Path) -> list[PlacedPartInput]:
    return [
        PlacedPartInput(
            source_stl_path=stl,
            mesh_sha256="0" * 64,
            position=PlatePosition(x_mm=0.0, y_mm=0.0),
        ),
        PlacedPartInput(
            source_stl_path=stl,
            mesh_sha256="0" * 64,
            position=PlatePosition(x_mm=15.0, y_mm=0.0),
        ),
    ]


def _make_service(
    session: Session, quantam: _FakeQuantAM, tmp_path: Path
) -> BuildService:
    return BuildService(
        session=session,
        sequencer=BuildSequencer(session, prefix="B#", digits=4),
        build_repo=BuildRepository(session, prefix="B#", digits=4),
        audit=AuditLogger(session, actor="tester"),
        quantam=quantam,
        export_dir=tmp_path / "mtt",
    )


def test_save_build_happy_path(
    session: Session, tmp_path: Path, cube_stl: Path
) -> None:
    svc = _make_service(session, _FakeQuantAM(), tmp_path)
    saved = svc.save_build(_inputs(cube_stl), notes="first run")

    assert str(saved.build_code) == "B#0001"
    assert saved.mtt_path is not None
    assert saved.mtt_sha256 is not None
    assert saved.mtt_path.exists()
    assert saved.mtt_sha256 == hashlib.sha256(saved.mtt_path.read_bytes()).hexdigest()
    assert [str(p.serial) for p in saved.parts] == ["B#0001-1", "B#0001-2"]

    row = session.get(BuildRow, 1)
    assert row is not None
    assert row.build_code == "B#0001"
    assert row.mtt_sha256 == saved.mtt_sha256
    assert len(row.parts) == 2

    events = session.query(AuditEventRow).order_by(AuditEventRow.id).all()
    types = [e.event_type for e in events]
    assert "build.code_allocated" in types
    assert "quantam.export_succeeded" in types
    assert "build.persisted" in types


def test_save_build_export_failure_rolls_back(
    session: Session, tmp_path: Path, cube_stl: Path
) -> None:
    svc = _make_service(session, _FakeQuantAM(fail_export=True), tmp_path)

    with pytest.raises(QuantAMExportFailedError):
        svc.save_build(_inputs(cube_stl))

    assert session.query(BuildRow).count() == 0
    assert session.query(AuditEventRow).count() == 0


def test_sequencer_advances_only_on_success(
    session: Session, tmp_path: Path, cube_stl: Path
) -> None:
    failing = _FakeQuantAM(fail_export=True)
    svc_bad = _make_service(session, failing, tmp_path)
    with pytest.raises(QuantAMExportFailedError):
        svc_bad.save_build(_inputs(cube_stl))

    good = _FakeQuantAM()
    svc_good = BuildService(
        session=session,
        sequencer=BuildSequencer(session, prefix="B#", digits=4),
        build_repo=BuildRepository(session, prefix="B#", digits=4),
        audit=AuditLogger(session, actor="tester"),
        quantam=good,
        export_dir=tmp_path / "mtt",
    )
    saved = svc_good.save_build(_inputs(cube_stl))
    assert str(saved.build_code) == "B#0001"


def test_export_request_rejects_empty_parts() -> None:
    from lpbf_serializer.domain.ids import BuildCode

    with pytest.raises(ValueError, match="at least one part"):
        ExportRequest(
            build_code=BuildCode(prefix="B#", number=1, digits=4),
            output_mtt_path=Path("x.mtt"),
            parts=(),
        )


def test_export_request_requires_mtt_extension() -> None:
    from lpbf_serializer.domain.ids import BuildCode
    from lpbf_serializer.quantam.client import ExportRequestPart

    with pytest.raises(ValueError, match=r"\.mtt"):
        ExportRequest(
            build_code=BuildCode(prefix="B#", number=1, digits=4),
            output_mtt_path=Path("x.zip"),
            parts=(
                ExportRequestPart(
                    stl_path=Path("a.stl"), pos_x_mm=0, pos_y_mm=0, serial="B#0001-1"
                ),
            ),
        )
