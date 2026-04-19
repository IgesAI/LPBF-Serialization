"""Tests for the engraving module."""

from __future__ import annotations

from pathlib import Path

import pytest
import trimesh

from lpbf_serializer.domain.models import EngravingSpec
from lpbf_serializer.geometry.engraving import EngravingFailedError, engrave_serial
from lpbf_serializer.geometry.stl import load_stl


def test_refuses_empty_serial(cube_stl: Path) -> None:
    mesh = load_stl(cube_stl).mesh
    with pytest.raises(EngravingFailedError, match="empty serial"):
        engrave_serial(mesh, "", spec=EngravingSpec())


def test_refuses_when_disabled(cube_stl: Path) -> None:
    mesh = load_stl(cube_stl).mesh
    spec = EngravingSpec(enabled=False)
    with pytest.raises(EngravingFailedError, match="enabled=False"):
        engrave_serial(mesh, "B#0001-1", spec=spec)


def test_refuses_non_watertight() -> None:
    mesh = trimesh.creation.box(extents=(5.0, 5.0, 5.0))
    mesh.update_faces(list(range(1, len(mesh.faces))))
    with pytest.raises(EngravingFailedError, match="non-watertight"):
        engrave_serial(mesh, "X", spec=EngravingSpec())


def test_refuses_depth_exceeds_part_height() -> None:
    mesh = trimesh.creation.box(extents=(20.0, 20.0, 1.0))
    spec = EngravingSpec(text_height_mm=1.0, depth_mm=1.5)
    with pytest.raises(EngravingFailedError, match="exceeds part height"):
        engrave_serial(mesh, "B#0001-1", spec=spec)
