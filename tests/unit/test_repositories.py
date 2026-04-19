"""Tests for BuildRepository and PartRepository."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from lpbf_serializer.db.engine import create_engine_and_session, run_migrations
from lpbf_serializer.db.repositories import (
    BuildNotFoundError,
    BuildRepository,
    DuplicateBuildCodeError,
    PartRepository,
)
from lpbf_serializer.domain.ids import BuildCode, PartSerial
from lpbf_serializer.domain.models import (
    BuildRecord,
    PartRecord,
    PlatePosition,
    QAStatus,
)


def _session(tmp_path: Path) -> Session:
    url = f"sqlite:///{(tmp_path / 'repo.sqlite3').as_posix()}"
    run_migrations(url)
    _, factory = create_engine_and_session(url)
    return factory()


def _record(code: BuildCode, count: int) -> BuildRecord:
    parts = tuple(
        PartRecord(
            serial=PartSerial(build_code=code, index=i + 1),
            part_number=i + 1,
            position=PlatePosition(x_mm=float(i * 15), y_mm=0.0),
            source_stl_path=Path(f"C:/parts/part{i + 1}.stl"),
            mesh_sha256="a" * 64,
            qa_status=QAStatus.PENDING,
        )
        for i in range(count)
    )
    return BuildRecord(
        build_code=code,
        created_at=datetime.now(timezone.utc),
        parts=parts,
    )


def test_insert_and_get(tmp_path: Path) -> None:
    s = _session(tmp_path)
    repo = BuildRepository(s, prefix="B#", digits=4)
    code = BuildCode(prefix="B#", number=1, digits=4)
    with s.begin():
        repo.insert(_record(code, 2))
    with s.begin():
        row = repo.get(code)
        assert row.build_code == "B#0001"
        assert len(row.parts) == 2


def test_duplicate_insert_raises(tmp_path: Path) -> None:
    s = _session(tmp_path)
    repo = BuildRepository(s, prefix="B#", digits=4)
    code = BuildCode(prefix="B#", number=1, digits=4)
    with s.begin():
        repo.insert(_record(code, 1))
    with s.begin(), pytest.raises(DuplicateBuildCodeError):
        repo.insert(_record(code, 1))


def test_not_found_raises(tmp_path: Path) -> None:
    s = _session(tmp_path)
    repo = BuildRepository(s, prefix="B#", digits=4)
    with s.begin(), pytest.raises(BuildNotFoundError):
        repo.get(BuildCode(prefix="B#", number=77, digits=4))


def test_update_mtt(tmp_path: Path) -> None:
    s = _session(tmp_path)
    repo = BuildRepository(s, prefix="B#", digits=4)
    code = BuildCode(prefix="B#", number=1, digits=4)
    with s.begin():
        repo.insert(_record(code, 1))
    with s.begin():
        repo.update_mtt(code, path="C:/out/B#0001.mtt", sha256="b" * 64)
    with s.begin():
        row = repo.get(code)
        assert row.mtt_path == "C:/out/B#0001.mtt"
        assert row.mtt_sha256 == "b" * 64


def test_list_recent_ordered(tmp_path: Path) -> None:
    s = _session(tmp_path)
    repo = BuildRepository(s, prefix="B#", digits=4)
    codes = [BuildCode(prefix="B#", number=i, digits=4) for i in (1, 2, 3)]
    for c in codes:
        with s.begin():
            repo.insert(_record(c, 1))
    with s.begin():
        rows = repo.list_recent(limit=10)
        assert [r.build_code for r in rows][0] == "B#0003"


def test_parts_repo_lookup(tmp_path: Path) -> None:
    s = _session(tmp_path)
    build_repo = BuildRepository(s, prefix="B#", digits=4)
    part_repo = PartRepository(s, prefix="B#", digits=4)
    code = BuildCode(prefix="B#", number=4, digits=4)
    with s.begin():
        build_repo.insert(_record(code, 3))
    with s.begin():
        parts = part_repo.list_for_build(code)
        assert len(parts) == 3
        found = part_repo.find_by_serial(
            PartSerial(build_code=code, index=2)
        )
        assert found.part_number == 2


def test_parts_repo_find_missing(tmp_path: Path) -> None:
    s = _session(tmp_path)
    part_repo = PartRepository(s, prefix="B#", digits=4)
    with s.begin(), pytest.raises(BuildNotFoundError):
        part_repo.find_by_serial(
            PartSerial(
                build_code=BuildCode(prefix="B#", number=99, digits=4),
                index=1,
            )
        )
