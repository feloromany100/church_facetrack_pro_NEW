"""
Logs page — searchable, filterable attendance table with CSV export.
"""
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                                QLabel, QComboBox, QPushButton, QFrame)
from PySide6.QtCore import Qt, QTimer

from facetrack.ui.theme import C, F, Pane
from facetrack.ui.components.data_table import DataTable
from facetrack.core.attendance_store import AttendanceStore

COLUMNS = ["Name", "Timestamp", "Camera", "Confidence", "Group", "Status"]

class LogsPage(Pane):
    def __init__(self, store: AttendanceStore, parent=None):
        super().__init__(parent)
        self._store = store
        self._build()
        self._refresh()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(8000)

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        # Filter bar — labels are just text, no boxes
        bar = QHBoxLayout()
        bar.setSpacing(10)

        cam_lbl = QLabel("Camera")
        cam_lbl.setFont(F.get(F.SIZE_SM))
        cam_lbl.setStyleSheet(f"color: {C.TEXT_SECONDARY};")
        self._cam_filter = QComboBox()
        self._cam_filter.addItems(["All Cameras", "Main Hall", "Entrance", "Youth Room"])
        self._cam_filter.setFixedHeight(32)
        self._cam_filter.currentIndexChanged.connect(self._refresh)

        grp_lbl = QLabel("Group")
        grp_lbl.setFont(F.get(F.SIZE_SM))
        grp_lbl.setStyleSheet(f"color: {C.TEXT_SECONDARY};")
        self._group_filter = QComboBox()
        self._group_filter.addItems(["All Groups", "Servant", "Youth", "Visitor", "Unknown"])
        self._group_filter.setFixedHeight(32)
        self._group_filter.currentIndexChanged.connect(self._refresh)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFixedHeight(32)
        refresh_btn.clicked.connect(self._refresh)

        bar.addWidget(cam_lbl)
        bar.addWidget(self._cam_filter)
        bar.addSpacing(8)
        bar.addWidget(grp_lbl)
        bar.addWidget(self._group_filter)
        bar.addStretch()
        bar.addWidget(refresh_btn)
        layout.addLayout(bar)

        self._table = DataTable(COLUMNS)
        layout.addWidget(self._table)

    def _refresh(self):
        records = self._store.get_all()
        cam_sel = self._cam_filter.currentText()
        if cam_sel != "All Cameras":
            records = [r for r in records if r.camera_name == cam_sel]
        grp_sel = self._group_filter.currentText()
        if grp_sel != "All Groups":
            records = [r for r in records if r.group.value == grp_sel]
        rows = []
        for r in records:
            rows.append([
                r.person_name,
                r.timestamp.strftime("%Y-%m-%d  %H:%M:%S"),
                r.camera_name,
                f"{r.confidence:.0%}" if r.confidence else "—",
                r.group.value,
                "⚠ Unknown" if r.is_unknown else "✓ Recognized",
            ])
        self._table.set_data(rows)

    def append_record(self, record):
        self._refresh()
