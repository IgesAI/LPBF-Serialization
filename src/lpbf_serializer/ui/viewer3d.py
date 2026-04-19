"""Simple 3D mesh preview embedded via pyvistaqt.

This is intentionally minimal: it shows the currently selected STL so the
operator can visually confirm orientation before placement. It is *not*
the canonical ground truth for the build - QuantAM is.
"""

from __future__ import annotations

from pathlib import Path

import pyvista as pv
from PySide6.QtWidgets import QVBoxLayout, QWidget
from pyvistaqt import QtInteractor


class Viewer3D(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._plotter = QtInteractor(self)
        layout.addWidget(self._plotter.interactor)
        self._plotter.set_background("#0F0F14")
        self._plotter.add_axes()

    def show_stl(self, path: Path) -> None:
        if not path.is_file():
            raise FileNotFoundError(f"STL file not found: {path}")
        self._plotter.clear()
        mesh = pv.read(str(path))
        self._plotter.add_mesh(
            mesh,
            color="#3AA3FF",
            show_edges=True,
            edge_color="#1E1E24",
            smooth_shading=True,
        )
        self._plotter.reset_camera()

    def clear(self) -> None:
        self._plotter.clear()
        self._plotter.add_axes()

    def close(self) -> bool:
        self._plotter.close()
        return super().close()
