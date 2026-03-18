"""
TopBar — clean status bar. Paints its own background.
"""
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QColor, QPen

from facetrack.ui.theme import C, F

class _Stat(QWidget):
    """Icon + value pair — no background, just text."""
    def __init__(self, icon: str, value: str, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(5)

        self._icon = QLabel(icon)
        self._icon.setFont(F.get(11))
        self._icon.setStyleSheet(f"color: {C.TEXT_MUTED};")

        self._val = QLabel(value)
        self._val.setFont(F.get(F.SIZE_SM))
        self._val.setStyleSheet(f"color: {C.TEXT_SECONDARY};")

        lay.addWidget(self._icon)
        lay.addWidget(self._val)

    def set_value(self, text: str):
        self._val.setText(text)

class _VDivider(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(1)
        self.setFixedHeight(20)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setPen(QPen(QColor(C.BORDER), 1))
        p.drawLine(0, 0, 0, self.height())
        p.end()

class TopBar(QWidget):
    alerts_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(52)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self._build()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(C.BG_SURFACE))
        p.drawRect(self.rect())
        p.setPen(QPen(QColor(C.BORDER), 1))
        p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        p.end()

    def _build(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(24, 0, 20, 0)
        lay.setSpacing(16)

        # Page title
        self._title = QLabel("Dashboard")
        self._title.setFont(F.get(F.SIZE_LG, F.BOLD))
        self._title.setStyleSheet(f"color: {C.TEXT_PRIMARY};")
        lay.addWidget(self._title)
        lay.addStretch()

        # Stats — plain text, no pill backgrounds
        self._cpu = _Stat("CPU", "—%")
        self._gpu = _Stat("GPU", "—%")
        self._cams = _Stat("CAM", "0")
        for s in (self._cpu, self._gpu, self._cams):
            lay.addWidget(s)
            lay.addWidget(_VDivider())

        # Bell button — minimal
        self._bell = QPushButton("🔔")
        self._bell.setFixedSize(32, 32)
        self._bell.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {C.BORDER};
                border-radius: 16px;
                font-size: 14px;
                color: {C.TEXT_SECONDARY};
            }}
            QPushButton:hover {{
                border-color: {C.GOLD};
                color: {C.GOLD};
            }}
        """)
        self._bell.clicked.connect(self.alerts_clicked)
        lay.addWidget(self._bell)

        # Role — text only, gold color
        self._role = QLabel("Admin")
        self._role.setFont(F.get(F.SIZE_SM, F.MEDIUM))
        self._role.setStyleSheet(f"color: {C.GOLD};")
        lay.addWidget(self._role)

    def set_title(self, title: str):
        self._title.setText(title)

    def update_stats(self, stats: dict):
        self._cpu.set_value(f"{stats.get('cpu', 0):.0f}%")
        self._gpu.set_value(f"{stats.get('gpu', 0):.0f}%")

    def set_camera_count(self, n: int):
        self._cams.set_value(str(n))

    def set_alert_count(self, n: int):
        self._bell.setText("🔔" if n == 0 else f"🔔{n}")
        self._bell.setStyleSheet(self._bell.styleSheet())
