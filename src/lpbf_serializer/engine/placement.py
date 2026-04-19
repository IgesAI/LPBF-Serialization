"""Deterministic ordering of parts by XY position.

The goal is that two identical plates (same parts at same coordinates,
modulo floating-point rounding within ``tolerance_mm``) always produce the
same ordering and therefore the same part serials.

The ordering is **row-major**: points are bucketed into rows by
``y_mm // tolerance_mm``; within a row they are sorted by ``x_mm``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar

from lpbf_serializer.domain.models import PlatePosition


class CoincidentPartsError(ValueError):
    """Raised when two parts share the same XY position within tolerance."""


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class PositionedItem(Generic[T]):
    position: PlatePosition
    item: T


def order_parts(
    items: Sequence[PositionedItem[T]],
    *,
    tolerance_mm: float = 0.01,
) -> tuple[PositionedItem[T], ...]:
    """Return ``items`` ordered row-major with row grouping by ``tolerance_mm``.

    Raises ``CoincidentPartsError`` if two items share an XY position within
    ``tolerance_mm`` on both axes - the user must resolve the collision
    before a serial can be issued.
    """
    if tolerance_mm <= 0:
        raise ValueError(f"tolerance_mm must be > 0, got {tolerance_mm}")
    if len(items) == 0:
        return ()

    for i, a in enumerate(items):
        for b in items[i + 1 :]:
            if (
                abs(a.position.x_mm - b.position.x_mm) < tolerance_mm
                and abs(a.position.y_mm - b.position.y_mm) < tolerance_mm
            ):
                raise CoincidentPartsError(
                    f"Parts at ({a.position.x_mm}, {a.position.y_mm}) and "
                    f"({b.position.x_mm}, {b.position.y_mm}) are coincident "
                    f"within {tolerance_mm} mm"
                )

    def key(it: PositionedItem[T]) -> tuple[int, float, float]:
        row = int(it.position.y_mm // tolerance_mm)
        return (row, it.position.x_mm, it.position.y_mm)

    return tuple(sorted(items, key=key))
