"""Interactive helper to capture UIA automation IDs from a live QuantAM.

Run this as an administrator against a **fresh** QuantAM instance that is
already logged in and licensed. The script:

1. Launches QuantAM at the configured path.
2. Waits for the main window.
3. Dumps the entire UIA tree (auto_id, control_type, name, rectangle) to
   ``docs/uia-capture-<version>-<timestamp>.txt`` for review.

The operator then edits
``src/lpbf_serializer/quantam/uia_client.py`` to add a new entry to
``UIA_IDS``. There is no automated write-back: the IDs table is source
code that belongs in version control.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from lpbf_serializer.config import load_settings
from lpbf_serializer.quantam.discovery import (
    assert_no_other_quantam_running,
    discover_quantam,
)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Capture QuantAM UIA elements.")
    p.add_argument("--output-dir", type=Path, default=Path("docs"))
    p.add_argument("--settle-seconds", type=float, default=5.0)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])

    settings = load_settings()
    version = discover_quantam(
        exe_path=settings.quantam_exe,
        expected_version=settings.quantam_expected_version,
    )
    assert_no_other_quantam_running(settings.quantam_exe)

    try:
        from pywinauto import Application, timings
    except ImportError:
        print("pywinauto is not installed", file=sys.stderr)
        return 2

    timings.Timings.window_find_timeout = 30

    app = Application(backend="uia").start(str(settings.quantam_exe))
    try:
        window = app.top_window()
        window.wait("ready", timeout=60)
        window.wait("visible", timeout=60)

        import time

        time.sleep(args.settle_seconds)

        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        args.output_dir.mkdir(parents=True, exist_ok=True)
        out = args.output_dir / f"uia-capture-{version}-{ts}.txt"

        with out.open("w", encoding="utf-8") as f:
            f.write(f"# QuantAM UIA capture\n")
            f.write(f"# version: {version}\n")
            f.write(f"# captured_at: {ts}\n\n")
            try:
                window.print_control_identifiers(depth=30, filename=str(out))
            except TypeError:
                lines: list[str] = []

                def _collect(el: object, depth: int = 0) -> None:
                    try:
                        lines.append(" " * depth * 2 + str(el))
                        children = el.children()  # type: ignore[attr-defined]
                    except Exception:  # noqa: BLE001
                        return
                    for c in children:
                        _collect(c, depth + 1)

                _collect(window.wrapper_object())
                f.write("\n".join(lines))
        print(f"Wrote UIA capture to {out}")
    finally:
        try:
            app.kill()
        except Exception:  # noqa: BLE001
            pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
