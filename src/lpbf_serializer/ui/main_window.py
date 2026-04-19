"""Main window.

The window wires the plate scene, 3D viewer, build history, QuantAM
health indicator, and the Save action that calls :class:`BuildService`.
Save is disabled unless:

- at least one part is placed,
- no parts are coincident,
- QuantAM reports healthy.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QToolBar,
    QWidget,
)
from sqlalchemy.orm import sessionmaker

from lpbf_serializer.audit.log import AuditLogger
from lpbf_serializer.audit.report import generate_build_report
from lpbf_serializer.config import Settings
from lpbf_serializer.db.repositories import BuildRepository
from lpbf_serializer.engine.sequencer import BuildSequencer
from lpbf_serializer.engine.serializer import PlacedPartInput
from lpbf_serializer.engine.service import BuildService
from lpbf_serializer.geometry.stl import load_stl
from lpbf_serializer.quantam.client import QuantAMClient
from lpbf_serializer.quantam.errors import QuantAMError
from lpbf_serializer.ui.history_panel import HistoryPanel
from lpbf_serializer.ui.plate_scene import (
    PartItem,
    PlacedPart,
    PlateScene,
    PlateView,
)
from lpbf_serializer.ui.viewer3d import Viewer3D


class MainWindow(QMainWindow):
    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: sessionmaker,  # type: ignore[type-arg]
        quantam_client: QuantAMClient | None = None,
    ) -> None:
        super().__init__()
        self._settings = settings
        self._session_factory = session_factory
        self._quantam_client = quantam_client
        self._quantam_healthy = False

        self.setWindowTitle("LPBF Serializer")
        self.resize(1400, 900)

        self._scene = PlateScene(
            plate_width_mm=settings.plate_width_mm,
            plate_depth_mm=settings.plate_depth_mm,
        )
        self._view = PlateView(self._scene, self)
        self.setCentralWidget(self._view)

        self._viewer3d = Viewer3D(self)
        viewer_dock = QDockWidget("3D Preview", self)
        viewer_dock.setWidget(self._viewer3d)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, viewer_dock)

        self._history = HistoryPanel(
            session_factory=session_factory,
            prefix=settings.build_code_prefix,
            digits=settings.build_code_digits,
        )
        history_dock = QDockWidget("Build History", self)
        history_dock.setWidget(self._history)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, history_dock)
        self.splitDockWidget(viewer_dock, history_dock, Qt.Orientation.Vertical)

        self._status_bar = QStatusBar(self)
        self.setStatusBar(self._status_bar)
        self._quantam_status = QLabel("QuantAM: unknown")
        self._status_bar.addPermanentWidget(self._quantam_status)

        self._build_actions()
        self._scene.selectionChanged.connect(self._on_selection_changed)
        self._scene.parts_changed.connect(self._on_parts_changed)

        self._view.fit_to_plate()
        self._history.refresh()
        self._refresh_serial_labels()
        self._refresh_quantam_status()
        self._update_save_enabled()

        self._quantam_timer = QTimer(self)
        self._quantam_timer.setInterval(15_000)
        self._quantam_timer.timeout.connect(self._refresh_quantam_status)
        self._quantam_timer.start()

    def _build_actions(self) -> None:
        toolbar = QToolBar("Main", self)
        self.addToolBar(toolbar)

        import_act = QAction("Import STL...", self)
        import_act.setShortcut(QKeySequence.StandardKey.Open)
        import_act.triggered.connect(self._on_import_stl)
        toolbar.addAction(import_act)

        self._remove_act = QAction("Remove Selected", self)
        self._remove_act.setShortcut(QKeySequence.StandardKey.Delete)
        self._remove_act.triggered.connect(self._on_remove_selected)
        toolbar.addAction(self._remove_act)

        toolbar.addSeparator()

        zoom_fit = QAction("Fit", self)
        zoom_fit.triggered.connect(self._view.fit_to_plate)
        toolbar.addAction(zoom_fit)

        zoom_in = QAction("Zoom +", self)
        zoom_in.triggered.connect(self._view.zoom_in)
        toolbar.addAction(zoom_in)

        zoom_out = QAction("Zoom -", self)
        zoom_out.triggered.connect(self._view.zoom_out)
        toolbar.addAction(zoom_out)

        toolbar.addSeparator()

        self._save_act = QAction("Save Build", self)
        self._save_act.setShortcut(QKeySequence.StandardKey.Save)
        self._save_act.triggered.connect(self._on_save_build)
        toolbar.addAction(self._save_act)

    def _on_import_stl(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Import STL",
            "",
            "STL files (*.stl)",
        )
        if not paths:
            return
        failures: list[str] = []
        for raw in paths:
            path = Path(raw)
            try:
                loaded = load_stl(path)
            except Exception as e:
                failures.append(f"{path.name}: {type(e).__name__}: {e}")
                continue

            lo, hi = loaded.bounds_mm
            size_x = max(hi[0] - lo[0], 1.0)
            size_y = max(hi[1] - lo[1], 1.0)

            placed = PlacedPart(
                stl_path=loaded.path,
                mesh_sha256=loaded.sha256,
                size_x_mm=size_x,
                size_y_mm=size_y,
            )
            start_x, start_y = self._next_free_slot(size_x, size_y)
            self._scene.add_part(placed, start_x, start_y)

        self._refresh_serial_labels()
        self._update_save_enabled()

        if failures:
            QMessageBox.warning(
                self,
                "Import errors",
                "Some files were not imported:\n\n" + "\n".join(failures),
            )

    def _next_free_slot(self, size_x: float, size_y: float) -> tuple[float, float]:
        spacing = 2.0
        existing = [it.pos() for it in self._scene.part_items()]
        x = spacing
        y = spacing
        row_height = size_y + spacing
        for _ in range(10_000):
            candidate_rect = (x, y, x + size_x, y + size_y)
            if all(
                not _rects_overlap(
                    candidate_rect,
                    (e.x(), e.y(), e.x() + size_x, e.y() + size_y),
                )
                for e in existing
            ):
                if (
                    x + size_x <= self._settings.plate_width_mm
                    and y + size_y <= self._settings.plate_depth_mm
                ):
                    return x, y
            x += size_x + spacing
            if x + size_x > self._settings.plate_width_mm:
                x = spacing
                y += row_height
                if y + size_y > self._settings.plate_depth_mm:
                    break
        return spacing, spacing

    def _on_remove_selected(self) -> None:
        for it in list(self._scene.selectedItems()):
            if isinstance(it, PartItem):
                self._scene.remove_part(it)
        self._refresh_serial_labels()
        self._update_save_enabled()

    def _on_selection_changed(self) -> None:
        for it in self._scene.selectedItems():
            if isinstance(it, PartItem):
                try:
                    self._viewer3d.show_stl(it.part.stl_path)
                except Exception as e:
                    self._status_bar.showMessage(
                        f"3D preview failed: {type(e).__name__}: {e}", 5000
                    )
                return

    def _on_parts_changed(self) -> None:
        self._refresh_serial_labels()
        self._update_save_enabled()

    def _refresh_serial_labels(self) -> None:
        items = list(self._scene.part_items())
        items.sort(
            key=lambda it: (
                int(it.position_mm().y_mm // 0.01),
                it.position_mm().x_mm,
            )
        )
        with self._session_factory() as session, session.begin():
            seq = BuildSequencer(
                session,
                prefix=self._settings.build_code_prefix,
                digits=self._settings.build_code_digits,
            )
            next_code = seq.peek()
        for idx, it in enumerate(items, start=1):
            it.set_label(f"{next_code}-{idx}")

    def _update_save_enabled(self) -> None:
        part_count = len(list(self._scene.part_items()))
        coincident = self._scene.refresh_coincidence()
        ok = part_count > 0 and not coincident and self._quantam_healthy
        self._save_act.setEnabled(ok)
        if part_count == 0:
            self._status_bar.showMessage("Add at least one STL to enable Save.")
        elif coincident:
            self._status_bar.showMessage("Resolve coincident parts (red) to enable Save.")
        elif not self._quantam_healthy:
            self._status_bar.showMessage("QuantAM is not reachable; Save disabled.")
        else:
            self._status_bar.showMessage(f"{part_count} part(s) ready.")

    def _refresh_quantam_status(self) -> None:
        if self._quantam_client is None:
            self._quantam_healthy = False
            self._quantam_status.setText("QuantAM: client not configured")
            self._update_save_enabled()
            return
        try:
            info = self._quantam_client.health_check()
        except QuantAMError as e:
            self._quantam_healthy = False
            self._quantam_status.setText(f"QuantAM: FAIL ({type(e).__name__})")
        else:
            self._quantam_healthy = True
            self._quantam_status.setText(f"QuantAM: {info.version}")
        self._update_save_enabled()

    def _on_save_build(self) -> None:
        if self._quantam_client is None:
            QMessageBox.critical(
                self, "Cannot save", "QuantAM client is not configured."
            )
            return

        inputs: list[PlacedPartInput] = []
        for it in self._scene.part_items():
            inputs.append(
                PlacedPartInput(
                    source_stl_path=it.part.stl_path,
                    mesh_sha256=it.part.mesh_sha256,
                    position=it.position_mm(),
                )
            )

        if len(inputs) == 0:
            return

        with self._session_factory() as session:
            svc = BuildService(
                session=session,
                sequencer=BuildSequencer(
                    session,
                    prefix=self._settings.build_code_prefix,
                    digits=self._settings.build_code_digits,
                ),
                build_repo=BuildRepository(
                    session,
                    prefix=self._settings.build_code_prefix,
                    digits=self._settings.build_code_digits,
                ),
                audit=AuditLogger(session, actor="gui"),
                quantam=self._quantam_client,
                export_dir=self._settings.export_dir,
            )
            try:
                saved = svc.save_build(inputs)
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Save failed",
                    f"Build was NOT saved.\n\n{type(e).__name__}: {e}",
                )
                return

        report_path: Path | None = None
        try:
            with self._session_factory() as session:
                report_path = generate_build_report(
                    session,
                    saved.build_code,
                    output_path=self._settings.report_dir
                    / f"{saved.build_code}.pdf",
                    plate_width_mm=self._settings.plate_width_mm,
                    plate_depth_mm=self._settings.plate_depth_mm,
                )
        except Exception as e:
            QMessageBox.warning(
                self,
                "Report failed",
                f"Build saved, but PDF report generation failed:\n"
                f"{type(e).__name__}: {e}",
            )

        detail = (
            f"Saved {saved.build_code}.\n"
            f"MTT: {saved.mtt_path}\n"
            f"SHA-256: {saved.mtt_sha256}"
        )
        if report_path is not None:
            detail += f"\nReport: {report_path}"
        QMessageBox.information(self, "Build saved", detail)
        self._history.refresh()
        self._refresh_serial_labels()


def _rects_overlap(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


_ = QWidget  # re-export for typing consistency
