"""Developer demo harness.

NOT FOR PRODUCTION. This script drives the BuildService end-to-end using a
stubbed QuantAM client that writes a fake `.mtt` (a ZIP containing the
source STL and a minimal machine.ini). It exists so developers and
reviewers can exercise the sequencer, DB, engraving (optional), audit
log, and PDF report without a licensed QuantAM install.

Run:  uv run python scripts/dev_demo.py
Outputs:
  %LOCALAPPDATA%\\LPBFSerializer\\exported-mtt\\B#XXXX.mtt
  %LOCALAPPDATA%\\LPBFSerializer\\reports\\B#XXXX.pdf
  %LOCALAPPDATA%\\LPBFSerializer\\lpbf.sqlite3

The real production flow uses the UIA client in
lpbf_serializer.quantam.uia_client and refuses to run until automation
IDs are captured. That is intentional and unchanged by this script.
"""

from __future__ import annotations

import hashlib
import sys
import zipfile
from pathlib import Path

from lpbf_serializer.audit.log import AuditLogger
from lpbf_serializer.audit.report import generate_build_report
from lpbf_serializer.config import load_settings
from lpbf_serializer.db.engine import create_engine_and_session, run_migrations
from lpbf_serializer.db.repositories import BuildRepository
from lpbf_serializer.domain.models import PlatePosition
from lpbf_serializer.engine.sequencer import BuildSequencer
from lpbf_serializer.engine.serializer import PlacedPartInput
from lpbf_serializer.engine.service import BuildService
from lpbf_serializer.geometry.stl import load_stl
from lpbf_serializer.quantam.client import (
    ExportRequest,
    ExportResult,
    MttManifest,
    QuantAMInfo,
)


class _DevStubQuantAM:
    """Writes a structurally valid but fake .mtt ZIP. DEV ONLY."""

    def health_check(self) -> QuantAMInfo:
        return QuantAMInfo(
            exe_path=Path("C:/fake/QuantAM.exe"),
            version="dev-stub",
        )

    def export_build(self, request: ExportRequest) -> ExportResult:
        request.output_mtt_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(request.output_mtt_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for i, p in enumerate(request.parts, start=1):
                zf.writestr(
                    f"parts/{i:03d}_{p.serial}.stl",
                    p.stl_path.read_bytes(),
                )
            machine_ini = (
                "[machine]\n"
                f"build_code = {request.build_code}\n"
                f"part_count = {len(request.parts)}\n"
            )
            zf.writestr("machine.ini", machine_ini)

        data = request.output_mtt_path.read_bytes()
        with zipfile.ZipFile(request.output_mtt_path, "r") as zf:
            names = tuple(zf.namelist())
        return ExportResult(
            mtt_path=request.output_mtt_path,
            manifest=MttManifest(
                mtt_path=request.output_mtt_path,
                sha256=hashlib.sha256(data).hexdigest(),
                entry_names=names,
            ),
        )

    def verify_mtt(self, path: Path) -> MttManifest:
        with zipfile.ZipFile(path, "r") as zf:
            names = tuple(zf.namelist())
        return MttManifest(
            mtt_path=path,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            entry_names=names,
        )


def _find_demo_stls() -> list[Path]:
    candidates = [
        Path(
            r"C:\Program Files\Renishaw\Renishaw QuantAM 6.1.0.1\Samples\Demo Parts"
        ),
        Path(
            r"C:\Program Files\Renishaw\Renishaw QuantAM 6.1.0.1\Samples\Training Parts"
        ),
    ]
    stls: list[Path] = []
    for c in candidates:
        if c.is_dir():
            stls.extend(sorted(c.glob("*.stl")))
    return stls[:4]


def main() -> int:
    settings = load_settings()
    settings.ensure_dirs()
    run_migrations(settings.effective_database_url)

    stls = _find_demo_stls()
    if not stls:
        print(
            "No sample STLs found under Renishaw QuantAM samples directory.\n"
            "Pass at least one .stl path as an argument, e.g.:\n"
            "  uv run python scripts/dev_demo.py path/to/a.stl path/to/b.stl",
            file=sys.stderr,
        )
        if len(sys.argv) < 2:
            return 2
        stls = [Path(a) for a in sys.argv[1:]]

    print(f"Using {len(stls)} STL(s):")
    for s in stls:
        print(f"  - {s}")

    inputs: list[PlacedPartInput] = []
    cols = 2
    pitch = 80.0
    for i, stl_path in enumerate(stls):
        loaded = load_stl(stl_path)
        inputs.append(
            PlacedPartInput(
                source_stl_path=loaded.path,
                mesh_sha256=loaded.sha256,
                position=PlatePosition(
                    x_mm=20.0 + (i % cols) * pitch,
                    y_mm=20.0 + (i // cols) * pitch,
                ),
            )
        )

    _, session_factory = create_engine_and_session(settings.effective_database_url)
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
            audit=AuditLogger(session, actor="dev-demo"),
            quantam=_DevStubQuantAM(),
            export_dir=settings.export_dir,
        )
        saved = svc.save_build(inputs, notes="dev_demo.py run")

    with session_factory() as session:
        report = generate_build_report(
            session,
            saved.build_code,
            output_path=settings.report_dir / f"{saved.build_code}.pdf",
            plate_width_mm=settings.plate_width_mm,
            plate_depth_mm=settings.plate_depth_mm,
        )

    print("\nSaved:")
    print(f"  Build:   {saved.build_code}")
    print(f"  Parts:   {len(saved.parts)}")
    print(f"  MTT:     {saved.mtt_path}")
    print(f"  SHA-256: {saved.mtt_sha256}")
    print(f"  Report:  {report}")
    print(f"  DB:      {settings.db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
