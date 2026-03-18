"""
Toast notification — non-blocking overlay that auto-dismisses.
Stacks vertically in the bottom-right corner of the parent window.
"""
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint
from PySide6.QtGui import QPainter, QColor

from facetrack.ui.theme import C, F
from facetrack.models.alert import AlertSeverity

_SEVERITY_COLORS = {
    AlertSeverity.INFO:    C.INFO,
    AlertSeverity.WARNING: C.WARNING,
    AlertSeverity.DANGER:  C.DANGER,
}

_active_toasts: list = []   # module-level stack

class Toast(QWidget):
    def __init__(self, title: str, message: str,
                 severity: AlertSeverity = AlertSeverity.INFO,
                 parent: QWidget = None, duration_ms: int = 4000):
        super().__init__(parent, Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.Tool |
                         Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._color = _SEVERITY_COLORS.get(severity, C.INFO)
        self._build(title, message)
        self._position()
        _active_toasts.append(self)
        self.show()
        QTimer.singleShot(duration_ms, self.close)

    def _build(self, title, message):
        self.setFixedWidth(320)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)

        # Accent bar
        bar = QWidget()
        bar.setFixedWidth(4)
        bar.setStyleSheet(f"background: {self._color}; border-radius: 2px;")
        layout.addWidget(bar)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        t = QLabel(title)
        t.setFont(F.get(F.SIZE_MD, F.BOLD))
        t.setStyleSheet(f"color: {C.TEXT_PRIMARY};")
        m = QLabel(message)
        m.setFont(F.get(F.SIZE_SM))
        m.setStyleSheet(f"color: {C.TEXT_SECONDARY};")
        m.setWordWrap(True)
        text_col.addWidget(t)
        text_col.addWidget(m)
        layout.addLayout(text_col)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MUTED};
                border: none; font-size: 11px;
            }}
            QPushButton:hover {{ color: {C.TEXT_PRIMARY}; }}
        """)
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignTop)

    def _position(self):
        parent = self.parent()
        if parent:
            pw, ph = parent.width(), parent.height()
        else:
            from PySide6.QtWidgets import QApplication
            screen = QApplication.primaryScreen().geometry()
            pw, ph = screen.width(), screen.height()

        margin = 16
        stack_offset = sum(t.height() + 8 for t in _active_toasts if t is not self)
        x = pw - self.width() - margin
        y = ph - 80 - stack_offset - self.sizeHint().height()
        self.move(x, y)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        bg = QColor(C.BG_ELEVATED)
        bg.setAlpha(240)
        p.setBrush(bg)
        p.drawRoundedRect(self.rect(), 10, 10)
        from PySide6.QtGui import QPen
        p.setPen(QPen(QColor(self._color + "55"), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 10, 10)
        p.end()

    def closeEvent(self, event):
        if self in _active_toasts:
            _active_toasts.remove(self)
        super().closeEvent(event)

def show_toast(title: str, message: str,
               severity: AlertSeverity = AlertSeverity.INFO,
               parent: QWidget = None):
    Toast(title, message, severity, parent)
