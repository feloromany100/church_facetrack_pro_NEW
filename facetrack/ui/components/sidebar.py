"""
Sidebar — clean navigation panel. Paints its own background via paintEvent.
"""
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                                QLabel, QPushButton, QSizePolicy)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QLinearGradient, QBrush

from facetrack.ui.theme import C, F

NAV_ITEMS = [
    ("dashboard", "⬡", "Dashboard"),
    ("cameras",   "◈", "Cameras"),
    ("logs",      "≡", "Logs"),
    ("insights",  "◎", "Insights"),
    ("alerts",    "◬", "Alerts"),
    ("settings",  "⊙", "Settings"),
]

class NavButton(QPushButton):
    def __init__(self, page_id: str, icon: str, label: str, parent=None):
        super().__init__(parent)
        self.page_id = page_id
        self._active = False
        self.setFixedHeight(44)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFlat(True)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 0, 16, 0)
        lay.setSpacing(12)

        self._icon_lbl = QLabel(icon)
        self._icon_lbl.setFixedWidth(18)
        self._icon_lbl.setFont(F.get(14))
        self._icon_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._text_lbl = QLabel(label)
        self._text_lbl.setFont(F.get(F.SIZE_SM, F.MEDIUM))
        self._text_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._badge = QLabel("")
        self._badge.setFont(F.get(9, F.BOLD))
        self._badge.hide()
        self._badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        lay.addWidget(self._icon_lbl)
        lay.addWidget(self._text_lbl)
        lay.addStretch()
        lay.addWidget(self._badge)

        self._apply_style()

    def set_active(self, active: bool):
        self._active = active
        self._apply_style()

    def set_badge(self, count: int):
        if count:
            self._badge.setText(str(count))
            self._badge.setStyleSheet(
                f"color: {C.BG_BASE}; background: {C.DANGER};"
                f"border-radius: 8px; padding: 1px 5px;"
            )
            self._badge.show()
        else:
            self._badge.hide()

    def _apply_style(self):
        if self._active:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                        stop:0 {C.NEON_BLUE}1A, stop:1 transparent);
                    border: none;
                    border-left: 2px solid {C.NEON_BLUE};
                    border-radius: 0;
                }}
            """)
            self._icon_lbl.setStyleSheet(f"color: {C.NEON_BLUE};")
            self._text_lbl.setStyleSheet(f"color: {C.TEXT_PRIMARY}; font-weight: 600;")
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    border: none;
                    border-left: 2px solid transparent;
                    border-radius: 0;
                }}
                QPushButton:hover {{
                    background: {C.BG_OVERLAY};
                }}
            """)
            self._icon_lbl.setStyleSheet(f"color: {C.TEXT_MUTED};")
            self._text_lbl.setStyleSheet(f"color: {C.TEXT_SECONDARY};")

class Sidebar(QWidget):
    page_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(200)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self._buttons: dict[str, NavButton] = {}
        self._active_id = ""
        self._build()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Sidebar background
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(C.BG_SURFACE))
        p.drawRect(self.rect())
        # Right border line
        p.setPen(QPen(QColor(C.BORDER), 1))
        p.drawLine(self.width() - 1, 0, self.width() - 1, self.height())
        p.end()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Logo area
        logo = QWidget()
        logo.setFixedHeight(64)
        logo.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        logo_lay = QHBoxLayout(logo)
        logo_lay.setContentsMargins(20, 0, 16, 0)
        logo_lay.setSpacing(10)

        cross = QLabel("✝")
        cross.setFont(F.get(22, F.BOLD))
        cross.setStyleSheet(f"color: {C.GOLD};")

        name_col = QVBoxLayout()
        name_col.setSpacing(1)
        t1 = QLabel("FaceTrack")
        t1.setFont(F.get(F.SIZE_MD, F.BOLD))
        t1.setStyleSheet(f"color: {C.TEXT_PRIMARY};")
        t2 = QLabel("Church Edition")
        t2.setFont(F.get(9))
        t2.setStyleSheet(f"color: {C.TEXT_MUTED};")
        name_col.addWidget(t1)
        name_col.addWidget(t2)

        logo_lay.addWidget(cross)
        logo_lay.addLayout(name_col)
        logo_lay.addStretch()
        lay.addWidget(logo)

        # Divider
        div = _HDivider()
        lay.addWidget(div)

        # Nav label
        nav_lbl = QLabel("MENU")
        nav_lbl.setFont(F.get(9, F.BOLD))
        nav_lbl.setStyleSheet(
            f"color: {C.TEXT_MUTED}; letter-spacing: 2px; padding: 14px 20px 6px;"
        )
        lay.addWidget(nav_lbl)

        for page_id, icon, label in NAV_ITEMS:
            btn = NavButton(page_id, icon, label)
            btn.clicked.connect(lambda checked=False, pid=page_id: self._select(pid))
            self._buttons[page_id] = btn
            lay.addWidget(btn)

        lay.addStretch()

        ver = QLabel("v2.0  ·  AI Edition")
        ver.setFont(F.get(9))
        ver.setStyleSheet(f"color: {C.TEXT_MUTED}; padding: 12px 20px;")
        lay.addWidget(ver)

        self._select("dashboard")

    def _select(self, page_id: str):
        if self._active_id and self._active_id in self._buttons:
            self._buttons[self._active_id].set_active(False)
        self._active_id = page_id
        self._buttons[page_id].set_active(True)
        self.page_selected.emit(page_id)

    def set_alert_badge(self, count: int):
        btn = self._buttons.get("alerts")
        if btn:
            btn.set_badge(count)

class _HDivider(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(1)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setPen(QPen(QColor(C.BORDER), 1))
        p.drawLine(0, 0, self.width(), 0)
        p.end()
