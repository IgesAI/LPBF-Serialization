"""Tests for the narrow MTT header reader."""

from __future__ import annotations

from pathlib import Path

import pytest

from lpbf_serializer.buildfile.mtt_reader import (
    ENVELOPE_MAGIC,
    MTT_LAYER_TAG,
    NoPartNamesFoundError,
    UnrecognisedEnvelopeError,
    parse_build_file,
)
from lpbf_serializer.domain.models import BuildFileFormat


def _write_fake_mtt(path: Path, part_names: list[str]) -> Path:
    """Write a minimal file mimicking the layout we observed in real MTTs.

    Per-part TLV (empirically from a real QuantAM 6.1 .mtt):
        \\x01 \\x07 \\x20 <1-byte total length of utf16 including NUL>
        <utf16-le name bytes> \\x00 \\x00
    """
    buf = bytearray(ENVELOPE_MAGIC)
    buf += b"\x00\x00"
    buf += bytes([len(MTT_LAYER_TAG) + 1]) + MTT_LAYER_TAG + b"\x00"
    for name in part_names:
        utf16 = name.encode("utf-16-le") + b"\x00\x00"
        if len(utf16) > 255:
            raise AssertionError("test fixture only supports single-byte length")
        buf += b"\x01\x07\x20" + bytes([len(utf16)]) + utf16
    path.write_bytes(bytes(buf))
    return path


def test_parses_mtt_with_two_parts(tmp_path: Path) -> None:
    p = _write_fake_mtt(
        tmp_path / "sample.mtt",
        ["EC5L0020 - ENGINE CASE - FRONT - B150P", "EC5L0021 - ENGINE CASE - REAR - B150P"],
    )
    parsed = parse_build_file(p)
    assert parsed.format is BuildFileFormat.MTT
    assert parsed.part_count == 2
    assert [n.name for n in parsed.part_names] == [
        "EC5L0020 - ENGINE CASE - FRONT - B150P",
        "EC5L0021 - ENGINE CASE - REAR - B150P",
    ]
    assert len(parsed.file_sha256) == 64


def test_rejects_missing_envelope_magic(tmp_path: Path) -> None:
    p = tmp_path / "bad.mtt"
    p.write_bytes(b"\xff" * 128)
    with pytest.raises(UnrecognisedEnvelopeError, match="envelope magic"):
        parse_build_file(p)


def test_rejects_mtt_without_layer_tag(tmp_path: Path) -> None:
    p = tmp_path / "no-tag.mtt"
    p.write_bytes(ENVELOPE_MAGIC + b"\x00" * 128)
    with pytest.raises(UnrecognisedEnvelopeError, match="MTT-LayerFile"):
        parse_build_file(p)


def test_mtt_without_part_names_raises(tmp_path: Path) -> None:
    p = _write_fake_mtt(tmp_path / "names.mtt", [])
    with pytest.raises(NoPartNamesFoundError):
        parse_build_file(p)


def test_renam_with_no_names_is_allowed(tmp_path: Path) -> None:
    p = tmp_path / "scan.renam"
    p.write_bytes(ENVELOPE_MAGIC + b"\x00" * 256)
    parsed = parse_build_file(p)
    assert parsed.format is BuildFileFormat.RENAM
    assert parsed.part_count == 0


def test_missing_file_raises_filenotfound(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        parse_build_file(tmp_path / "ghost.mtt")


@pytest.mark.skipif(
    not Path(r"C:\Users\nateg\LPBF\EC5L0020 - ENGINE CASE - FRONT - B150.mtt").is_file(),
    reason="Real QuantAM 6.x sample not present on this host",
)
def test_real_quantam_sample_parses() -> None:
    p = Path(r"C:\Users\nateg\LPBF\EC5L0020 - ENGINE CASE - FRONT - B150.mtt")
    parsed = parse_build_file(p)
    assert parsed.format is BuildFileFormat.MTT
    assert parsed.part_count == 2
    names = [n.name for n in parsed.part_names]
    assert any("EC5L0020" in n for n in names)
    assert any("EC5L0021" in n for n in names)
