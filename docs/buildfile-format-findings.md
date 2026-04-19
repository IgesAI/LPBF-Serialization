# Build File Format Findings (Phase 8 spike)

Investigated: 2026-04-19
Samples provided by user:

| File | Size | SHA-256 |
| ---- | ---- | ------- |
| `EC5L0020 - ENGINE CASE - FRONT - B150.mtt` | 311.50 MiB (326,629,158 B) | `682fdd6e…3a1a` |
| `EC5L0020 - ENGINE CASE - FRONT - B150.renam` | 352.49 MiB (369,617,090 B) | `f9e061ca…2973` |

Both files were produced by a recent **Renishaw QuantAM 6.x** install.

## 1. Top-line conclusion

**Both files are custom binary blobs, not ZIP archives.**

This directly contradicts prior public literature (ANSYS, Dyndrite, our own
`deep-research-report.md`) that described `.mtt` as _"a ZIP of STLs + a
machine file"_. That description was accurate for QuantAM 5.x. It is
**not** accurate for the QuantAM 6.x files we have in hand.

Practical consequence: we cannot open either file with `zipfile`, we cannot
swap an STL member, and we cannot append a new entry. Every prior plan
assumption that relied on ZIP-level manipulation is invalidated.

## 2. What the inspector actually sees

### `.mtt`

- `zipfile.is_zipfile()` returns `False`.
- Magic header (first 64 bytes):

  ```
  01 E0 00 00 00 00 00 01 FC 02 0E 4D 54 54 2D 4C
  61 79 65 72 46 69 6C 65 00 03 02 01 02 1B 02 23
  E8 04 08 E0 00 00 00 00 13 77 8E D4 05 20 EB 06
  01 01 07 20 4E 45 00 43 00 35 00 4C 00 30 00 30
  ```

  Notable substrings:
  - `0x0B..0x18`: ASCII **`MTT-LayerFile`** (length-prefixed, 14 bytes
    including trailing NUL). This is the format magic.
  - From `0x34`: UTF-16LE **`EC5L0020 - ENGINE CASE - FRONT - B150`**.
  - From `0x122`: UTF-16LE **`EC5L0021 - ENGINE CASE - REAR - B150`**.

  The structure of the bytes between these fields (`03 02 01 02 1B 02 23
  E8 …`) looks like a **Tag-Length-Value encoding**, possibly
  protobuf-adjacent. The install ships a `QuantAMAPIImpl.pta` artifact
  which is consistent with a precompiled type archive.

### Full-file UTF-16LE string scan (`.mtt`)

- Entire 311 MiB scanned. Only **two** strings of length ≥ 8 characters
  exist in the whole file, both already listed above (the two part
  names). There are **no** other UTF-16 part names, no machine name, no
  build-file metadata strings.

### `.renam`

- `zipfile.is_zipfile()` returns `False`.
- Same `01 E0 00 00 …` magic family as `.mtt` (shared envelope).
- Full-file UTF-16LE string scan: **zero** hits of length ≥ 8.
- 16 MiB ASCII scan: only random printable bytes from encoded floats, no
  human-readable tokens.

Interpretation: the `.renam` is the post-sliced TEMPUS scan-vector output.
Part identity is already "baked in" as numeric IDs inside the binary.
There is nothing in it that we can string-match, edit, or reference by
name.

## 3. What this means for the user's requirement

The user wants to drop an already-prepared `.mtt` / `.renam` / `.amx`
into this app and have it auto-assign per-part serials.

Given the findings above, the three honest paths are:

### Option A — In-place string substitution of part names in `.mtt`

What we do:

1. Open the `.mtt` read-only, locate the UTF-16LE part-name fields at their
   byte offsets, and verify their expected lengths.
2. Issue a build code (`B#0001`) and row-major order the parts (we can
   deduce ordering from the fixed offsets 0x34, 0x122, … ascending).
3. Compose a new name such as `B#0001-1 EC5L0020 - ENGINE CASE - FRONT - B150`
   and write it back **at the same byte offset**, truncating or padding to
   preserve exact file length. A length-preserving patch does not disturb
   any downstream offsets.
4. Update any length-prefix byte(s) if the encoding uses them. (We need
   to verify this from a before/after diff using two test builds.)
5. Recompute and record the SHA-256 so we have provable traceability.

Scope it does NOT cover:

- The geometry is untouched; no serial is engraved on the physical part.
- The same treatment for `.renam` is **not possible** — no name field
  exists to patch.

Confidence: medium. The patch itself is mechanically simple; the risk is
that QuantAM validates an embedded checksum or length-prefix we haven't
found yet. Only way to confirm is to patch one test file and open it in
QuantAM.

### Option B — Sidecar serialization only (no file modification)

What we do:

1. Treat the supplied `.mtt`/`.renam` as **read-only evidence**.
2. Hash it, record it in the DB, associate it with the issued build code
   (`B#0001`) and per-part serials derived from the names we extracted
   from the MTT header.
3. Produce the existing PDF report (already implemented) plus an
   **operator-facing plate token artifact** (PDF/PNG with build code +
   per-part serial table + QR) intended to be physically attached to the
   plate or affixed as a paper record before the build.
4. At QA time, the printed part's provenance is established via: build
   code on the plate label → DB row → hashed build file bytes.

Confidence: **high**. Zero file-format risk. Does not modify the build
file and therefore cannot break the printer. Does not change what gets
printed.

Downside: the printed parts carry no on-part serial. Traceability relies
entirely on the plate-level token and the DB.

### Option C — Reverse-engineer the `.mtt` TLV format (or integrate an SDK)

What we do:

1. Produce two minimal known-good `.mtt` files from QuantAM that differ
   by exactly one controlled change (e.g., single-cube build vs single-
   cube build with a different part name).
2. Byte-diff them to locate the part-name length prefix, the part
   bounding-box fields, and the machine-config block.
3. Repeat until we have a parser spec.
4. Alternatively, engage Renishaw for SDK access and skip the reverse
   engineering. Partners (Autodesk, Dyndrite, Dassault) are documented as
   using this SDK.
5. Use libSLM/PySLM as a cross-check - the library was written against
   QuantAM 5.3 and will either still work, or the diff tells us what
   changed.

Confidence: low initially, high eventually. Calendar cost is 1-3 weeks of
focused work per file format.

## 4. Recommendation

Ship **Option B now** and run **Option A as a controlled pilot** in
parallel on a throwaway test build. Option C is a separate, larger
engagement and should only be undertaken if B+A prove insufficient.

- Option B is low-risk and delivers the user's core traceability need
  (build code, per-part serials, PDF report, signed hashes) in under a
  day of additional work on top of what is already merged.
- Option A is high-value-if-safe but needs a before/after round-trip
  through QuantAM to prove the printer still accepts the patched file.
  Until that proof exists, treating Option A as production-safe would
  violate the "no assumptions" rule.
