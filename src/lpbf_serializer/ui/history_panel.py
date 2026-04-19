"""Sidebar listing recent builds."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy.orm import sessionmaker

from lpbf_serializer.db.repositories import BuildRepository


class HistoryPanel(QWidget):
    def __init__(
        self,
        *,
        session_factory: sessionmaker,  # type: ignore[type-arg]
        prefix: str,
        digits: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._session_factory = session_factory
        self._prefix = prefix
        self._digits = digits

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._table = QTableWidget(0, 3, self)
        self._table.setHorizontalHeaderLabels(["Build", "Parts", "Created"])
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self._table)

    def refresh(self) -> None:
        with self._session_factory() as session:
            repo = BuildRepository(
                session, prefix=self._prefix, digits=self._digits
            )
            rows = repo.list_recent(limit=100)
            self._table.setRowCount(len(rows))
            for i, row in enumerate(rows):
                self._set_cell(i, 0, row.build_code)
                self._set_cell(i, 1, str(len(row.parts)))
                self._set_cell(i, 2, row.created_at.isoformat(timespec="seconds"))

    def _set_cell(self, row: int, col: int, text: str) -> None:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self._table.setItem(row, col, item)

    def bind_row_selected(self, handler: Callable[[str], None]) -> None:
        def _on_selection() -> None:
            selected = self._table.selectedItems()
            if not selected:
                return
            row = selected[0].row()
            code_item = cast("QTableWidgetItem", self._table.item(row, 0))
            handler(code_item.text())

        self._table.itemSelectionChanged.connect(_on_selection)
