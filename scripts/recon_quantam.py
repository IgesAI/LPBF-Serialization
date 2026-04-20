"""QuantAM recon: classify plugin DLLs, list exports, list imports.

One-off developer tool. Writes findings to stdout so we can decide if
and how to integrate with QuantAM's native/managed surface.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pefile

QUANTAM_ROOT = Path(r"C:\Program Files\Renishaw\Renishaw QuantAM 6.1.0.1")
PLUGINS = QUANTAM_ROOT / "Plugins"


def _is_managed(pe: pefile.PE) -> bool:
    cli_header = pe.OPTIONAL_HEADER.DATA_DIRECTORY[14]
    return bool(cli_header.Size)


def describe(path: Path) -> None:
    try:
        pe = pefile.PE(str(path), fast_load=True)
    except Exception as e:
        print(f"{path.name}: cannot parse PE: {e}")
        return

    kind = "managed" if _is_managed(pe) else "native"
    machine_raw = pe.FILE_HEADER.Machine
    machine = pefile.MACHINE_TYPE.get(machine_raw, f"0x{machine_raw:04x}")
    print(f"\n=== {path.name} ({kind}, {machine}) ===")

    pe.parse_data_directories(
        directories=[
            pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"],
            pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXPORT"],
        ]
    )

    exports: list[str] = []
    if hasattr(pe, "DIRECTORY_ENTRY_EXPORT"):
        for sym in pe.DIRECTORY_ENTRY_EXPORT.symbols:
            name = sym.name.decode("latin-1") if sym.name else f"ordinal#{sym.ordinal}"
            exports.append(name)
    print(f"exports ({len(exports)}):")
    for n in exports[:30]:
        print(f"   - {n}")
    if len(exports) > 30:
        print(f"   ... +{len(exports) - 30} more")

    deps: list[str] = []
    if hasattr(pe, "DIRECTORY_ENTRY_IMPORT"):
        for entry in pe.DIRECTORY_ENTRY_IMPORT:
            deps.append(entry.dll.decode("latin-1"))
    print(f"imports ({len(deps)}):")
    for n in deps:
        print(f"   - {n}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Recon the QuantAM install.")
    parser.add_argument(
        "targets",
        nargs="*",
        help="DLL/EXE names to probe (default: curated list).",
    )
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    defaults = [
        PLUGINS / "CADImportExport.exe",
        PLUGINS / "MTTExport.dll",
        PLUGINS / "AMX.Export.dll",
        PLUGINS / "AMX.Import.dll",
        PLUGINS / "BuildFileHandler.dll",
        PLUGINS / "STLLoader.dll",
        PLUGINS / "ScanGenerator.dll",
        PLUGINS / "Supports.dll",
        PLUGINS / "AMServices.dll",
        PLUGINS / "CLI.Import.dll",
        QUANTAM_ROOT / "QuantAMAPI.dll",
        QUANTAM_ROOT / "QuantAMAPIImpl.dll",
        QUANTAM_ROOT / "BuildFileReader.dll",
        QUANTAM_ROOT / "BuildFileWriter.dll",
        QUANTAM_ROOT / "BuildFileValidator.dll",
        QUANTAM_ROOT / "Machines.Quantam.dll",
        QUANTAM_ROOT / "QuantAM.ViewModels.dll",
        QUANTAM_ROOT / "QuantAM.UILibrary.dll",
    ]
    targets = [Path(t) for t in args.targets] if args.targets else defaults

    for t in targets:
        if not t.is_file():
            print(f"\n=== {t.name}: NOT FOUND ===")
            continue
        describe(t)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
