"""Tests for the read-only build-file inspector."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from lpbf_serializer.buildfile.inspector import (
    BuildFileInspectionError,
    EntryKind,
    inspect_build_file,
)


def _make_zip(path: Path, members: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return path


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(BuildFileInspectionError, match="not found"):
        inspect_build_file(tmp_path / "ghost.mtt")


def test_not_a_zip(tmp_path: Path) -> None:
    p = tmp_path / "raw.amx"
    p.write_bytes(b"not-a-zip" + b"\x00" * 512)
    report = inspect_build_file(p)
    assert report.is_zip is False
    assert report.entries == ()
    assert "not-a-zip-archive" in report.notes
    assert len(report.magic_hex) >= 64
    assert len(report.file_sha256) == 64


def test_zip_classification(tmp_path: Path) -> None:
    stl_bin = b"\x00" * 80 + b"\x02\x00\x00\x00" + b"\x00" * 100
    stl_ascii = b"solid foo\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\n"
    ini = b"[machine]\nbuild=B150\n"
    xml = b"<?xml version='1.0'?><root/>"
    json_data = b'{"k": 1}'
    binary_blob = bytes(range(256)) * 4

    p = _make_zip(
        tmp_path / "sample.mtt",
        {
            "parts/001.stl": stl_bin,
            "parts/002.stl": stl_ascii,
            "machine.ini": ini,
            "meta/info.xml": xml,
            "meta/info.json": json_data,
            "thumb.png": binary_blob,
        },
    )
    report = inspect_build_file(p)
    assert report.is_zip is True
    assert len(report.entries) == 6

    by_name = {e.name: e for e in report.entries}
    assert by_name["parts/001.stl"].kind is EntryKind.STL_BINARY
    assert by_name["parts/002.stl"].kind is EntryKind.STL_ASCII
    assert by_name["machine.ini"].kind is EntryKind.INI
    assert by_name["machine.ini"].text_content is not None
    assert "build=B150" in by_name["machine.ini"].text_content
    assert by_name["meta/info.xml"].kind is EntryKind.XML
    assert by_name["meta/info.json"].kind is EntryKind.JSON
    assert by_name["thumb.png"].kind is EntryKind.BINARY
    assert by_name["thumb.png"].text_content is None


def test_very_large_text_member_is_truncated(tmp_path: Path) -> None:
    big = b"x=1\n" * 1_000_000
    p = _make_zip(tmp_path / "big.mtt", {"notes.txt": big})
    report = inspect_build_file(p)
    entry = next(e for e in report.entries if e.name == "notes.txt")
    assert any(n.startswith("text-truncated") for n in entry.notes)
    assert entry.text_content is None
