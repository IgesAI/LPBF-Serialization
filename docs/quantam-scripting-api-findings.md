# QuantAM Scripting API Findings

Investigated: 2026-04-19 (after the user requested an in-place serial-
stamping workflow for existing `.mtt` / `.renam` / `.amx` files).

## TL;DR

- QuantAM 6.1.0.1 **ships a native scripting API** as `QuantAMAPI.dll`
  (307 C-style exports) plus `QuantAMAPIImpl.dll` (39 exports).
- That API is **loadable from Python** via `ctypes.WinDLL` without
  QuantAM running. We confirmed one zero-argument call
  (`qmAPI_HasRndLicensce() -> 0`) succeeds cleanly.
- **No headers or docs are shipped.** Partners (Autodesk Fusion,
  Dyndrite, Dassault, Siemens) use this API under NDA. We have the
  symbol names but not the call signatures.
- The real `.mtt` / `.renam` files from the user **are not ZIP archives**
  (see `buildfile-format-findings.md`). In-place byte editing of the
  binary without the API is reverse-engineering, not engineering.

## What the API exposes (by name)

Grouped by prefix (counts out of 307 exports in `QuantAMAPI.dll`):

| Prefix                    | N  | What it implies                                        |
| ------------------------- | -- | ------------------------------------------------------ |
| `qmBuildFile_*`           | 77 | Open/save/enumerate/modify the top-level build object  |
| `qmBuild_*`               | 55 | Higher-level "build session" operations                |
| `qmBuildFileLaser_*`      | 21 | Per-part laser assignment                              |
| `qmBuildFileModel_*`      | 18 | Per-model (part) geometry & transform queries/edits    |
| `qmCLI_*`                 | 12 | Common Layer Interface (slice) IO                      |
| `qmPart_*`                | 12 | Per-part build-style queries                           |
| `qmBuildFileValidatorV2_*`| 11 | File validation                                        |
| `qmBuildFileLayer_*`      | 10 | Per-layer queries                                      |
| `qmLayer_*`               | 10 | Per-layer scan-vector construction                     |
| `qmSampledSection_*`      | 10 | Sampled cross-sections                                 |
| `qmScanSection_*`         |  9 | Scan-section construction                              |
| `qmAPI_*`                 |  6 | API lifecycle (scripting mode, record, etc.)           |
| `qmLayerScan_*`           |  6 | Per-layer scan entries                                 |
| `qmTempusParams_*`        |  6 | TEMPUS-specific scan parameters                        |
| others                    | 44 | Profiles, materials, preview layers, renam export, etc |

The function name patterns that are directly relevant to the user's
workflow:

- `qmBuildFile_Load`, `qmBuildFile_Load_WithErrorHandler` - open `.mtt`
- `qmBuildFile_Save`, `qmBuildFile_SaveRenam`, `qmBuild_ExportMTT`,
  `qmBuild_ExportRenam` - save back
- `qmBuildFile_GetModelIDs`, `qmBuildFile_GetModelIDCount` - enumerate parts
- `qmBuildFileModel_GetName`, `qmBuildFileModel_GetNameLength` - read part name
- `qmBuildFileModel_BoundingBox` - read part bounding box (important for
  placing the serial on the top face)
- `qmBuildFileModel_GetTransformationMatrix` /
  `SetTransformationMatrix` / `Translate` / `RotateAlongZ*` - read and
  modify part placement
- `qmBuild_CreatePart`, `qmBuild_CreateClonedPart`,
  `qmBuildFile_DeleteModel` - part lifecycle
- `qmLayer_AddSinglePassEntity`, `qmLayer_AddSkin`,
  `qmLayerScan_AddPartProfileScan` - ⭐ add scan entities to specific
  layers. This is the mechanism by which we could **burn serial text
  onto the top face of a part** during the normal build, by appending
  extra scan vectors on the top N layers. No geometry modification.

`QuantAMAPIImpl.dll` exposes the session lifecycle:

- `beginScripting` / `endScripting`
- `getHandleToBuildFile` / `getHandleToBuildFileWithErrorHandler`
- `createBuild` / `deleteBuild`
- `compareBuildFiles`, `compareRenAMFiles*` - before/after diff for
  validation of our edits
- `getNewBuildFileValidator` - validate a produced file
- `initializeLogger`

## What is definitively known

- `ctypes.WinDLL(r"C:\Program Files\Renishaw\Renishaw QuantAM 6.1.0.1\QuantAMAPI.dll")`
  loads successfully.
- `qmAPI_HasRndLicensce` is callable with `argtypes=[], restype=c_int`.
  It returns `0` on this host (standard license, not R&D).
- `qmAPI_RecordInit` is **not** zero-argument. Calling it with `[]`
  raises `OSError: access violation reading 0x0`. It takes a pointer
  whose type we do not know.
