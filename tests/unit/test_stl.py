"""Tests for the STL loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from lpbf_serializer.geometry.stl import (
    MeshNotWatertightError,
    StlLoadError,
    load_stl,
)


def test_loads_watertight_cube(cube_stl: Path) -> None:
    loaded = load_stl(cube_stl)
    assert loaded.mesh.is_watertight
    assert len(loaded.sha256) == 64
    lo, hi = loaded.bounds_mm
    assert pytest.approx(hi[0] - lo[0], abs=1e-6) == 10.0


def test_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(StlLoadError, match="does not exist"):
        load_stl(tmp_path / "nope.stl")


def test_rejects_wrong_extension(tmp_path: Path) -> None:
    p = tmp_path / "file.obj"
    p.write_text("")
    with pytest.raises(StlLoadError, match="Not an .stl file"):
        load_stl(p)


def test_rejects_non_watertight(non_watertight_stl: Path) -> None:
    with pytest.raises(MeshNotWatertightError):
        load_stl(non_watertight_stl)


def test_sha256_is_deterministic(cube_stl: Path) -> None:
    a = load_stl(cube_stl).sha256
    b = load_stl(cube_stl).sha256
    assert a == b
