"""Tests for QuantAM discovery against the real installed binaries."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from lpbf_serializer.quantam.discovery import discover_quantam
from lpbf_serializer.quantam.errors import (
    QuantAMNotFoundError,
    QuantAMVersionMismatchError,
)


def test_missing_exe(tmp_path: Path) -> None:
    with pytest.raises(QuantAMNotFoundError):
        discover_quantam(
            exe_path=tmp_path / "ghost.exe", expected_version="6.1.0.1"
        )


@pytest.mark.skipif(sys.platform != "win32", reason="QuantAM is Windows-only")
def test_real_quantam_install_if_present() -> None:
    candidate = Path(
        r"C:\Program Files\Renishaw\Renishaw QuantAM 6.1.0.1\Renishaw QuantAM.exe"
    )
    if not candidate.is_file():
        pytest.skip("QuantAM 6.1.0.1 not installed on this host")

    version = discover_quantam(exe_path=candidate, expected_version="6.1.0.1")
    assert version == "6.1.0.1"


@pytest.mark.skipif(sys.platform != "win32", reason="QuantAM is Windows-only")
def test_version_mismatch_raises() -> None:
    candidate = Path(
        r"C:\Program Files\Renishaw\Renishaw QuantAM 6.1.0.1\Renishaw QuantAM.exe"
    )
    if not candidate.is_file():
        pytest.skip("QuantAM 6.1.0.1 not installed on this host")

    with pytest.raises(QuantAMVersionMismatchError):
        discover_quantam(exe_path=candidate, expected_version="999.0.0.0")
