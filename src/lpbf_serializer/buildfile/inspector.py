"""Read-only inspection of Renishaw build files.

The inspector does three things and nothing else:

1. Opens the file at ``path`` and records its size, SHA-256, and extension.
2. Tries to read it as a ZIP archive (the known ``.mtt`` / ``.renam``
   envelope). If ZIP, enumerates every member with its name, size,
   compressed size, CRC, and a conservative classification
   (STL / mesh / text / binary / directory). Text members are loaded
   fully for review; binary members are summarised only.
3. If not a ZIP, records the first ``magic_sample_bytes`` of the file for
   format identification and lists no members.

No part of this module mutates the file, extracts full STL payloads, or
attempts to "interpret" a binary machine file. That is Phase 9 work that
will be written *after* we have a concrete decision on parser strategy.
"""

from __future__ import annotations

import hashlib
import zipfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class BuildFileInspectionError(Exception):
    """Raised when the file cannot be opened or read at all."""


class EntryKind(str, Enum):
    STL_ASCII = "stl-ascii"
    STL_BINARY = "stl-binary"
    TEXT = "text"
    XML = "xml"
    JSON = "json"
    INI = "ini"
    BINARY = "binary"
    DIRECTORY = "directory"
    EMPTY = "empty"


_TEXT_EXTS = {
    ".txt",
    ".ini",
    ".cfg",
    ".xml",
    ".json",
    ".csv",
    ".log",
    ".md",
    ".yml",
    ".yaml",
    ".toml",
}

_MAX_TEXT_CAPTURE_BYTES = 2 * 1024 * 1024
_MAX_BINARY_HEAD_BYTES = 256


@dataclass(frozen=True, slots=True)
class InspectedEntry:
    """One member inside the build-file envelope."""

    name: str
    kind: EntryKind
    uncompressed_size: int
    compressed_size: int
    crc32: int
    head_hex: str
    text_content: str | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ExtractedString:
    """One ASCII or UTF-16LE string located in a non-ZIP blob."""

    offset: int
    encoding: str
    value: str


@dataclass(frozen=True, slots=True)
class InspectionReport:
    path: Path
    file_size_bytes: int
    file_sha256: str
    is_zip: bool
    zip_comment: str | None
    magic_hex: str
    entries: tuple[InspectedEntry, ...]
    strings: tuple[ExtractedString, ...] = field(default_factory=tuple)
    scanned_bytes: int = 0
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def extension(self) -> str:
        return self.path.suffix.lower()


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_head(path: Path, n: int) -> bytes:
    with path.open("rb") as f:
        return f.read(n)


def _classify(name: str, head: bytes, size: int) -> tuple[EntryKind, tuple[str, ...]]:
    if size == 0:
        return EntryKind.EMPTY, ()

    lower = name.lower()
    if lower.endswith("/"):
        return EntryKind.DIRECTORY, ()

    suffix = "." + lower.rsplit(".", 1)[-1] if "." in lower else ""

    if suffix == ".stl":
        if head[:6].lstrip().lower().startswith(b"solid"):
            return EntryKind.STL_ASCII, ()
        return EntryKind.STL_BINARY, ()

    if suffix == ".xml":
        return EntryKind.XML, ()
    if suffix == ".json":
        return EntryKind.JSON, ()
    if suffix == ".ini":
        return EntryKind.INI, ()
    if suffix in _TEXT_EXTS:
        return EntryKind.TEXT, ()

    if head.lstrip().startswith(b"<?xml"):
        return EntryKind.XML, ("detected-as-xml-by-content",)
    stripped = head.lstrip()
    if stripped.startswith((b"{", b"[")):
        return EntryKind.JSON, ("detected-as-json-by-content",)

    try:
        head.decode("utf-8")
    except UnicodeDecodeError:
        pass
    else:
        if not any(b in head for b in (0, 1, 2, 3, 4, 5, 6, 7, 11, 14, 15)):
            return EntryKind.TEXT, ("detected-as-text-by-content",)

    return EntryKind.BINARY, ()


