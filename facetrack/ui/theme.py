"""
Single source of truth for all visual design tokens.
"""
from PySide6.QtGui import QColor, QFont, QPalette, QPainter, QPen, QBrush
from PySide6.QtWidgets import QApplication, QWidget, QStyleFactory
from PySide6.QtCore import Qt

# ── Palette ────────────────────────────────────────────────────────────────────
class C:
    BG_BASE      = "#080C14"
    BG_SURFACE   = "#0D1421"
    BG_ELEVATED  = "#111827"
    BG_OVERLAY   = "#1A2235"

    NEON_BLUE    = "#00D4FF"
    NEON_BLUE_DIM= "#0099BB"
    GOLD         = "#F5C842"
    GOLD_DIM     = "#B8962E"

    SUCCESS      = "#22C55E"
    WARNING      = "#F59E0B"
    DANGER       = "#EF4444"
    INFO         = "#3B82F6"

    TEXT_PRIMARY   = "#F0F4FF"
    TEXT_SECONDARY = "#7A8BA8"
    TEXT_MUTED     = "#3D4F6B"

    BORDER       = "#1E2D45"
    BORDER_GLOW  = "#00D4FF44"

# ── Typography ─────────────────────────────────────────────────────────────────
class F:
    SIZE_XS  = 10
    SIZE_SM  = 12
    SIZE_MD  = 13
    SIZE_LG  = 15
    SIZE_XL  = 18
    SIZE_2XL = 24
    SIZE_3XL = 32

    BOLD   = QFont.Weight.Bold
    MEDIUM = QFont.Weight.Medium
    NORMAL = QFont.Weight.Normal

    @staticmethod
    def get(size: int, weight=QFont.Weight.Normal) -> QFont:
        f = QFont()
        f.setFamilies(["Inter", "SF Pro Display", "Segoe UI", "Arial"])
        f.setPixelSize(size)
        f.setWeight(weight)
        return f

# ── Transparent container ─────────────────────────────────────────────────────
class Pane(QWidget):
    """
    Drop-in replacement for plain QWidget used as a layout container.
    Has a custom paintEvent that fills with BG_BASE — this prevents Fusion
    from painting its own Window-color background on top.
    Use for: page widgets, body containers, scroll container children.
    """
    def __init__(self, parent=None, bg: str = C.BG_BASE):
        super().__init__(parent)
        self._bg = QColor(bg)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._bg)
        p.drawRect(self.rect())
        p.end()

# ── Card base: sections/panels with their own background ─────────────────────
class Card(QWidget):
    """
    Any widget that needs a visible card background.
    Uses paintEvent — Fusion never overrides a custom paintEvent.
    """
    def __init__(self, parent=None, radius: int = 12,
                 bg: str = C.BG_SURFACE, border: str = C.BORDER,
                 accent: str = None):
        super().__init__(parent)
        self._radius = radius
        self._bg = QColor(bg)
        self._border = QColor(border)
        self._accent = QColor(accent) if accent else None

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(0, 0, -1, -1)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._bg)
        p.drawRoundedRect(r, self._radius, self._radius)

        p.setPen(QPen(self._border, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r, self._radius, self._radius)

        if self._accent:
            from PySide6.QtGui import QLinearGradient
            bar_h = 3
            grad = QLinearGradient(0, 0, self.width(), 0)
            grad.setColorAt(0, self._accent)
            c2 = QColor(self._accent); c2.setAlpha(0)
            grad.setColorAt(1, c2)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(grad))
            p.drawRoundedRect(0, self.height() - bar_h, self.width(), bar_h, 2, 2)
        p.end()

