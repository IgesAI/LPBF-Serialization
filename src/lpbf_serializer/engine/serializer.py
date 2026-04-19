"""Assign part serials to placed parts.

This is a pure function. It takes:

- a build code issued by the sequencer,
- a sequence of placed parts (STL path + mesh hash + XY position),

and returns a tuple of :class:`PartRecord` with a monotonically increasing
``part_number`` and corresponding :class:`PartSerial`. The ordering comes
from :func:`order_parts`; there is no randomness and no reliance on
dict ordering or input order.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from lpbf_serializer.domain.ids import BuildCode, PartSerial
from lpbf_serializer.domain.models import PartRecord, PlatePosition, QAStatus
from lpbf_serializer.engine.placement import PositionedItem, order_parts


@dataclass(frozen=True, slots=True)
class PlacedPartInput:
    source_stl_path: Path
    mesh_sha256: str
    position: PlatePosition


@dataclass(frozen=True, slots=True)
class PreparedPart:
    record: PartRecord


def assign_serials(
    build_code: BuildCode,
    inputs: Sequence[PlacedPartInput],
    *,
    tolerance_mm: float = 0.01,
) -> tuple[PartRecord, ...]:
    if len(inputs) == 0:
        raise ValueError("At least one part is required to assign serials")

    wrapped = tuple(
        PositionedItem(position=p.position, item=p) for p in inputs
    )
    ordered = order_parts(wrapped, tolerance_mm=tolerance_mm)

    records: list[PartRecord] = []
    for idx, pos_item in enumerate(ordered, start=1):
        src = pos_item.item
        records.append(
            PartRecord(
                serial=PartSerial(build_code=build_code, index=idx),
                part_number=idx,
                position=src.position,
                source_stl_path=src.source_stl_path,
                mesh_sha256=src.mesh_sha256,
                qa_status=QAStatus.PENDING,
            )
        )
    return tuple(records)
