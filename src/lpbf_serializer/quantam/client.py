"""Abstract QuantAM client contract.

Everything outside the ``quantam`` package depends only on this module.
The concrete UIA implementation lives in ``uia_client`` and is selected at
application startup.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from lpbf_serializer.domain.ids import BuildCode


@dataclass(frozen=True, slots=True)
class QuantAMInfo:
    exe_path: Path
    version: str


@dataclass(frozen=True, slots=True)
class ExportRequestPart:
    stl_path: Path
    pos_x_mm: float
    pos_y_mm: float
    serial: str


@dataclass(frozen=True, slots=True)
class ExportRequest:
    build_code: BuildCode
    output_mtt_path: Path
    parts: tuple[ExportRequestPart, ...]

    def __post_init__(self) -> None:
        if len(self.parts) == 0:
            raise ValueError("ExportRequest must contain at least one part")
        if self.output_mtt_path.suffix.lower() != ".mtt":
            raise ValueError(
                f"output_mtt_path must end with .mtt, got {self.output_mtt_path}"
            )


@dataclass(frozen=True, slots=True)
class MttManifest:
    """Details extracted from an on-disk ``.mtt`` (ZIP) archive."""

    mtt_path: Path
    sha256: str
    entry_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExportResult:
    mtt_path: Path
    manifest: MttManifest


class QuantAMClient(Protocol):
    """Contract for any QuantAM automation backend."""

    def health_check(self) -> QuantAMInfo:
        """Return install/version info. Raise on any problem."""

    def export_build(self, request: ExportRequest) -> ExportResult:
        """Drive QuantAM to produce the ``.mtt`` at ``request.output_mtt_path``.

        On success returns an :class:`ExportResult` whose ``manifest.sha256``
        is the hash of the produced file. On any failure, raises a subclass
        of :class:`lpbf_serializer.quantam.errors.QuantAMError`. The caller
        must treat a raise as "no .mtt was produced and no state should be
        persisted".
        """

    def verify_mtt(self, path: Path) -> MttManifest:
        """Parse and hash an existing ``.mtt`` file."""
