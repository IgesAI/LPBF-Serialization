"""Read and hash a ``.mtt`` file produced by QuantAM.

An ``.mtt`` is a ZIP archive. We verify that it can be opened, that it
contains at least one STL and one machine parameter file, then hash the
entire archive with SHA-256.

No content is modified. The hash is over the raw bytes on disk so that
two readers will always agree on the value.
"""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

from lpbf_serializer.quantam.client import MttManifest
from lpbf_serializer.quantam.errors import QuantAMVerificationFailedError


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_mtt_manifest(path: Path) -> MttManifest:
    if not path.is_file():
        raise QuantAMVerificationFailedError(f".mtt file not found: {path}")
    if path.suffix.lower() != ".mtt":
        raise QuantAMVerificationFailedError(f"Not an .mtt file: {path}")

    try:
        with zipfile.ZipFile(path, "r") as zf:
            names = tuple(zf.namelist())
            bad = zf.testzip()
    except zipfile.BadZipFile as e:
        raise QuantAMVerificationFailedError(
            f".mtt at {path} is not a valid ZIP archive: {e}"
        ) from e

    if bad is not None:
        raise QuantAMVerificationFailedError(
            f".mtt at {path} has a corrupt entry: {bad}"
        )
    if len(names) == 0:
        raise QuantAMVerificationFailedError(f".mtt at {path} is empty")

    lower = [n.lower() for n in names]
    if not any(n.endswith(".stl") for n in lower):
        raise QuantAMVerificationFailedError(
            f".mtt at {path} contains no STL entries: {names}"
        )

    return MttManifest(
        mtt_path=path,
        sha256=_sha256_of(path),
        entry_names=names,
    )
