"""
DataTable — styled QTableWidget with search + sort + export.
"""
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                                QTableWidget, QTableWidgetItem,
                                QLineEdit, QPushButton, QLabel,
                                QHeaderView, QAbstractItemView)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor

from facetrack.ui.theme import C, F

class DataTable(QWidget):
    row_clicked = Signal(int)   # row index

    def __init__(self, columns: list, parent=None):
        super().__init__(parent)
        self._columns = columns
        self._all_data: list = []
        self._build()

    def paintEvent(self, _e):
        pass  # transparent — inherits parent background

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # Toolbar
        toolbar = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("🔍  Search…")
        self._search.setFixedHeight(36)
        self._search.textChanged.connect(self._filter)
        toolbar.addWidget(self._search)
        toolbar.addStretch()

        self._count_lbl = QLabel("0 records")
        self._count_lbl.setFont(F.get(F.SIZE_SM))
        self._count_lbl.setStyleSheet(f"color: {C.TEXT_SECONDARY};")
        toolbar.addWidget(self._count_lbl)

        self._export_btn = QPushButton("⬇  Export CSV")
        self._export_btn.setFixedHeight(36)
        self._export_btn.clicked.connect(self._export)
        toolbar.addWidget(self._export_btn)
        layout.addLayout(toolbar)

        # Table
        self._table = QTableWidget(0, len(self._columns))
        self._table.setHorizontalHeaderLabels(self._columns)
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        self._table.cellClicked.connect(lambda r, _: self.row_clicked.emit(r))
        layout.addWidget(self._table)

    def set_data(self, rows: list):
        """rows: list of lists, one per row, matching columns order."""
        self._all_data = rows
        self._render(rows)

    def _render(self, rows: list):
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter |
                                      Qt.AlignmentFlag.AlignLeft)
                # Color-code confidence column if present
                if self._columns[c].lower() == "confidence":
                    try:
                        conf = float(str(val).strip("%")) / 100 \
                            if "%" in str(val) else float(val)
                        color = C.SUCCESS if conf >= 0.8 else \
                                C.WARNING if conf >= 0.5 else C.DANGER
                        item.setForeground(QColor(color))
                    except Exception:
                        pass
                self._table.setItem(r, c, item)
        self._table.setSortingEnabled(True)
        self._count_lbl.setText(f"{len(rows)} records")

    def _filter(self, text: str):
        if not text:
            self._render(self._all_data)
            return
        q = text.lower()
        filtered = [row for row in self._all_data
                    if any(q in str(v).lower() for v in row)]
        self._render(filtered)

    def _export(self):
        from PySide6.QtWidgets import QFileDialog
        import csv
        path, _ = QFileDialog.getSaveFileName(
            self, "Export CSV", "attendance.csv", "CSV Files (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(self._columns)
            writer.writerows(self._all_data)
