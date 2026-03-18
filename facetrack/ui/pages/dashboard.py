"""
Dashboard — stat cards + chart + activity feed.
"""
from datetime import datetime
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                                QLabel, QScrollArea, QFrame, QSizePolicy)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QColor, QPen, QLinearGradient, QBrush, QFont

from facetrack.ui.theme import C, F, Card, Pane
from facetrack.ui.components.stat_card import StatCard
from facetrack.core.attendance_store import AttendanceStore

class _WeeklyChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = [0] * 7
        self._days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        self.setMinimumHeight(140)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

    def set_data(self, counts: list):
        self._data = counts
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        pl, pr, pt, pb = 8, 8, 10, 28
        cw = w - pl - pr
        ch = h - pt - pb
        max_v = max(self._data) or 1
        bw = cw // 7
        gap = max(3, bw // 6)

        p.setPen(QPen(QColor(C.BORDER), 1, Qt.PenStyle.DashLine))
        for i in range(3):
            y = pt + ch * i // 2
            p.drawLine(pl, y, w - pr, y)

        for i, val in enumerate(self._data):
            bh = int(ch * val / max_v) if val else 2
            bx = pl + i * bw + gap
            by = pt + ch - bh
            bww = bw - gap * 2

            grad = QLinearGradient(bx, by, bx, by + bh)
            grad.setColorAt(0, QColor(C.NEON_BLUE))
            c2 = QColor(C.NEON_BLUE); c2.setAlpha(40)
            grad.setColorAt(1, c2)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(grad))
            p.drawRoundedRect(bx, by, bww, bh, 2, 2)

            p.setPen(QColor(C.TEXT_MUTED))
            p.setFont(QFont("Arial", 8))
            p.drawText(bx, h - 6, self._days[i])

            if val:
                p.setPen(QColor(C.TEXT_SECONDARY))
                p.setFont(QFont("Arial", 8))
                p.drawText(bx, by - 3, str(val))
        p.end()

class _ActivityRow(QWidget):
    def __init__(self, name: str, camera: str, time_str: str,
                 is_unknown: bool = False, parent=None):
        super().__init__(parent)
        self.setFixedHeight(40)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        dot = QLabel("●")
        dot.setFont(F.get(8))
        dot.setStyleSheet(f"color: {C.DANGER if is_unknown else C.SUCCESS};")
        dot.setFixedWidth(10)

        name_lbl = QLabel(name)
        name_lbl.setFont(F.get(F.SIZE_SM, F.MEDIUM))
        name_lbl.setStyleSheet(f"color: {C.TEXT_PRIMARY};")

        cam_lbl = QLabel(camera)
        cam_lbl.setFont(F.get(F.SIZE_SM))
        cam_lbl.setStyleSheet(f"color: {C.TEXT_MUTED};")

        time_lbl = QLabel(time_str)
        time_lbl.setFont(F.get(F.SIZE_SM))
        time_lbl.setStyleSheet(f"color: {C.TEXT_MUTED};")

        lay.addWidget(dot)
        lay.addWidget(name_lbl)
        lay.addWidget(cam_lbl)
        lay.addStretch()
        lay.addWidget(time_lbl)

    def paintEvent(self, _e):
        pass  # transparent — parent Card shows through

class DashboardPage(Pane):
    def __init__(self, store: AttendanceStore, parent=None):
        super().__init__(parent)
        self._store = store
        self._build()
        self._refresh()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(5000)

    def _build(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = Pane()
        scroll.setWidget(container)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self._lay = QVBoxLayout(container)
        self._lay.setContentsMargins(28, 24, 28, 28)
        self._lay.setSpacing(20)

        # Stat cards
        cards_row = QHBoxLayout()
        cards_row.setSpacing(14)
        self._card_total   = StatCard("Attendance", "—", "Today total",   "◈", C.NEON_BLUE)
        self._card_known   = StatCard("Recognized", "—", "Known persons", "◎", C.SUCCESS)
        self._card_unknown = StatCard("Unknown",    "—", "Needs review",  "◬", C.WARNING)
        self._card_cameras = StatCard("Cameras",    "—", "Live streams",  "⬡", C.GOLD)
        for card in (self._card_total, self._card_known,
                     self._card_unknown, self._card_cameras):
            card.setFixedHeight(120)
            cards_row.addWidget(card)
        self._lay.addLayout(cards_row)

        # Bottom row
        bottom = QHBoxLayout()
        bottom.setSpacing(14)

        chart_card = Card(radius=10, bg=C.BG_SURFACE, border=C.BORDER)
        chart_lay = QVBoxLayout(chart_card)
        chart_lay.setContentsMargins(20, 16, 20, 16)
        chart_lay.setSpacing(10)
        ct = QLabel("Weekly Trend")
        ct.setFont(F.get(F.SIZE_SM, F.BOLD))
        ct.setStyleSheet(f"color: {C.TEXT_PRIMARY};")
        chart_lay.addWidget(ct)
        self._chart = _WeeklyChart()
        chart_lay.addWidget(self._chart)
        bottom.addWidget(chart_card, 3)

        feed_card = Card(radius=10, bg=C.BG_SURFACE, border=C.BORDER)
        feed_lay = QVBoxLayout(feed_card)
        feed_lay.setContentsMargins(20, 16, 20, 16)
        feed_lay.setSpacing(8)
        ft = QLabel("Recent Activity")
        ft.setFont(F.get(F.SIZE_SM, F.BOLD))
        ft.setStyleSheet(f"color: {C.TEXT_PRIMARY};")
        feed_lay.addWidget(ft)
        self._activity_layout = QVBoxLayout()
        self._activity_layout.setSpacing(0)
        self._activity_layout.setContentsMargins(0, 0, 0, 0)
        feed_lay.addLayout(self._activity_layout)
        bottom.addWidget(feed_card, 2)

        self._lay.addLayout(bottom)
        self._lay.addStretch()

    def _refresh(self):
        today = self._store.get_today()
        self._card_total.set_value(str(len(today)))
        self._card_known.set_value(str(self._store.get_known_today()))
        self._card_unknown.set_value(str(self._store.get_unknown_today()))
        self._chart.set_data(self._store.weekly_counts())

        while self._activity_layout.count():
            item = self._activity_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        for rec in self._store.get_all()[:10]:
            self._activity_layout.addWidget(
                _ActivityRow(rec.person_name, rec.camera_name,
                             rec.timestamp.strftime("%H:%M"), rec.is_unknown))
        self._activity_layout.addStretch()

    def set_camera_count(self, n: int):
        self._card_cameras.set_value(str(n))
