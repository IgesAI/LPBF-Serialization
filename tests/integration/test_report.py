"""Verify the PDF report renders from a real saved build."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from lpbf_serializer.audit.log import AuditLogger
from lpbf_serializer.audit.report import ReportError, generate_build_report
from lpbf_serializer.db.engine import create_engine_and_session, run_migrations
from lpbf_serializer.db.repositories import BuildRepository
from lpbf_serializer.domain.ids import BuildCode
from lpbf_serializer.domain.models import PlatePosition
from lpbf_serializer.engine.sequencer import BuildSequencer
from lpbf_serializer.engine.serializer import PlacedPartInput
from lpbf_serializer.engine.service import BuildService
from lpbf_serializer.quantam.client import ExportRequest, ExportResult, MttManifest


class _FakeQuantAM:
    def health_check(self):  # type: ignore[no-untyped-def]
        from lpbf_serializer.quantam.client import QuantAMInfo

        return QuantAMInfo(exe_path=Path("C:/fake.exe"), version="6.1.0.1")

    def export_build(self, request: ExportRequest) -> ExportResult:
        payload = b"|".join(
            f"{p.serial}@({p.pos_x_mm},{p.pos_y_mm})".encode() for p in request.parts
        )
        request.output_mtt_path.parent.mkdir(parents=True, exist_ok=True)
        request.output_mtt_path.write_bytes(payload)
        return ExportResult(
            mtt_path=request.output_mtt_path,
            manifest=MttManifest(
                mtt_path=request.output_mtt_path,
                sha256=hashlib.sha256(payload).hexdigest(),
                entry_names=tuple(p.stl_path.name for p in request.parts),
            ),
        )

    def verify_mtt(self, path: Path):  # type: ignore[no-untyped-def]
        data = path.read_bytes()
        return MttManifest(
            mtt_path=path, sha256=hashlib.sha256(data).hexdigest(), entry_names=()
        )


@pytest.fixture
def session(tmp_path: Path) -> Session:
    url = f"sqlite:///{(tmp_path / 'rep.sqlite3').as_posix()}"
    run_migrations(url)
    _, factory = create_engine_and_session(url)
    return factory()


def test_report_generation(session: Session, tmp_path: Path, cube_stl: Path) -> None:
    svc = BuildService(
        session=session,
        sequencer=BuildSequencer(session, prefix="B#", digits=4),
        build_repo=BuildRepository(session, prefix="B#", digits=4),
        audit=AuditLogger(session, actor="tester"),
        quantam=_FakeQuantAM(),
        export_dir=tmp_path / "mtt",
    )
    saved = svc.save_build(
        [
            PlacedPartInput(
                source_stl_path=cube_stl,
                mesh_sha256="a" * 64,
                position=PlatePosition(x_mm=20.0, y_mm=30.0),
            ),
            PlacedPartInput(
                source_stl_path=cube_stl,
                mesh_sha256="a" * 64,
                position=PlatePosition(x_mm=60.0, y_mm=30.0),
            ),
        ]
    )

    out = generate_build_report(
        session,
        saved.build_code,
        output_path=tmp_path / "report.pdf",
        plate_width_mm=250.0,
        plate_depth_mm=250.0,
    )
    data = out.read_bytes()
    assert data.startswith(b"%PDF-")
    assert len(data) > 2000


def test_report_missing_build(session: Session, tmp_path: Path) -> None:
    with pytest.raises(ReportError, match="No build row"):
        generate_build_report(
            session,
            BuildCode(prefix="B#", number=999, digits=4),
            output_path=tmp_path / "missing.pdf",
            plate_width_mm=250.0,
            plate_depth_mm=250.0,
        )