# ── Global QSS — only styles interactive/input widgets ────────────────────────
STYLESHEET = f"""
/* Reset everything to transparent — no widget paints its own bg by default */
QWidget {{
    background: transparent;
    color: {C.TEXT_PRIMARY};
    font-family: Inter, "Segoe UI", Arial;
    font-size: 13px;
    border: none;
    outline: none;
    selection-background-color: {C.NEON_BLUE};
    selection-color: {C.BG_BASE};
}}

/* Only these top-level containers get a real background */
QMainWindow, QDialog {{
    background: {C.BG_BASE};
}}

/* Scrollbars */
QScrollBar:vertical {{
    background: transparent;
    width: 5px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {C.BG_OVERLAY};
    border-radius: 2px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{ background: {C.NEON_BLUE_DIM}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: transparent;
    height: 5px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {C.BG_OVERLAY};
    border-radius: 2px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* Buttons — default is ghost style */
QPushButton {{
    background: transparent;
    color: {C.TEXT_SECONDARY};
    border: 1px solid {C.BORDER};
    border-radius: 7px;
    padding: 6px 16px;
    font-size: 12px;
    font-weight: 500;
}}
QPushButton:hover {{
    color: {C.TEXT_PRIMARY};
    border-color: {C.NEON_BLUE};
    background: {C.BG_OVERLAY};
}}
QPushButton:pressed {{ background: {C.BG_ELEVATED}; }}
QPushButton:disabled {{
    color: {C.TEXT_MUTED};
    border-color: {C.BG_OVERLAY};
}}

/* Primary button — used via setProperty("role","primary") */
QPushButton[role="primary"] {{
    background: {C.NEON_BLUE};
    color: {C.BG_BASE};
    border: none;
    font-weight: 600;
}}
QPushButton[role="primary"]:hover {{ background: {C.NEON_BLUE_DIM}; }}

/* Danger button */
QPushButton[role="danger"] {{
    background: transparent;
    color: {C.DANGER};
    border: 1px solid {C.DANGER}66;
}}
QPushButton[role="danger"]:hover {{ background: {C.DANGER}22; }}

/* Success button */
QPushButton[role="success"] {{
    background: transparent;
    color: {C.SUCCESS};
    border: 1px solid {C.SUCCESS}66;
}}
QPushButton[role="success"]:hover {{ background: {C.SUCCESS}22; }}

/* Inputs */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {C.BG_ELEVATED};
    border: 1px solid {C.BORDER};
    border-radius: 7px;
    padding: 6px 10px;
    color: {C.TEXT_PRIMARY};
    font-size: 12px;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {C.NEON_BLUE};
}}
QLineEdit::placeholder {{ color: {C.TEXT_MUTED}; }}

QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    background: {C.BG_OVERLAY};
    border: none;
    width: 14px;
    border-radius: 3px;
}}

QComboBox::drop-down {{ border: none; width: 20px; background: transparent; }}
QComboBox QAbstractItemView {{
    background: {C.BG_ELEVATED};
    border: 1px solid {C.BORDER};
    selection-background-color: {C.NEON_BLUE};
    selection-color: {C.BG_BASE};
    color: {C.TEXT_PRIMARY};
    outline: none;
}}

/* Slider */
QSlider {{ background: transparent; }}
QSlider::groove:horizontal {{
    background: {C.BG_OVERLAY};
    height: 3px;
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {C.NEON_BLUE};
    width: 13px;
    height: 13px;
    margin: -5px 0;
    border-radius: 7px;
}}
QSlider::sub-page:horizontal {{
    background: {C.NEON_BLUE};
    border-radius: 2px;
}}

/* CheckBox */
QCheckBox {{ background: transparent; spacing: 8px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border-radius: 4px;
    border: 1px solid {C.BORDER};
    background: {C.BG_ELEVATED};
}}
QCheckBox::indicator:checked {{
    background: {C.NEON_BLUE};
    border-color: {C.NEON_BLUE};
}}

/* Table */
QTableWidget, QTableView {{
    background: {C.BG_SURFACE};
    gridline-color: {C.BORDER};
    border: 1px solid {C.BORDER};
    border-radius: 10px;
    alternate-background-color: {C.BG_ELEVATED};
}}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{
    background: {C.BG_ELEVATED};
    color: {C.TEXT_SECONDARY};
    font-size: 10px;
    font-weight: 600;
    padding: 8px 12px;
    border: none;
    border-bottom: 1px solid {C.BORDER};
    text-transform: uppercase;
    letter-spacing: 1px;
}}
QTableWidget::item, QTableView::item {{
    padding: 8px 12px;
    border: none;
    background: transparent;
}}
QTableWidget::item:selected, QTableView::item:selected {{
    background: {C.BG_OVERLAY};
    color: {C.NEON_BLUE};
}}
QTableCornerButton::section {{ background: {C.BG_ELEVATED}; border: none; }}

/* Progress bar */
QProgressBar {{
    background: {C.BG_OVERLAY};
    border: none;
    border-radius: 2px;
    max-height: 4px;
}}
QProgressBar::chunk {{
    background: {C.NEON_BLUE};
    border-radius: 2px;
}}

/* Scroll area */
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}

/* Tooltip */
QToolTip {{
    background: {C.BG_ELEVATED};
    color: {C.TEXT_PRIMARY};
    border: 1px solid {C.BORDER};
    border-radius: 6px;
    padding: 5px 9px;
    font-size: 11px;
}}
"""

def apply_theme(app: QApplication):
    app.setStyle(QStyleFactory.create("Fusion"))
    app.setStyleSheet(STYLESHEET)
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window,          QColor(C.BG_BASE))
    p.setColor(QPalette.ColorRole.WindowText,      QColor(C.TEXT_PRIMARY))
    p.setColor(QPalette.ColorRole.Base,            QColor(C.BG_SURFACE))
    p.setColor(QPalette.ColorRole.AlternateBase,   QColor(C.BG_ELEVATED))
    p.setColor(QPalette.ColorRole.Text,            QColor(C.TEXT_PRIMARY))
    p.setColor(QPalette.ColorRole.Button,          QColor(C.BG_OVERLAY))
    p.setColor(QPalette.ColorRole.ButtonText,      QColor(C.TEXT_PRIMARY))
    p.setColor(QPalette.ColorRole.Highlight,       QColor(C.NEON_BLUE))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(C.BG_BASE))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor(C.TEXT_MUTED))
    p.setColor(QPalette.ColorRole.Mid,             QColor(C.BORDER))
    p.setColor(QPalette.ColorRole.Dark,            QColor(C.BG_ELEVATED))
    app.setPalette(p)
