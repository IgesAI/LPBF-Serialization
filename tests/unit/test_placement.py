"""Tests for deterministic part placement ordering."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from lpbf_serializer.domain.models import PlatePosition
from lpbf_serializer.engine.placement import (
    CoincidentPartsError,
    PositionedItem,
    order_parts,
)


def _item(tag: str, x: float, y: float) -> PositionedItem[str]:
    return PositionedItem(position=PlatePosition(x_mm=x, y_mm=y), item=tag)


def test_empty() -> None:
    assert order_parts(()) == ()


def test_row_major_ordering() -> None:
    items = (
        _item("c", 10.0, 0.0),
        _item("a", 0.0, 0.0),
        _item("d", 0.0, 10.0),
        _item("b", 5.0, 0.0),
    )
    ordered = order_parts(items, tolerance_mm=0.1)
    assert [p.item for p in ordered] == ["a", "b", "c", "d"]


def test_rejects_coincident() -> None:
    items = (_item("a", 1.0, 1.0), _item("b", 1.0005, 1.0005))
    with pytest.raises(CoincidentPartsError):
        order_parts(items, tolerance_mm=0.01)


def test_tolerance_must_be_positive() -> None:
    with pytest.raises(ValueError, match="tolerance_mm must be > 0"):
        order_parts((_item("a", 0.0, 0.0),), tolerance_mm=0.0)


@given(
    coords=st.lists(
        st.tuples(
            st.floats(min_value=0.0, max_value=200.0, allow_nan=False, allow_infinity=False),
            st.floats(min_value=0.0, max_value=200.0, allow_nan=False, allow_infinity=False),
        ),
        min_size=1,
        max_size=25,
        unique=True,
    )
)
@settings(max_examples=50, deadline=None)
def test_order_is_deterministic_under_permutation(
    coords: list[tuple[float, float]],
) -> None:
    items = tuple(_item(f"p{i}", x, y) for i, (x, y) in enumerate(coords))
    try:
        a = order_parts(items, tolerance_mm=0.5)
    except CoincidentPartsError:
        return
    b = order_parts(tuple(reversed(items)), tolerance_mm=0.5)
    assert [p.item for p in a] == [p.item for p in b]
