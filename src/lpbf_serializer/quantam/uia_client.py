"""UIA-driven QuantAM client.

This is the *only* production implementation of :class:`QuantAMClient`.
It drives the live QuantAM GUI via Windows UI Automation (UIA) using
``pywinauto``.

Because Renishaw does not publish a public automation contract for the
QuantAM GUI, this module pins its behaviour to a specific set of captured
UIA element IDs. The captured IDs live in :data:`UIA_IDS` below and are
tagged with the QuantAM build number they were captured against. If the
detected QuantAM version does not match the ID capture version, the
client raises :class:`QuantAMVersionMismatchError` instead of guessing.

Capture procedure (run against a live, licensed QuantAM):

1. Close all QuantAM windows.
2. Run ``uv run python -m lpbf_serializer.quantam.capture_ids`` (a helper
   yet to be added; see Phase 5.1 in the project plan).
3. Inspect the output, update :data:`UIA_IDS`, and commit the change.

Until IDs are captured for a particular QuantAM version, this client
refuses to export and raises :class:`QuantAMExportFailedError` with a
message pointing to this file. There is no silent fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lpbf_serializer.quantam.client import (
    ExportRequest,
    ExportResult,
    MttManifest,
    QuantAMClient,
    QuantAMInfo,
)
from lpbf_serializer.quantam.discovery import (
    assert_no_other_quantam_running,
    discover_quantam,
)
from lpbf_serializer.quantam.errors import (
    QuantAMExportFailedError,
    QuantAMLaunchError,
    QuantAMUnexpectedDialogError,
)
from lpbf_serializer.quantam.manifest import read_mtt_manifest


@dataclass(frozen=True, slots=True)
class UiaIdSet:
    """Stable automation IDs for a specific QuantAM version.

    Fields are ``control_type:auto_id_or_name`` strings. They are fed
    into ``pywinauto`` selectors as-is.
    """

    main_window_title_contains: str
    open_stl_menu_path: tuple[str, ...]
    save_build_as_menu_path: tuple[str, ...]
    save_dialog_filename_edit: str
    save_dialog_save_button: str


UIA_IDS: dict[str, UiaIdSet] = {}
"""Map QuantAM version -> captured UIA id set.

Intentionally empty in the initial commit. Populate via the capture helper
before the UIA client can export a build. See the module docstring.
"""


class UiaQuantAMClient(QuantAMClient):
    def __init__(
        self,
        *,
        exe_path: Path,
        expected_version: str,
        action_timeout_seconds: float = 30.0,
    ) -> None:
        self._exe_path = exe_path
        self._expected_version = expected_version
        self._timeout = action_timeout_seconds

    def health_check(self) -> QuantAMInfo:
        version = discover_quantam(
            exe_path=self._exe_path, expected_version=self._expected_version
        )
        return QuantAMInfo(exe_path=self._exe_path, version=version)

    def verify_mtt(self, path: Path) -> MttManifest:
        return read_mtt_manifest(path)

    def export_build(self, request: ExportRequest) -> ExportResult:
        info = self.health_check()
        ids = UIA_IDS.get(info.version)
        if ids is None:
            raise QuantAMExportFailedError(
                f"No UIA id set captured for QuantAM {info.version}. "
                "Capture IDs before attempting an export - see "
                "lpbf_serializer.quantam.uia_client docstring."
            )

        assert_no_other_quantam_running(self._exe_path)

        try:
            from pywinauto import Application, timings
        except ImportError as e:
            raise QuantAMLaunchError(
                "pywinauto is not installed; cannot drive QuantAM GUI"
            ) from e

        timings.Timings.window_find_timeout = int(self._timeout)

        app = Application(backend="uia").start(str(self._exe_path))
        try:
            window = app.window(title_re=f".*{ids.main_window_title_contains}.*")
            window.wait("ready", timeout=self._timeout)

            for stl_part in request.parts:
                self._import_stl(window, ids, stl_path=stl_part.stl_path)

            self._save_as(
                window, ids, output_mtt_path=request.output_mtt_path
            )
        except QuantAMUnexpectedDialogError:
            raise
        except Exception as e:
            raise QuantAMExportFailedError(
                f"Driving QuantAM via UIA failed: {e}"
            ) from e
        finally:
            try:
                app.kill()
            except Exception:  # noqa: BLE001
                pass

        if not request.output_mtt_path.is_file():
            raise QuantAMExportFailedError(
                f"QuantAM did not produce {request.output_mtt_path}"
            )

        manifest = self.verify_mtt(request.output_mtt_path)
        return ExportResult(mtt_path=request.output_mtt_path, manifest=manifest)

    def _import_stl(self, window: Any, ids: UiaIdSet, *, stl_path: Path) -> None:
        menu = window.menu_select(" -> ".join(ids.open_stl_menu_path))
        del menu
        dlg = window.child_window(
            control_type="Window", found_index=0
        ).wait("ready", timeout=self._timeout)
        file_edit = dlg.child_window(control_type="Edit")
        file_edit.set_edit_text(str(stl_path))
        dlg.child_window(title="Open", control_type="Button").click()

    def _save_as(
        self, window: Any, ids: UiaIdSet, *, output_mtt_path: Path
    ) -> None:
        window.menu_select(" -> ".join(ids.save_build_as_menu_path))
        dlg = window.child_window(
            control_type="Window", found_index=0
        ).wait("ready", timeout=self._timeout)
        file_edit = dlg.child_window(auto_id=ids.save_dialog_filename_edit)
        file_edit.set_edit_text(str(output_mtt_path))
        dlg.child_window(auto_id=ids.save_dialog_save_button).click()
