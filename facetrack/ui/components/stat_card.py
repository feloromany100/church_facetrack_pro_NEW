"""
StatCard — metric card using Card base (paintEvent background, no QSS boxes).
"""
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy
from PySide6.QtCore import Qt

from facetrack.ui.theme import C, F, Card

class StatCard(Card):
    def __init__(self, title: str, value: str, subtitle: str = "",
                 icon: str = "", accent: str = C.NEON_BLUE, parent=None):
        super().__init__(parent, radius=12, bg=C.BG_SURFACE,
                         border=C.BORDER, accent=accent)
        self.setMinimumSize(160, 110)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._build(title, value, subtitle, icon, accent)

    def _build(self, title, value, subtitle, icon, accent):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 18)
        lay.setSpacing(6)

        # Icon + title row
        top = QHBoxLayout()
        top.setSpacing(8)
        if icon:
            ic = QLabel(icon)
            ic.setFont(F.get(18))
            ic.setStyleSheet(f"color: {accent};")
            top.addWidget(ic)
        t = QLabel(title.upper())
        t.setFont(F.get(9, F.MEDIUM))
        t.setStyleSheet(f"color: {C.TEXT_MUTED}; letter-spacing: 1px;")
        top.addWidget(t)
        top.addStretch()
        lay.addLayout(top)

        # Big value
        self._val = QLabel(value)
        self._val.setFont(F.get(F.SIZE_3XL, F.BOLD))
        self._val.setStyleSheet(f"color: {C.TEXT_PRIMARY};")
        lay.addWidget(self._val)

        if subtitle:
            sub = QLabel(subtitle)
            sub.setFont(F.get(F.SIZE_SM))
            sub.setStyleSheet(f"color: {C.TEXT_SECONDARY};")
            lay.addWidget(sub)

        lay.addStretch()

    def set_value(self, v: str):
        self._val.setText(v)
