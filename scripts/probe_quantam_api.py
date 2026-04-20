"""Safe probe: try to LoadLibrary QuantAMAPI.dll and discover what's callable.

We do NOT invoke functions whose signatures we don't know. We only:
1. Load the DLL.
2. Confirm each export is resolvable as a function pointer.
3. Try the obviously-safe zero-argument lifecycle entries
   (initializeLogger, beginScripting with no args - if they accept void).

If any call crashes the process, that is information too.
"""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

QUANTAM_ROOT = Path(r"C:\Program Files\Renishaw\Renishaw QuantAM 6.1.0.1")


def main() -> int:
    os.add_dll_directory(str(QUANTAM_ROOT))
    os.add_dll_directory(str(QUANTAM_ROOT / "Plugins"))

    target = QUANTAM_ROOT / "QuantAMAPI.dll"
    try:
        lib = ctypes.WinDLL(str(target))
    except OSError as e:
        print(f"Cannot load {target}: {e}")
        return 2
    print(f"Loaded {target}")

    names_to_probe = [
        "qmAPI_CheckDependencies",
        "qmAPI_HasRndLicensce",
        "qmAPI_SetScriptingMode",
        "qmAPI_Record",
        "qmAPI_RecordInit",
        "qmAPI_RecordUnInit",
    ]
    for name in names_to_probe:
        try:
            fn = getattr(lib, name)
        except AttributeError:
            print(f"  ! {name}: not found")
            continue
        print(f"  - {name}: resolved at 0x{ctypes.cast(fn, ctypes.c_void_p).value:x}")

    print("\nAttempting to call obviously void() functions (skipping any with args)...")
    safe_tries = [
        "qmAPI_RecordInit",
        "qmAPI_HasRndLicensce",
    ]
    for name in safe_tries:
        try:
            fn = getattr(lib, name)
            fn.restype = ctypes.c_int
            fn.argtypes = []
            rc = fn()
            print(f"  {name}() = {rc}")
        except Exception as e:
            print(f"  {name}() raised: {type(e).__name__}: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
