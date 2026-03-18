"""
Insights page — ministry analytics: trends, groups, absences.
"""
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                                QLabel, QFrame, QScrollArea, QSizePolicy)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QColor, QFont, QPen, QBrush

from facetrack.ui.theme import C, F, Card, Pane
from facetrack.storage.attendance_store import AttendanceStore
from facetrack.models.person import PersonGroup

class _PieChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: list = []   # [(label, value, color)]
        self.setMinimumSize(200, 200)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

    def set_data(self, data: list):
        self._data = data
        self.update()

    def paintEvent(self, event):
        if not self._data:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        total = sum(v for _, v, _ in self._data) or 1
        cx, cy = self.width() // 2, self.height() // 2
        r = min(cx, cy) - 20
        angle = 0
        for label, val, color in self._data:
            span = int(val / total * 5760)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(color))
            p.drawPie(cx - r, cy - r, r * 2, r * 2, angle, span)
            angle += span
        # Center hole (donut)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(C.BG_SURFACE))
        inner = int(r * 0.55)
        p.drawEllipse(cx - inner, cy - inner, inner * 2, inner * 2)
        p.end()

class _InsightCard(Card):
    def __init__(self, title: str, value: str, desc: str,
                 icon: str, color: str, parent=None):
        super().__init__(parent, radius=10, bg=C.BG_SURFACE, border=color + "55")
        self._accent_color = color
        self.setFixedHeight(100)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(14)

        icon_lbl = QLabel(icon)
        icon_lbl.setFont(F.get(24))
        icon_lbl.setStyleSheet(f"color: {color};")
        icon_lbl.setFixedWidth(32)

        col = QVBoxLayout()
        col.setSpacing(1)
        t = QLabel(title)
        t.setFont(F.get(F.SIZE_SM))
        t.setStyleSheet(f"color: {C.TEXT_SECONDARY};")
        v = QLabel(value)
        v.setFont(F.get(F.SIZE_2XL, F.BOLD))
        v.setStyleSheet(f"color: {C.TEXT_PRIMARY};")
        d = QLabel(desc)
        d.setFont(F.get(9))
        d.setStyleSheet(f"color: {C.TEXT_MUTED};")
        col.addWidget(t)
        col.addWidget(v)
        col.addWidget(d)

        layout.addWidget(icon_lbl)
        layout.addLayout(col)
        layout.addStretch()
        self._val_lbl = v

    def set_value(self, v: str):
        self._val_lbl.setText(v)

class InsightsPage(Pane):
    def __init__(self, store: AttendanceStore, parent=None):
        super().__init__(parent)
        self._store = store
        self._build()
        self._refresh()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(10000)

    def _build(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = Pane()
        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self._main = QVBoxLayout(container)
        self._main.setContentsMargins(24, 20, 24, 24)
        self._main.setSpacing(20)

        # Top insight cards
        row1 = QHBoxLayout()
        row1.setSpacing(16)
        self._card_first  = _InsightCard("First-Time Visitors", "—",
                                          "This week", "🌟", C.GOLD)
        self._card_absent = _InsightCard("Absent This Week",    "—",
                                          "Regular members", "📉", C.DANGER)
        self._card_growth = _InsightCard("Weekly Growth",       "—",
                                          "vs last week", "📈", C.SUCCESS)
        for c in (self._card_first, self._card_absent, self._card_growth):
            c.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            row1.addWidget(c)
        self._main.addLayout(row1)

        # Bottom: pie + legend
        bottom = QHBoxLayout()
        bottom.setSpacing(16)

        pie_card = self._make_card("Group Breakdown")
        self._pie = _PieChart()
        self._pie.setMinimumHeight(220)
        pie_card.layout().addWidget(self._pie)
        bottom.addWidget(pie_card, 1)

        legend_card = self._make_card("Group Details")
        self._legend_layout = QVBoxLayout()
        self._legend_layout.setSpacing(8)
        legend_card.layout().addLayout(self._legend_layout)
        bottom.addWidget(legend_card, 1)

        self._main.addLayout(bottom)
        self._main.addStretch()

    def _make_card(self, title: str) -> QWidget:
        card = Card(radius=10, bg=C.BG_SURFACE, border=C.BORDER)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        t = QLabel(title)
        t.setFont(F.get(F.SIZE_SM, F.BOLD))
        t.setStyleSheet(f"color: {C.TEXT_PRIMARY};")
        layout.addWidget(t)
        return card

    def _refresh(self):
        records = self._store.get_all()
        today_recs = self._store.get_today()
        weekly = self._store.weekly_counts()

        # First-time visitors (unknown in today)
        first_time = sum(1 for r in today_recs if r.is_unknown)
        self._card_first.set_value(str(first_time))

        # Absent (simple: known people not seen today)
        known_today = {r.person_name for r in today_recs if not r.is_unknown}
        all_known = {r.person_name for r in records if not r.is_unknown}
        absent = len(all_known - known_today)
        self._card_absent.set_value(str(absent))

        # Growth
        if len(weekly) >= 2 and weekly[-2]:
            growth = int((weekly[-1] - weekly[-2]) / weekly[-2] * 100)
            self._card_growth.set_value(f"{'+' if growth >= 0 else ''}{growth}%")
        else:
            self._card_growth.set_value("—")

        # Group breakdown
        group_counts = {}
        for r in today_recs:
            g = r.group.value
            group_counts[g] = group_counts.get(g, 0) + 1

        group_colors = {
            "Servant": C.NEON_BLUE,
            "Youth":   C.GOLD,
            "Visitor": C.SUCCESS,
            "Unknown": C.DANGER,
        }
        pie_data = [(g, v, group_colors.get(g, C.INFO))
                    for g, v in group_counts.items()]
        self._pie.set_data(pie_data)

        # Legend
        while self._legend_layout.count():
            item = self._legend_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for g, v, color in pie_data:
            row = QHBoxLayout()
            dot = QLabel("●")
            dot.setFont(F.get(14))
            dot.setStyleSheet(f"color: {color};")
            lbl = QLabel(f"{g}")
            lbl.setFont(F.get(F.SIZE_MD))
            lbl.setStyleSheet(f"color: {C.TEXT_PRIMARY};")
            val = QLabel(str(v))
            val.setFont(F.get(F.SIZE_MD, F.BOLD))
            val.setStyleSheet(f"color: {color};")
            row.addWidget(dot)
            row.addWidget(lbl)
            row.addStretch()
            row.addWidget(val)
            w = QWidget()
            w.paintEvent = lambda _e: None  # transparent
            w.setLayout(row)
            self._legend_layout.addWidget(w)
        self._legend_layout.addStretch()
