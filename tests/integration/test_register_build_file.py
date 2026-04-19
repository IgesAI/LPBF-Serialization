"""Integration test for sidecar build-file registration."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from lpbf_serializer.audit.log import AuditLogger
from lpbf_serializer.audit.plate_token import generate_plate_token
from lpbf_serializer.audit.report import generate_build_report
from lpbf_serializer.buildfile.mtt_reader import (
    ENVELOPE_MAGIC,
    MTT_LAYER_TAG,
    NoPartNamesFoundError,
)
from lpbf_serializer.db.engine import create_engine_and_session, run_migrations
from lpbf_serializer.db.repositories import BuildRepository
from lpbf_serializer.db.schema import AuditEventRow, BuildRow
from lpbf_serializer.domain.models import BuildFileFormat
from lpbf_serializer.engine.sequencer import BuildSequencer
from lpbf_serializer.engine.service import BuildService
from lpbf_serializer.quantam.client import (
    ExportRequest,
    ExportResult,
    MttManifest,
    QuantAMInfo,
)


class _NullQuantAM:
    def health_check(self) -> QuantAMInfo:
        return QuantAMInfo(exe_path=Path(), version="sidecar-no-export")

    def export_build(self, request: ExportRequest) -> ExportResult:
        del request
        raise RuntimeError("export not used in sidecar test")

    def verify_mtt(self, path: Path) -> MttManifest:
        del path
        raise RuntimeError("verify not used in sidecar test")


def _fake_mtt(path: Path, names: list[str]) -> Path:
    buf = bytearray(ENVELOPE_MAGIC) + b"\x00\x00"
    buf += bytes([len(MTT_LAYER_TAG) + 1]) + MTT_LAYER_TAG + b"\x00"
    for n in names:
        utf = n.encode("utf-16-le") + b"\x00\x00"
        buf += b"\x01\x07\x20" + bytes([len(utf)]) + utf
    path.write_bytes(bytes(buf))
    return path


@pytest.fixture
def session(tmp_path: Path) -> Session:
    url = f"sqlite:///{(tmp_path / 'reg.sqlite3').as_posix()}"
    run_migrations(url)
    _, factory = create_engine_and_session(url)
    return factory()


def _service(session: Session) -> BuildService:
    return BuildService(
        session=session,
        sequencer=BuildSequencer(session, prefix="B#", digits=4),
        build_repo=BuildRepository(session, prefix="B#", digits=4),
        audit=AuditLogger(session, actor="tester"),
        quantam=_NullQuantAM(),
        export_dir=Path("ignored"),
    )


def test_register_sidecar_happy_path(
    session: Session, tmp_path: Path
) -> None:
    mtt = _fake_mtt(
        tmp_path / "EC5L0020 - ENGINE CASE - FRONT - B150.mtt",
        [
            "EC5L0020 - ENGINE CASE - FRONT - B150P",
            "EC5L0021 - ENGINE CASE - REAR - B150P",
        ],
    )
    svc = _service(session)
    saved = svc.register_build_file(mtt, notes="integration test")

    assert str(saved.build_code) == "B#0001"
    assert saved.mtt_path is None
    assert saved.mtt_sha256 is None
    assert saved.source_build_file is not None
    assert saved.source_build_file.format is BuildFileFormat.MTT
    assert [str(p.serial) for p in saved.parts] == ["B#0001-1", "B#0001-2"]
    assert [p.part_name for p in saved.parts] == [
        "EC5L0020 - ENGINE CASE - FRONT - B150P",
        "EC5L0021 - ENGINE CASE - REAR - B150P",
    ]

    row = session.query(BuildRow).one()
    assert row.source_build_file_path is not None
    assert row.source_build_file_sha256 == saved.source_build_file.file_sha256
    assert row.source_build_file_format == "mtt"
    assert all(p.pos_x is None and p.stl_path is None for p in row.parts)
    assert [p.part_name for p in row.parts] == [
        "EC5L0020 - ENGINE CASE - FRONT - B150P",
        "EC5L0021 - ENGINE CASE - REAR - B150P",
    ]

    events = session.query(AuditEventRow).all()
    assert any(e.event_type == "build.code_allocated" for e in events)
    assert any(e.event_type == "build.serials_assigned" for e in events)
    assert any(e.event_type == "build.persisted" for e in events)


def test_register_produces_pdf_and_plate_token(
    session: Session, tmp_path: Path
) -> None:
    mtt = _fake_mtt(tmp_path / "demo.mtt", ["partAlpha", "partBeta"])
    svc = _service(session)
    saved = svc.register_build_file(mtt)

    report_pdf = generate_build_report(
        session,
        saved.build_code,
        output_path=tmp_path / "report.pdf",
        plate_width_mm=250.0,
        plate_depth_mm=250.0,
    )
    token_pdf = generate_plate_token(
        session,
        saved.build_code,
        output_path=tmp_path / "token.pdf",
    )
    assert report_pdf.read_bytes().startswith(b"%PDF-")
    assert token_pdf.read_bytes().startswith(b"%PDF-")
    assert token_pdf.stat().st_size > 1500


def test_register_refuses_mtt_with_no_part_names(
    session: Session, tmp_path: Path
) -> None:
    mtt = _fake_mtt(tmp_path / "empty.mtt", [])
    svc = _service(session)
    with pytest.raises(NoPartNamesFoundError):
        svc.register_build_file(mtt)
    assert session.query(BuildRow).count() == 0
    assert session.query(AuditEventRow).count() == 0
