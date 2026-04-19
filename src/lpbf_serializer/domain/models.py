"""Domain entities used across layers.

These are plain frozen pydantic models with strict validation. They do not
inherit from ORM classes and do not accept partial construction.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from lpbf_serializer.domain.ids import BuildCode, PartSerial


class QAStatus(str, Enum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    QUARANTINED = "quarantined"


class PlatePosition(BaseModel):
    """XY origin of a part on the build plate, in millimetres."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    x_mm: float = Field(ge=0.0)
    y_mm: float = Field(ge=0.0)

    @field_validator("x_mm", "y_mm")
    @classmethod
    def _finite(cls, v: float) -> float:
        if v != v or v in (float("inf"), float("-inf")):
            raise ValueError("position coordinate must be finite")
        return v


class EngravingSpec(BaseModel):
    """Parameters for serial engraving on a part."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text_height_mm: float = Field(gt=0.0, le=10.0, default=1.0)
    depth_mm: float = Field(gt=0.0, le=2.0, default=0.3)
    font_name: str = Field(min_length=1, default="DejaVuSans")

    enabled: bool = True


class BuildFileFormat(str, Enum):
    """Format of a Renishaw build file we were handed."""

    MTT = "mtt"
    RENAM = "renam"
    AMX = "amx"
    UNKNOWN = "unknown"


class PartRecord(BaseModel):
    """A part as known to the build engine before/after DB persistence.

    In **drag-place mode** (STL imported by hand) ``position``,
    ``source_stl_path`` and ``mesh_sha256`` are all populated. In
    **sidecar mode** (registered from an existing .mtt / .renam without
    cracking it open) they are all ``None`` and ``part_name`` is the
    string extracted from the build-file header.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    serial: PartSerial
    part_number: int = Field(ge=1)
    part_name: str | None = None
    position: PlatePosition | None = None
    source_stl_path: Path | None = None
    mesh_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    qa_status: QAStatus = QAStatus.PENDING


class BuildRecord(BaseModel):
    """A build plate as known to the build engine before/after DB persistence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    build_code: BuildCode
    created_at: datetime
    parts: tuple[PartRecord, ...]
    mtt_path: Path | None = None
    mtt_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    source_build_file_path: Path | None = None
    source_build_file_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    source_build_file_format: BuildFileFormat | None = None
    notes: str = ""

    @field_validator("parts")
    @classmethod
    def _parts_match_build(cls, v: tuple[PartRecord, ...]) -> tuple[PartRecord, ...]:
        if len(v) == 0:
            raise ValueError("A build must contain at least one part")
        numbers = [p.part_number for p in v]
        if numbers != sorted(numbers):
            raise ValueError("Part numbers must be in ascending order")
        if len(set(numbers)) != len(numbers):
            raise ValueError("Part numbers must be unique")
        expected = list(range(1, len(v) + 1))
        if numbers != expected:
            raise ValueError(
                f"Part numbers must be contiguous starting at 1; got {numbers}"
            )
        return v
