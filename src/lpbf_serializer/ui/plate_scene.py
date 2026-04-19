"""2D plate layout scene.

A ``QGraphicsScene`` scaled so that 1 scene unit == 1 millimetre.
Parts are represented by ``PartItem``, which is draggable within the plate
bounds and carries its own serial label. Coincidence detection is a first-
class concept: the scene exposes ``has_coincident_parts()`` and highlights
offending items red. The UI's Save button is disabled while any coincidence
exists.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QStyleOptionGraphicsItem,
    QWidget,
)

from lpbf_serializer.domain.models import PlatePosition


@dataclass(frozen=True, slots=True)
class PlacedPart:
    stl_path: Path
    mesh_sha256: str
    size_x_mm: float
    size_y_mm: float


class PartItem(QGraphicsRectItem):
    COINCIDENCE_TOLERANCE_MM = 0.01

    def __init__(
        self,
        *,
        part: PlacedPart,
        x_mm: float,
        y_mm: float,
        plate_width_mm: float,
        plate_depth_mm: float,
    ) -> None:
        super().__init__(0, 0, part.size_x_mm, part.size_y_mm)
        self._part = part
        self._plate_w = plate_width_mm
        self._plate_d = plate_depth_mm
        self._label = QGraphicsSimpleTextItem("?", self)
        self._label.setBrush(QBrush(QColor("white")))
        self._label.setZValue(1)
        self._coincident = False

        self.setPen(QPen(QColor("#3AA3FF"), 0.2))
        self.setBrush(QBrush(QColor(58, 163, 255, 120)))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setPos(x_mm, y_mm)
        self.setToolTip(str(part.stl_path))

    @property
    def part(self) -> PlacedPart:
        return self._part

    def position_mm(self) -> PlatePosition:
        p = self.pos()
        return PlatePosition(x_mm=float(p.x()), y_mm=float(p.y()))

    def set_label(self, text: str) -> None:
        self._label.setText(text)
        rect = self._label.boundingRect()
        self._label.setPos(
            (self._part.size_x_mm - rect.width()) * 0.5,
            (self._part.size_y_mm - rect.height()) * 0.5,
        )

    def set_coincident(self, value: bool) -> None:
        if value == self._coincident:
            return
        self._coincident = value
        color = QColor(255, 70, 70, 170) if value else QColor(58, 163, 255, 120)
        self.setBrush(QBrush(color))

    def itemChange(
        self, change: QGraphicsItem.GraphicsItemChange, value: object
    ) -> object:
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and isinstance(
            value, QPointF
        ):
            x = min(max(0.0, value.x()), max(0.0, self._plate_w - self._part.size_x_mm))
            y = min(max(0.0, value.y()), max(0.0, self._plate_d - self._part.size_y_mm))
            return QPointF(x, y)
        return super().itemChange(change, value)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        super().paint(painter, option, widget)


class PlateScene(QGraphicsScene):
    parts_changed = Signal()

    def __init__(
        self, *, plate_width_mm: float, plate_depth_mm: float, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._plate_w = plate_width_mm
        self._plate_d = plate_depth_mm
        self.setSceneRect(QRectF(0, 0, plate_width_mm, plate_depth_mm))
        self._draw_plate()

    def _draw_plate(self) -> None:
        plate = QGraphicsRectItem(0, 0, self._plate_w, self._plate_d)
        plate.setBrush(QBrush(QColor("#1E1E24")))
        plate.setPen(QPen(QColor("#555"), 0.5))
        plate.setZValue(-10)
        self.addItem(plate)

        grid_pen = QPen(QColor("#2C2C35"), 0.1)
        step = 10.0
        x = 0.0
        while x <= self._plate_w:
            line = self.addLine(x, 0, x, self._plate_d, grid_pen)
            line.setZValue(-5)
            x += step
        y = 0.0
        while y <= self._plate_d:
            line = self.addLine(0, y, self._plate_w, y, grid_pen)
            line.setZValue(-5)
            y += step

    def add_part(self, part: PlacedPart, x_mm: float, y_mm: float) -> PartItem:
        item = PartItem(
            part=part,
            x_mm=x_mm,
            y_mm=y_mm,
            plate_width_mm=self._plate_w,
            plate_depth_mm=self._plate_d,
        )
        self.addItem(item)
        self.parts_changed.emit()
        return item

    def remove_part(self, item: PartItem) -> None:
        self.removeItem(item)
        self.parts_changed.emit()

    def part_items(self) -> tuple[PartItem, ...]:
        return tuple(it for it in self.items() if isinstance(it, PartItem))

    def refresh_coincidence(self) -> bool:
        items = self.part_items()
        colliding: set[int] = set()
        for i, a in enumerate(items):
            for j in range(i + 1, len(items)):
                b = items[j]
                ap = a.position_mm()
                bp = b.position_mm()
                if (
                    abs(ap.x_mm - bp.x_mm) < PartItem.COINCIDENCE_TOLERANCE_MM
                    and abs(ap.y_mm - bp.y_mm) < PartItem.COINCIDENCE_TOLERANCE_MM
                ):
                    colliding.add(i)
                    colliding.add(j)
        any_bad = len(colliding) > 0
        for idx, it in enumerate(items):
            it.set_coincident(idx in colliding)
        return any_bad


class PlateView(QGraphicsView):
    def __init__(self, scene: PlateScene, parent: QWidget | None = None) -> None:
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QBrush(QColor("#0F0F14")))
        self.scale(4.0, -4.0)  # mm-ish zoom; Y inverted so (0,0) is bottom-left

    def fit_to_plate(self) -> None:
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def zoom_in(self) -> None:
        self.scale(1.25, 1.25)

    def zoom_out(self) -> None:
        self.scale(0.8, 0.8)

    def part_items(self) -> Iterable[PartItem]:
        scene = self.scene()
        if isinstance(scene, PlateScene):
            return scene.part_items()
        return ()
