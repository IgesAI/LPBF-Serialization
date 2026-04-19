"""Tests for the .mtt ZIP manifest reader."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from lpbf_serializer.quantam.errors import QuantAMVerificationFailedError
from lpbf_serializer.quantam.manifest import read_mtt_manifest


def _make_mtt(path: Path, entries: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return path


def test_reads_valid_mtt(tmp_path: Path) -> None:
    p = _make_mtt(
        tmp_path / "ok.mtt",
        {"model.stl": b"solid x\nendsolid\n", "machine.ini": b"[mach]\n"},
    )
    manifest = read_mtt_manifest(p)
    assert manifest.mtt_path == p
    assert "model.stl" in manifest.entry_names
    assert len(manifest.sha256) == 64


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(QuantAMVerificationFailedError, match="not found"):
        read_mtt_manifest(tmp_path / "ghost.mtt")


def test_wrong_extension(tmp_path: Path) -> None:
    p = tmp_path / "x.zip"
    p.write_bytes(b"PK\x03\x04")
    with pytest.raises(QuantAMVerificationFailedError, match="Not an .mtt file"):
        read_mtt_manifest(p)


def test_invalid_zip(tmp_path: Path) -> None:
    p = tmp_path / "bad.mtt"
    p.write_bytes(b"not a zip")
    with pytest.raises(QuantAMVerificationFailedError, match="not a valid ZIP"):
        read_mtt_manifest(p)


def test_empty_archive(tmp_path: Path) -> None:
    p = _make_mtt(tmp_path / "empty.mtt", {})
    with pytest.raises(QuantAMVerificationFailedError, match="empty"):
        read_mtt_manifest(p)


def test_no_stl_entries(tmp_path: Path) -> None:
    p = _make_mtt(tmp_path / "nostl.mtt", {"machine.ini": b"x"})
    with pytest.raises(QuantAMVerificationFailedError, match="no STL"):
        read_mtt_manifest(p)
