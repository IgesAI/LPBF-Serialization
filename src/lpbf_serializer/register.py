"""Sidecar registration CLI.

Usage:
    uv run python -m lpbf_serializer.register <path-to-mtt|renam|amx>

Reads the header of the given Renishaw build file, allocates a build
code, assigns per-part serials in header order, persists everything
transactionally, and emits:

- a full build report PDF,
- a plate-token PDF with QR code.

The build file itself is not modified.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from lpbf_serializer.audit.log import AuditLogger
from lpbf_serializer.audit.plate_token import generate_plate_token
from lpbf_serializer.audit.report import generate_build_report
from lpbf_serializer.buildfile.mtt_reader import MttReaderError
from lpbf_serializer.config import load_settings
from lpbf_serializer.db.engine import create_engine_and_session, run_migrations
from lpbf_serializer.db.repositories import BuildRepository
from lpbf_serializer.engine.sequencer import BuildSequencer
from lpbf_serializer.engine.service import BuildService
from lpbf_serializer.quantam.client import (
    ExportRequest,
    ExportResult,
    MttManifest,
    QuantAMInfo,
)


class _NullQuantAM:
    """No-op QuantAM client used for sidecar-only registration.

    Sidecar registration never calls ``export_build`` (we do not produce
    an MTT; we consume one). ``health_check`` returns a sentinel. If any
    code path accidentally calls ``export_build`` against this client it
    raises - we do not silently succeed.
    """

    def health_check(self) -> QuantAMInfo:
        return QuantAMInfo(
            exe_path=Path(), version="sidecar-no-export"
        )

    def export_build(self, request: ExportRequest) -> ExportResult:
        del request
        raise RuntimeError(
            "export_build is not supported in sidecar registration mode"
        )

    def verify_mtt(self, path: Path) -> MttManifest:
        del path
        raise RuntimeError(
            "verify_mtt is not supported in sidecar registration mode"
        )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="lpbf_serializer.register",
        description=(
            "Register an already-prepared Renishaw build file into the "
            "LPBF serializer DB, assign per-part serials, and emit a "
            "PDF report + plate-token PDF. Does NOT modify the build file."
        ),
    )
    p.add_argument(
        "path",
        type=Path,
        help="Path to the .mtt / .renam / .amx file to register.",
    )
    p.add_argument(
        "--notes",
        default="",
        help="Free-text notes to attach to the persisted build row.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    if not args.path.is_file():
        print(f"error: file not found: {args.path}", file=sys.stderr)
        return 2

    settings = load_settings()
    settings.ensure_dirs()
    run_migrations(settings.effective_database_url)
    _, session_factory = create_engine_and_session(settings.effective_database_url)

    try:
        with session_factory() as session:
            svc = BuildService(
                session=session,
                sequencer=BuildSequencer(
                    session,
                    prefix=settings.build_code_prefix,
                    digits=settings.build_code_digits,
                ),
                build_repo=BuildRepository(
                    session,
                    prefix=settings.build_code_prefix,
                    digits=settings.build_code_digits,
                ),
                audit=AuditLogger(session, actor="register-cli"),
                quantam=_NullQuantAM(),
                export_dir=settings.export_dir,
            )
            saved = svc.register_build_file(args.path, notes=args.notes)
    except MttReaderError as e:
        print(f"error: {type(e).__name__}: {e}", file=sys.stderr)
        return 3

    with session_factory() as session:
        report_pdf = generate_build_report(
            session,
            saved.build_code,
            output_path=settings.report_dir / f"{saved.build_code}.pdf",
            plate_width_mm=settings.plate_width_mm,
            plate_depth_mm=settings.plate_depth_mm,
        )
        token_pdf = generate_plate_token(
            session,
            saved.build_code,
            output_path=settings.report_dir / f"{saved.build_code}-plate-token.pdf",
        )

    print(f"Registered build: {saved.build_code}")
    print(f"  Source file: {args.path}")
    if saved.source_build_file is not None:
        print(f"  Format:      {saved.source_build_file.format.value}")
        print(f"  File size:   {saved.source_build_file.file_size_bytes:,} bytes")
        print(f"  File SHA256: {saved.source_build_file.file_sha256}")
        print(f"  Parts ({saved.source_build_file.part_count}):")
        for p in saved.parts:
            print(f"    {p.serial}  <-  {p.part_name}")
    print(f"  Report:      {report_pdf}")
    print(f"  Plate token: {token_pdf}")
    print(f"  DB:          {settings.db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
