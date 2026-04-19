"""CLI: ``uv run python -m lpbf_serializer.buildfile.inspect <path>``.

Writes a human-readable Markdown report to stdout (or ``--output``).
Optionally extracts every ZIP member to a directory for manual review.
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

from lpbf_serializer.buildfile.inspector import (
    BuildFileInspectionError,
    EntryKind,
    InspectedEntry,
    InspectionReport,
    inspect_build_file,
)


def _fmt_size(n: int) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    size = float(n)
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{int(size):,} {unit}"
            return f"{size:,.2f} {unit}"
        size /= 1024.0
    return f"{n} B"


def _render_markdown(report: InspectionReport) -> str:
    lines: list[str] = []
    lines.append(f"# Build file inspection: `{report.path.name}`")
    lines.append("")
    lines.append(f"- Full path: `{report.path}`")
    lines.append(f"- Extension: `{report.extension}`")
    lines.append(f"- Size: {_fmt_size(report.file_size_bytes)} ({report.file_size_bytes:,} bytes)")
    lines.append(f"- SHA-256: `{report.file_sha256}`")
    lines.append(f"- ZIP archive: **{report.is_zip}**")
    if report.zip_comment:
        lines.append(f"- ZIP comment: `{report.zip_comment}`")
    lines.append(f"- Magic (first 64 bytes): `{report.magic_hex[:128]}`")
    if report.notes:
        lines.append("- Notes:")
        for n in report.notes:
            lines.append(f"  - `{n}`")
    lines.append("")

    if not report.is_zip:
        lines.append("## No ZIP envelope detected")
        lines.append("")
        lines.append(
            f"The file is not a readable ZIP archive. A printable-string "
            f"scan was run over the first {_fmt_size(report.scanned_bytes)} "
            f"to surface any readable text (part names, machine IDs, "
            f"encoded filenames). No structure is inferred."
        )
        lines.append("")
        lines.append(f"### Extracted strings ({len(report.strings)} hits)")
        lines.append("")
        if not report.strings:
            lines.append("_No printable strings of length >= 6 were found._")
        else:
            lines.append("| Offset | Enc | Value |")
            lines.append("|-------:|-----|-------|")
            for s in report.strings:
                clean = s.value.replace("|", "\\|")
                lines.append(f"| `0x{s.offset:08x}` | `{s.encoding}` | `{clean}` |")
        return "\n".join(lines) + "\n"

    by_kind: dict[EntryKind, list[InspectedEntry]] = {}
    for e in report.entries:
        by_kind.setdefault(e.kind, []).append(e)

    lines.append(f"## Summary ({len(report.entries)} entries)")
    lines.append("")
    lines.append("| Kind | Count | Total uncompressed |")
    lines.append("|------|------:|-------------------:|")
    for kind in sorted(by_kind.keys(), key=lambda k: k.value):
        items = by_kind[kind]
        total = sum(e.uncompressed_size for e in items)
        lines.append(f"| `{kind.value}` | {len(items)} | {_fmt_size(total)} |")
    lines.append("")

    lines.append("## Entries")
    lines.append("")
    lines.append(
        "| # | Kind | Name | Uncompressed | Compressed | CRC32 | Head (hex, 64B) |"
    )
    lines.append("|---|------|------|-------------:|-----------:|------:|-----------------|")
    for i, e in enumerate(report.entries, 1):
        lines.append(
            f"| {i} | `{e.kind.value}` | `{e.name}` | "
            f"{_fmt_size(e.uncompressed_size)} | {_fmt_size(e.compressed_size)} | "
            f"`{e.crc32:08X}` | `{e.head_hex[:64]}` |"
        )
    lines.append("")

    lines.append("## Text / config members (full content)")
    lines.append("")
    any_text = False
    for e in report.entries:
        if e.text_content is None:
            continue
        any_text = True
        lines.append(f"### `{e.name}` ({e.kind.value})")
        if e.notes:
            lines.append(f"Notes: {', '.join(f'`{n}`' for n in e.notes)}")
        lines.append("")
        fence = "```xml" if e.kind is EntryKind.XML else "```"
        lines.append(fence)
        lines.append(e.text_content.rstrip())
        lines.append("```")
        lines.append("")
    if not any_text:
        lines.append("_No text / config members were captured._")
        lines.append("")

    return "\n".join(lines) + "\n"


def _extract_all(report: InspectionReport, out_dir: Path) -> list[Path]:
    if not report.is_zip:
        return []
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    with zipfile.ZipFile(report.path, "r") as zf:
        for info in zf.infolist():
            target = out_dir / info.filename
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, target.open("wb") as dst:
                while True:
                    chunk = src.read(1 << 20)
                    if not chunk:
                        break
                    dst.write(chunk)
            written.append(target)
    return written


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="lpbf_serializer.buildfile.inspect",
        description="Read-only inspection of a Renishaw .mtt / .renam / .amx file.",
    )
    p.add_argument("path", type=Path, help="Path to the build file to inspect.")
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Write the markdown report to this file instead of stdout.",
    )
    p.add_argument(
        "--extract-to",
        type=Path,
        default=None,
        help="If provided, extract every ZIP member to this directory.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    try:
        report = inspect_build_file(args.path)
    except BuildFileInspectionError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    md = _render_markdown(report)
    if args.output is None:
        sys.stdout.write(md)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(md, encoding="utf-8")
        print(f"Wrote {args.output}")

    if args.extract_to is not None:
        written = _extract_all(report, args.extract_to)
        print(f"Extracted {len(written)} entries to {args.extract_to}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
