# LPBF Part Serializer

Desktop application for deterministic part serialization and build sequencing on
Renishaw AM400/AM400Q Laser-Powder-Bed-Fusion (LPBF) systems.

## What it does

Given a set of STL parts, the app:

1. Issues a unique, monotonically increasing build token (e.g. `B#0001`).
2. Places parts on a virtual build plate with deterministic coordinates.
3. Assigns per-part serials (`B#0001-1`, `B#0001-2`, ...) from a total ordering
   of the XY positions.
4. Optionally engraves the serial onto the STL (mesh boolean subtraction).
5. Drives a licensed **Renishaw QuantAM** installation to export a real `.mtt`
   build file. The app never fabricates a `.mtt`; if QuantAM is unreachable or
   the export cannot be verified, the operation fails loudly and nothing is
   persisted.
6. Writes an append-only audit log and a per-build PDF report suitable for
   ISO/ASTM 52901 / 52920 traceability evidence.

## Requirements

- Windows 10 / 11 (QuantAM is Windows-only).
- Renishaw QuantAM **6.1.0.1** installed and licensed.
- Python 3.11 or 3.12.
- [uv](https://docs.astral.sh/uv/) for dependency management.

## Setup

```powershell
uv sync
uv run alembic upgrade head
uv run lpbf-serializer
```

## Design tenets

- **No silent fallbacks.** Every input (STL file, DB row, QuantAM response)
  either exists or the call raises a typed exception. There is no default
  geometry, no mock build code, no "best effort" export.
- **Deterministic identifiers.** Part serials are a pure function of the
  ordered XY positions; identical inputs always produce identical serials.
- **Transactional persistence.** Build-code issuance, part writes, and audit
  events share a single database transaction. An export failure rolls the
  whole build back.
- **Verifiable exports.** Every `.mtt` produced by QuantAM is opened,
  inspected, and hashed before the build row is committed.

## Repository layout

```
src/lpbf_serializer/
  domain/      # Value objects: BuildCode, PartSerial, PlatePosition
  db/          # SQLAlchemy schema, repositories, Alembic migrations
  engine/      # Sequencer, placement ordering, serial assignment
  geometry/    # STL load/validate, serial engraving
  quantam/     # QuantAM discovery, UIA client, .mtt verification
  ui/          # PySide6 main window, plate scene, 3D viewer, history
  audit/       # Append-only audit log, PDF report generator
```

See `docs/` for architectural notes, including the QuantAM automation findings
that define the only supported export path.
