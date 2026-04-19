"""STL loading with strict validation.

The loader refuses to silently "repair" malformed meshes. If the file is
not a readable STL, or the resulting mesh is not watertight (genus-0 is
not required, but the boundary must be closed), the loader raises.

Every successful load also computes the SHA-256 of the *on-disk file*
bytes, which the audit layer later stores alongside the part record to
prove the provenance of the geometry.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import numpy as np
import trimesh


class StlLoadError(Exception):
    """Raised when an STL cannot be read or is not a mesh."""


class MeshNotWatertightError(StlLoadError):
    """Raised when an STL loads but the mesh has open boundaries."""


@dataclass(frozen=True, slots=True)
class LoadedMesh:
    path: Path
    mesh: trimesh.Trimesh
    sha256: str

    @property
    def bounds_mm(self) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        lo, hi = cast("np.ndarray", self.mesh.bounds)
        return (
            (float(lo[0]), float(lo[1]), float(lo[2])),
            (float(hi[0]), float(hi[1]), float(hi[2])),
        )


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_stl(path: Path, *, require_watertight: bool = True) -> LoadedMesh:
    if not path.is_file():
        raise StlLoadError(f"STL file does not exist: {path}")
    if path.suffix.lower() != ".stl":
        raise StlLoadError(f"Not an .stl file: {path}")

    try:
        mesh = trimesh.load(path, force="mesh", process=True, merge_norm=True)
    except Exception as e:
        raise StlLoadError(f"Failed to read {path}: {e}") from e

    if not isinstance(mesh, trimesh.Trimesh):
        raise StlLoadError(
            f"Expected a single triangle mesh in {path}, got {type(mesh).__name__}"
        )
    if mesh.faces.shape[0] == 0:
        raise StlLoadError(f"Mesh in {path} has zero faces")

    mesh.merge_vertices()

    if require_watertight and not mesh.is_watertight:
        raise MeshNotWatertightError(
            f"Mesh in {path} is not watertight (open edges detected)"
        )

    return LoadedMesh(path=path, mesh=mesh, sha256=_file_sha256(path))