def _inspect_zip(path: Path) -> tuple[tuple[InspectedEntry, ...], str | None]:
    entries: list[InspectedEntry] = []
    with zipfile.ZipFile(path, "r") as zf:
        comment = zf.comment.decode("utf-8", errors="replace") if zf.comment else None
        for info in zf.infolist():
            name = info.filename
            head_bytes = b""
            if not info.is_dir() and info.file_size > 0:
                with zf.open(info, "r") as member:
                    head_bytes = member.read(_MAX_BINARY_HEAD_BYTES)

            kind, cls_notes = _classify(
                name=name, head=head_bytes, size=info.file_size
            )

            text_content: str | None = None
            notes = list(cls_notes)

            is_text_kind = kind in {
                EntryKind.TEXT,
                EntryKind.XML,
                EntryKind.JSON,
                EntryKind.INI,
            }
            if is_text_kind and 0 < info.file_size <= _MAX_TEXT_CAPTURE_BYTES:
                with zf.open(info, "r") as member:
                    raw = member.read()
                try:
                    text_content = raw.decode("utf-8")
                except UnicodeDecodeError:
                    try:
                        text_content = raw.decode("utf-16")
                        notes.append("decoded-as-utf16")
                    except UnicodeDecodeError:
                        text_content = raw.decode("latin-1")
                        notes.append("decoded-as-latin1")
            elif is_text_kind and info.file_size > _MAX_TEXT_CAPTURE_BYTES:
                notes.append(
                    f"text-truncated-over-{_MAX_TEXT_CAPTURE_BYTES}-bytes"
                )

            entries.append(
                InspectedEntry(
                    name=name,
                    kind=kind,
                    uncompressed_size=info.file_size,
                    compressed_size=info.compress_size,
                    crc32=info.CRC,
                    head_hex=head_bytes[:64].hex(),
                    text_content=text_content,
                    notes=tuple(notes),
                )
            )
    return tuple(entries), comment


def _is_printable_ascii(b: int) -> bool:
    return 0x20 <= b <= 0x7E


def _scan_strings(
    data: bytes,
    *,
    min_len: int = 6,
    base_offset: int = 0,
    max_results: int = 2048,
) -> tuple[ExtractedString, ...]:
    """Extract printable ASCII and UTF-16LE strings from a raw blob.

    Purely pattern-based: runs of printable bytes of length >= ``min_len``.
    No structural interpretation is performed.
    """
    out: list[ExtractedString] = []

    i = 0
    n = len(data)
    while i < n:
        if _is_printable_ascii(data[i]):
            start = i
            while i < n and _is_printable_ascii(data[i]):
                i += 1
            if i - start >= min_len:
                out.append(
                    ExtractedString(
                        offset=base_offset + start,
                        encoding="ascii",
                        value=data[start:i].decode("ascii", errors="replace"),
                    )
                )
        else:
            i += 1
        if len(out) >= max_results:
            break

    i = 0
    while i + 1 < n and len(out) < max_results:
        if data[i + 1] == 0 and _is_printable_ascii(data[i]):
            start = i
            chars: list[int] = []
            while (
                i + 1 < n
                and data[i + 1] == 0
                and _is_printable_ascii(data[i])
            ):
                chars.append(data[i])
                i += 2
            if len(chars) >= min_len:
                out.append(
                    ExtractedString(
                        offset=base_offset + start,
                        encoding="utf-16le",
                        value=bytes(chars).decode("ascii", errors="replace"),
                    )
                )
        else:
            i += 1

    return tuple(out)


def inspect_build_file(
    path: Path,
    *,
    magic_sample_bytes: int = 256,
    scan_strings_bytes: int = 4 * 1024 * 1024,
    min_string_length: int = 6,
) -> InspectionReport:
    """Return a structured, read-only report on ``path``.

    For non-ZIP files we additionally run a printable-string scan over the
    first ``scan_strings_bytes`` bytes. This is purely diagnostic and never
    asserts structure - it just surfaces any human-readable text the file
    carries (part names, machine IDs, encoded filenames).

    Raises ``BuildFileInspectionError`` only on filesystem-level failures
    (missing file, unreadable). Format-level oddities are reported in the
    :class:`InspectionReport` ``notes`` instead of raising.
    """
    if not path.is_file():
        raise BuildFileInspectionError(f"File not found: {path}")

    size = path.stat().st_size
    sha = _sha256_of(path)
    magic = _read_head(path, magic_sample_bytes)
    magic_hex = magic.hex()

    notes: list[str] = []
    is_zip = zipfile.is_zipfile(path)
    entries: tuple[InspectedEntry, ...] = ()
    zip_comment: str | None = None
    strings: tuple[ExtractedString, ...] = ()
    scanned = 0

    if is_zip:
        try:
            entries, zip_comment = _inspect_zip(path)
        except zipfile.BadZipFile as e:
            notes.append(f"zipfile-read-failed: {e}")
            is_zip = False

    if not is_zip:
        notes.append("not-a-zip-archive")
        to_read = min(scan_strings_bytes, size)
        with path.open("rb") as f:
            blob = f.read(to_read)
        scanned = len(blob)
        strings = _scan_strings(
            blob, min_len=min_string_length, base_offset=0
        )
        if scanned < size:
            notes.append(f"string-scan-truncated-at-{scanned}-bytes")

    return InspectionReport(
        path=path,
        file_size_bytes=size,
        file_sha256=sha,
        is_zip=is_zip,
        zip_comment=zip_comment,
        magic_hex=magic_hex,
        entries=entries,
        strings=strings,
        scanned_bytes=scanned,
        notes=tuple(notes),
    )
