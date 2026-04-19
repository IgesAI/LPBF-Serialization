"""Standalone UTF-16LE string scanner for Renishaw binary build files.

Intended for one-off format discovery. Scans the entire file (not just the
first N MB) for sequences of UTF-16LE printable ASCII characters of at
least ``min_len`` length and prints them in order of offset.

Usage:
    uv run python scripts/scan_utf16_strings.py <path> [--min-len 8] [--output report.md]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _is_printable(b: int) -> bool:
    return 0x20 <= b <= 0x7E


def scan_utf16(
    data: bytes, *, min_len: int = 8
) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    n = len(data)
    i = 0
    while i + 1 < n:
        if data[i + 1] == 0 and _is_printable(data[i]):
            start = i
            chars: list[int] = []
            while (
                i + 1 < n
                and data[i + 1] == 0
                and _is_printable(data[i])
            ):
                chars.append(data[i])
                i += 2
            if len(chars) >= min_len:
                out.append((start, bytes(chars).decode("ascii")))
        else:
            i += 1
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("path", type=Path)
    p.add_argument("--min-len", type=int, default=8)
    p.add_argument("--output", type=Path, default=None)
    p.add_argument(
        "--max-chunk",
        type=int,
        default=64 * 1024 * 1024,
        help="Read the file in chunks of this size (bytes). 0 = whole file.",
    )
    args = p.parse_args(argv if argv is not None else sys.argv[1:])

    if not args.path.is_file():
        print(f"error: file not found: {args.path}", file=sys.stderr)
        return 2

    size = args.path.stat().st_size
    out_lines: list[str] = []
    out_lines.append(
        f"# UTF-16LE string scan: {args.path.name}  ({size:,} bytes)\n"
    )
    out_lines.append(f"Minimum length: {args.min_len}\n")

    found: list[tuple[int, str]] = []
    with args.path.open("rb") as f:
        if args.max_chunk == 0:
            data = f.read()
            found = scan_utf16(data, min_len=args.min_len)
        else:
            base = 0
            overlap = 2 * (args.min_len + 4)
            prev_tail = b""
            while True:
                chunk = f.read(args.max_chunk)
                if not chunk:
                    break
                blob = prev_tail + chunk
                hits = scan_utf16(blob, min_len=args.min_len)
                for rel, s in hits:
                    absolute = base - len(prev_tail) + rel
                    found.append((absolute, s))
                prev_tail = blob[-overlap:] if len(blob) > overlap else blob
                base += len(chunk)

    seen: set[tuple[int, str]] = set()
    uniq: list[tuple[int, str]] = []
    for off, s in found:
        key = (off, s)
        if key in seen:
            continue
        seen.add(key)
        uniq.append((off, s))

    out_lines.append(f"Total hits: {len(uniq)}\n")
    out_lines.append("| Offset | Length | Value |")
    out_lines.append("|-------:|-------:|-------|")
    for off, s in uniq:
        escaped = s.replace("|", "\\|").replace("`", "'")
        out_lines.append(f"| 0x{off:010x} | {len(s)} | `{escaped}` |")

    text = "\n".join(out_lines) + "\n"
    if args.output is None:
        sys.stdout.write(text)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
