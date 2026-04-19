"""Serial-text engraving via mesh boolean subtraction.

Given a watertight input mesh and a serial string, produce a new mesh with
the serial text recessed into the mesh's top face.

Failure modes are all explicit:

- The text mesh cannot be generated (empty / degenerate extrusion).
- Boolean subtraction fails or produces a non-watertight result.
- The engrave depth exceeds the available headroom on the top face.

In each case we raise :class:`EngravingFailedError`. The caller must not
fall back to an un-engraved mesh on failure.
"""

from __future__ import annotations

import numpy as np
import trimesh

from lpbf_serializer.domain.models import EngravingSpec


class EngravingFailedError(Exception):
    """Raised when an engraving cannot be performed safely."""


def _build_text_mesh(text: str, spec: EngravingSpec) -> trimesh.Trimesh:
    try:
        path_creation = trimesh.path.creation
        text_path = path_creation.text(  # type: ignore[attr-defined]
            text=text,
            font=spec.font_name,
            height=spec.text_height_mm,
        )
    except Exception as e:
        raise EngravingFailedError(
            f"Could not render text {text!r} with font {spec.font_name!r}: {e}"
        ) from e

    try:
        text_mesh_any = text_path.extrude(height=spec.depth_mm)
    except Exception as e:
        raise EngravingFailedError(f"Could not extrude text path: {e}") from e

    if isinstance(text_mesh_any, list):
        parts = [m for m in text_mesh_any if isinstance(m, trimesh.Trimesh)]
        if len(parts) == 0:
            raise EngravingFailedError("Text extrusion produced no solid meshes")
        combined = trimesh.util.concatenate(parts)
        if not isinstance(combined, trimesh.Trimesh):
            raise EngravingFailedError("Text extrusion did not yield a Trimesh")
        return combined
    if not isinstance(text_mesh_any, trimesh.Trimesh):
        raise EngravingFailedError(
            f"Text extrusion returned {type(text_mesh_any).__name__}, expected Trimesh"
        )
    return text_mesh_any


def engrave_serial(
    mesh: trimesh.Trimesh,
    serial: str,
    *,
    spec: EngravingSpec,
) -> trimesh.Trimesh:
    if not spec.enabled:
        raise EngravingFailedError(
            "engrave_serial was called with spec.enabled=False"
        )
    if len(serial.strip()) == 0:
        raise EngravingFailedError("Refusing to engrave an empty serial")
    if not mesh.is_watertight:
        raise EngravingFailedError("Refusing to engrave a non-watertight mesh")

    lo, hi = mesh.bounds
    headroom = float(hi[2] - lo[2])
    if spec.depth_mm >= headroom:
        raise EngravingFailedError(
            f"Engrave depth {spec.depth_mm} mm exceeds part height {headroom:.3f} mm"
        )

    text_mesh = _build_text_mesh(serial, spec=spec)

    text_w = float(text_mesh.bounds[1][0] - text_mesh.bounds[0][0])
    text_d = float(text_mesh.bounds[1][1] - text_mesh.bounds[0][1])
    part_w = float(hi[0] - lo[0])
    part_d = float(hi[1] - lo[1])
    margin = max(spec.text_height_mm * 0.5, 0.5)
    if text_w + 2 * margin > part_w or text_d + 2 * margin > part_d:
        raise EngravingFailedError(
            f"Serial '{serial}' ({text_w:.2f} x {text_d:.2f} mm) does not fit "
            f"on top face ({part_w:.2f} x {part_d:.2f} mm) with margin {margin:.2f}"
        )

    center_xy = np.array(
        [
            (lo[0] + hi[0]) * 0.5 - (text_mesh.bounds[0][0] + text_mesh.bounds[1][0]) * 0.5,
            (lo[1] + hi[1]) * 0.5 - (text_mesh.bounds[0][1] + text_mesh.bounds[1][1]) * 0.5,
            hi[2] - spec.depth_mm - text_mesh.bounds[0][2],
        ],
        dtype=float,
    )
    text_mesh.apply_translation(center_xy)

    try:
        cut = trimesh.boolean.difference([mesh, text_mesh])
    except Exception as e:
        raise EngravingFailedError(f"Boolean subtraction failed: {e}") from e

    if not isinstance(cut, trimesh.Trimesh) or cut.faces.shape[0] == 0:
        raise EngravingFailedError(
            "Boolean subtraction produced an empty or invalid mesh"
        )
    if not cut.is_watertight:
        raise EngravingFailedError(
            "Engraved mesh is not watertight; refusing to return it"
        )
    return cut
