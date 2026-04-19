"""Smoke tests for the plate scene and PartItem behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtWidgets")

from lpbf_serializer.ui.plate_scene import PlacedPart, PlateScene  # noqa: E402

pytestmark = pytest.mark.gui


def _placed(size: float = 10.0) -> PlacedPart:
    return PlacedPart(
        stl_path=Path("fake.stl"),
        mesh_sha256="a" * 64,
        size_x_mm=size,
        size_y_mm=size,
    )


def test_add_parts_reports_positions(qtbot):  # type: ignore[no-untyped-def]
    scene = PlateScene(plate_width_mm=100.0, plate_depth_mm=100.0)
    a = scene.add_part(_placed(), 5.0, 5.0)
    b = scene.add_part(_placed(), 40.0, 40.0)
    del qtbot
    positions = {str(it.position_mm()) for it in scene.part_items()}
    assert len(positions) == 2
    assert a is not b


def test_coincidence_detection_flags_parts(qtbot):  # type: ignore[no-untyped-def]
    scene = PlateScene(plate_width_mm=100.0, plate_depth_mm=100.0)
    scene.add_part(_placed(), 10.0, 10.0)
    scene.add_part(_placed(), 10.0, 10.0)
    del qtbot
    assert scene.refresh_coincidence() is True


def test_no_coincidence_when_separated(qtbot):  # type: ignore[no-untyped-def]
    scene = PlateScene(plate_width_mm=100.0, plate_depth_mm=100.0)
    scene.add_part(_placed(), 10.0, 10.0)
    scene.add_part(_placed(), 50.0, 50.0)
    del qtbot
    assert scene.refresh_coincidence() is False


def test_movement_clamps_inside_plate(qtbot):  # type: ignore[no-untyped-def]
    scene = PlateScene(plate_width_mm=100.0, plate_depth_mm=100.0)
    item = scene.add_part(_placed(size=20.0), 0.0, 0.0)
    del qtbot
    item.setPos(-50.0, -50.0)
    assert item.position_mm().x_mm == 0.0
    assert item.position_mm().y_mm == 0.0

    item.setPos(1000.0, 1000.0)
    assert item.position_mm().x_mm == 80.0
    assert item.position_mm().y_mm == 80.0
