"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest
import trimesh


@pytest.fixture
def cube_stl(tmp_path: Path) -> Path:
    """A watertight 10x10x10 mm cube, written to a temp STL file."""
    mesh = trimesh.creation.box(extents=(10.0, 10.0, 10.0))
    path = tmp_path / "cube.stl"
    mesh.export(path)
    return path


@pytest.fixture
def tall_cube_stl(tmp_path: Path) -> Path:
    """A taller 20x20x10 cube with enough headroom for engraving."""
    mesh = trimesh.creation.box(extents=(20.0, 20.0, 10.0))
    path = tmp_path / "tall_cube.stl"
    mesh.export(path)
    return path


@pytest.fixture
def non_watertight_stl(tmp_path: Path) -> Path:
    """An STL with a deliberately removed face (open mesh)."""
    mesh = trimesh.creation.box(extents=(5.0, 5.0, 5.0))
    mesh.update_faces(list(range(1, len(mesh.faces))))
    path = tmp_path / "open.stl"
    mesh.export(path)
    return path
