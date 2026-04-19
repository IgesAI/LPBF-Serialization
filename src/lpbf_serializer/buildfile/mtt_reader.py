"""Narrow, evidence-based reader for QuantAM 6.x build files.

What this reader asserts:

- The file starts with the known Renishaw envelope magic
  (``01 E0 00 00 00 00 00``) and, for ``.mtt`` specifically, also carries
  the length-prefixed ASCII marker ``MTT-LayerFile``.
- Part names are encoded as UTF-16LE sequences of printable ASCII inside
  the file's header region.

What this reader does NOT do:

- Parse the TLV payload.
- Extract STL geometry.
- Read or write part positions.
- Produce any value that was not directly observed in the file bytes.

If the envelope magic is missing, the reader raises. It never "best
effort" guesses at format.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from lpbf_serializer.domain.models import BuildFileFormat

ENVELOPE_MAGIC: bytes = bytes.fromhex("01e0000000000001")
MTT_LAYER_TAG: bytes = b"MTT-LayerFile"

_DEFAULT_HEADER_BYTES = 64 * 1024
_MIN_PART_NAME_LEN = 6


class MttReaderError(Exception):
    """Base class for mtt_reader failures."""


class UnrecognisedEnvelopeError(MttReaderError):
    """File does not begin with the known Renishaw envelope magic."""


class NoPartNamesFoundError(MttReaderError):
    """No UTF-16LE part-name strings were found in the header region."""


@dataclass(frozen=True, slots=True)
class HeaderPartName:
    offset: int
    name: str


@dataclass(frozen=True, slots=True)
class ParsedBuildFile:
    path: Path
    file_sha256: str
    file_size_bytes: int
    format: BuildFileFormat
    envelope_magic_hex: str
    header_scanned_bytes: int
    part_names: tuple[HeaderPartName, ...]

    @property
    def part_count(self) -> int:
        return len(self.part_names)


def _format_from_extension(path: Path) -> BuildFileFormat:
    suffix = path.suffix.lower()
    if suffix == ".mtt":
        return BuildFileFormat.MTT
    if suffix == ".renam":
        return BuildFileFormat.RENAM
    if suffix == ".amx":
        return BuildFileFormat.AMX
    return BuildFileFormat.UNKNOWN


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_header(path: Path, n: int) -> bytes:
    with path.open("rb") as f:
        return f.read(n)


def _is_printable_ascii(b: int) -> bool:
    return 0x20 <= b <= 0x7E


def _extract_utf16le_names(
    header: bytes, *, min_len: int = _MIN_PART_NAME_LEN
) -> tuple[HeaderPartName, ...]:
    out: list[HeaderPartName] = []
    n = len(header)
    i = 0
    while i + 1 < n:
        if header[i + 1] == 0 and _is_printable_ascii(header[i]):
            start = i
            chars: list[int] = []
            while (
                i + 1 < n
                and header[i + 1] == 0
                and _is_printable_ascii(header[i])
            ):
                chars.append(header[i])
                i += 2
            if len(chars) >= min_len:
                out.append(
                    HeaderPartName(
                        offset=start,
                        name=bytes(chars).decode("ascii"),
                    )
                )
        else:
            i += 1
    return tuple(out)


def parse_build_file(
    path: Path,
    *,
    header_bytes: int = _DEFAULT_HEADER_BYTES,
) -> ParsedBuildFile:
    """Parse the header of a Renishaw build file and return what we can verify.

    Raises:
        FileNotFoundError: if ``path`` does not exist.
        UnrecognisedEnvelopeError: if the file does not start with the
            known Renishaw envelope magic.
        NoPartNamesFoundError: if the format is ``MTT`` but no UTF-16LE
            part-name string of the expected kind is found in the
            inspected header window. For ``RENAM``, the absence of names
            is *expected* and not an error.
    """
    if not path.is_file():
        raise FileNotFoundError(str(path))

    size = path.stat().st_size
    sha = _file_sha256(path)
    fmt = _format_from_extension(path)

    header = _read_header(path, min(header_bytes, size))
    if not header.startswith(ENVELOPE_MAGIC):
        raise UnrecognisedEnvelopeError(
            f"{path.name}: header does not start with Renishaw envelope magic "
            f"({ENVELOPE_MAGIC.hex()}); got {header[:8].hex()}"
        )

    if fmt is BuildFileFormat.MTT and MTT_LAYER_TAG not in header[:64]:
        raise UnrecognisedEnvelopeError(
            f"{path.name}: MTT-LayerFile marker not found in first 64 bytes"
        )

    names = _extract_utf16le_names(header)

    if fmt is BuildFileFormat.MTT and len(names) == 0:
        raise NoPartNamesFoundError(
            f"{path.name}: no UTF-16LE part names found in first {len(header)} bytes"
        )

    return ParsedBuildFile(
        path=path,
        file_sha256=sha,
        file_size_bytes=size,
        format=fmt,
        envelope_magic_hex=header[:16].hex(),
        header_scanned_bytes=len(header),
        part_names=names,
    )
