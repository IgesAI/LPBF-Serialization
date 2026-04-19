"""Tests for serial assignment (engine.serializer)."""

from __future__ import annotations

from pathlib import Path

import pytest

from lpbf_serializer.domain.ids import BuildCode
from lpbf_serializer.domain.models import PlatePosition
from lpbf_serializer.engine.serializer import PlacedPartInput, assign_serials


def _inp(x: float, y: float, name: str) -> PlacedPartInput:
    return PlacedPartInput(
        source_stl_path=Path(f"C:/parts/{name}.stl"),
        mesh_sha256="a" * 64,
        position=PlatePosition(x_mm=x, y_mm=y),
    )


def test_requires_at_least_one_part() -> None:
    bc = BuildCode(prefix="B#", number=1, digits=4)
    with pytest.raises(ValueError, match="At least one part"):
        assign_serials(bc, [])


def test_serials_are_row_major_numbered_from_one() -> None:
    bc = BuildCode(prefix="B#", number=5, digits=4)
    parts = assign_serials(
        bc,
        [
            _inp(10.0, 0.0, "c"),
            _inp(0.0, 0.0, "a"),
            _inp(0.0, 10.0, "d"),
            _inp(5.0, 0.0, "b"),
        ],
    )
    assert [str(p.serial) for p in parts] == [
        "B#0005-1",
        "B#0005-2",
        "B#0005-3",
        "B#0005-4",
    ]
    assert [p.part_number for p in parts] == [1, 2, 3, 4]
    assert [Path(p.source_stl_path).stem for p in parts] == ["a", "b", "c", "d"]


def test_output_is_pure_function_of_positions() -> None:
    bc = BuildCode(prefix="B#", number=1, digits=4)
    a = assign_serials(bc, [_inp(1.0, 1.0, "x"), _inp(2.0, 2.0, "y")])
    b = assign_serials(bc, [_inp(2.0, 2.0, "y"), _inp(1.0, 1.0, "x")])
    assert [str(p.serial) for p in a] == [str(p.serial) for p in b]
