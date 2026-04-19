"""QuantAM install discovery and version verification.

This is the real code that runs at application startup. It does not
fabricate data: if the executable is missing, it raises. If the file
version differs from the expected version, it raises. If another QuantAM
instance is already running (automation cannot safely co-exist), it
raises.
"""

from __future__ import annotations

from pathlib import Path

import psutil

from lpbf_serializer.quantam.errors import (
    QuantAMLaunchError,
    QuantAMNotFoundError,
    QuantAMVersionMismatchError,
)


def _read_file_version(exe_path: Path) -> str:
    """Read the Windows PE ``FileVersion`` resource from ``exe_path``.

    Uses ``win32api`` via ``pywin32``. On non-Windows or when the resource
    is absent, raises ``QuantAMNotFoundError``.
    """
    try:
        from win32api import GetFileVersionInfo
    except ImportError as e:
        raise QuantAMLaunchError(
            "win32api is not available; cannot verify QuantAM version"
        ) from e

    try:
        info = GetFileVersionInfo(str(exe_path), "\\")
    except Exception as e:
        raise QuantAMNotFoundError(
            f"Could not read version info from {exe_path}: {e}"
        ) from e

    ms = info["FileVersionMS"]
    ls = info["FileVersionLS"]
    return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"


def discover_quantam(
    *,
    exe_path: Path,
    expected_version: str,
) -> str:
    """Verify install and return the detected version string.

    Raises:
        QuantAMNotFoundError: if ``exe_path`` is missing.
        QuantAMVersionMismatchError: if the PE ``FileVersion`` differs.
    """
    if not exe_path.is_file():
        raise QuantAMNotFoundError(f"QuantAM executable not found: {exe_path}")

    version = _read_file_version(exe_path)
    if version != expected_version:
        raise QuantAMVersionMismatchError(
            f"QuantAM version {version} at {exe_path} does not match "
            f"expected version {expected_version}"
        )
    return version


def assert_no_other_quantam_running(exe_path: Path) -> None:
    """Raise if any process matching the QuantAM executable is already running.

    Automation cannot safely share a QuantAM GUI instance - modal state and
    open builds of the running instance would collide with the automated
    flow. The operator must close any existing session first.
    """
    target = exe_path.name.lower()
    for proc in psutil.process_iter(attrs=["name", "exe"]):
        try:
            name = (proc.info.get("name") or "").lower()
            exe = (proc.info.get("exe") or "").lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if name == target or exe.endswith(target):
            raise QuantAMLaunchError(
                f"QuantAM is already running (pid {proc.pid}); "
                f"close it before automating a build"
            )
