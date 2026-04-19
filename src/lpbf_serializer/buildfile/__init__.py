"""Read / inspect / (eventually) rewrite Renishaw build files.

Supported file extensions (as ``Path.suffix``, case-insensitive):

- ``.mtt``   - current Renishaw machine toolpath file (ZIP envelope).
- ``.renam`` - Renishaw TEMPUS scanning data (ZIP envelope, richer inner file).
- ``.amx``   - legacy Renishaw format (envelope not yet characterised).

This package starts read-only: the :mod:`inspector` module dumps the raw
structure of a file so we can decide, with real data in hand, which parser
to commit to. Nothing in this package fabricates, modifies, or guesses the
structure of a build file.
"""

from __future__ import annotations

from lpbf_serializer.buildfile.inspector import (
    BuildFileInspectionError,
    EntryKind,
    ExtractedString,
    InspectedEntry,
    InspectionReport,
    inspect_build_file,
)
from lpbf_serializer.buildfile.mtt_reader import (
    HeaderPartName,
    MttReaderError,
    NoPartNamesFoundError,
    ParsedBuildFile,
    UnrecognisedEnvelopeError,
    parse_build_file,
)

__all__ = [
    "BuildFileInspectionError",
    "EntryKind",
    "ExtractedString",
    "HeaderPartName",
    "InspectedEntry",
    "InspectionReport",
    "MttReaderError",
    "NoPartNamesFoundError",
    "ParsedBuildFile",
    "UnrecognisedEnvelopeError",
    "inspect_build_file",
    "parse_build_file",
]