- No C/C++ headers are shipped anywhere under
  `C:\Program Files\Renishaw\Renishaw QuantAM 6.1.0.1`.
- No COM registration exists under `HKCR` or `HKLM\SOFTWARE\Renishaw`.
- The shipped `QuantAM_Help.pdf` is an end-user guide only; there is
  no scripting / API section.
- `CADImportExport.exe` is a plugin executable that depends on the
  ACIS kernel and is not a general-purpose CLI.

## What is not known without the SDK

- The exact C calling convention per export (`__cdecl` vs `__stdcall`).
  Heuristic: Windows x64 collapses both to the Microsoft x64 calling
  convention, so this is less risky than on x86.
- Every function signature (argument types and return type).
- Error code conventions. Some functions appear to return `int` status
  codes; others return handle pointers; the `...WithErrorHandler`
  variants write into an out-parameter.
- Whether `beginScripting` must be called first, and with what args.
- Whether the functions require a licensed QuantAM process in the same
  session.

## The three honest forward paths

### Path A - Request the official SDK from Renishaw

The user has an active QuantAM license. Renishaw has an established
partner/developer programme (Autodesk Fusion, Dyndrite, Dassault,
Siemens). Emailing the Renishaw AM integration team with a concrete
technical request ("I want to build an internal serial-stamping tool
using the `qm*` scripting API surface visible in QuantAMAPI.dll 6.1.0.1")
should unblock the headers and documentation.

- Timeline: unknown, realistically 1-4 weeks round trip.
- Risk: may require a partner NDA we have to evaluate.
- Payoff: fully-supported, canonical API use. Serial-text-as-scan-vector
  approach (via `qmLayer_AddSinglePassEntity`) becomes cleanly
  implementable with zero guessing.

### Path B - Reverse-engineer signatures (no SDK)

Use Ghidra / IDA to disassemble `QuantAMAPI.dll` and infer signatures
from MSVC x64 calling-convention conventions (`rcx`, `rdx`, `r8`, `r9`,
floats in `xmm0`-`xmm3`). Pair with test-driven discovery: we write
small throwaway `.mtt` files through QuantAM's GUI, then exercise the
API against them and compare with `qmBuildFileCompare*`.

- Timeline: days to a couple of weeks of focused work.
- Risk: we will get at least one signature wrong at some point. Calling
  with a wrong signature in C can silently corrupt process memory. We
  must do this against scratch files only, never against the user's
  real build.
- Payoff: independence from Renishaw.

### Path C - STL-first workflow (no QuantAM API use)

Reverse the user-facing flow. Instead of editing an existing `.mtt`:

1. User hands us the per-part STLs **before** orienting them in QuantAM.
2. Our existing engraving module (Phase 3) recesses the serial into
   each part's top face.
3. User imports the engraved STLs into QuantAM as usual, orients them,
   adds supports, and saves `.mtt` as they already do.
4. Our app generates the build code, DB row, plate-token PDF, and
   audit log at the time of export (not when the `.mtt` is already
   written).

- Timeline: works today, zero additional dependencies.
- Risk: does not match the user's stated workflow
  ("I've already prepared the `.mtt`").
- Payoff: production-ready serialization pipeline with real geometry
  engraving, immediately.

### Path D - Hybrid: read-only API use + sidecar record keeping

Reverse-engineer **only** the read-only signatures
(`qmBuildFile_Load`, `qmBuildFile_GetModelIDs`,
`qmBuildFileModel_GetName`, `qmBuildFileModel_BoundingBox`,
`qmBuildFileModel_GetTransformationMatrix`,
`qmBuildFile_Unload`). Use these to enumerate the user's existing
`.mtt` with full part metadata (name, position, bounding box). Assign
serials on top of that metadata. Emit the plate-token PDF and the
database record, **without** writing to the `.mtt`. The user continues
to print the file they already had.

- Timeline: ~1-3 days.
- Risk: read-only calls cannot corrupt the file. A mis-guessed
  signature crashes our process; it does not damage user data.
- Payoff: database-level traceability with real part positions (not
  just names), today, while either waiting on the SDK (Path A) or
  deciding whether geometry engraving is even needed (Path C).

## Recommendation

1. **In parallel**: email Renishaw for the SDK (Path A). There is no
   downside to starting that clock.
2. **Now**: ship Path D so the user has real part-position data
   reflected in the database and plate token immediately, even before
   the SDK arrives.
3. **After SDK or after Path B proves out**: implement the laser
   scan-vector injection (`qmLayer_AddSinglePassEntity`) to actually
   burn the serial into each part's top face during the normal print.
   This is the elegant, zero-geometry-change answer to the user's
   original request.

No code has been written toward Paths A / B / D yet. This document is
the evidence base for the decision.
