"""
Alerts page — real-time unknown face alerts with action buttons.
"""
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                                QLabel, QPushButton, QScrollArea,
                                QFrame, QSizePolicy)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor

from facetrack.ui.theme import C, F, Card, Pane
from facetrack.core.alert_manager import AlertManager
from facetrack.models.alert import Alert, AlertSeverity

_SEV_COLOR = {
    AlertSeverity.INFO:    C.INFO,
    AlertSeverity.WARNING: C.WARNING,
    AlertSeverity.DANGER:  C.DANGER,
}

class _AlertCard(Card):
    add_to_db = Signal(str)
    dismissed  = Signal(str)

    def __init__(self, alert: Alert, parent=None):
        color = _SEV_COLOR.get(alert.severity, C.WARNING)
        super().__init__(parent, radius=8, bg=C.BG_SURFACE, border=color + "44")
        self._alert = alert
        self.setFixedHeight(86)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(14)

        # Icon
        icon = QLabel("⚠" if alert.severity == AlertSeverity.WARNING else
                       "🚨" if alert.severity == AlertSeverity.DANGER else "ℹ")
        icon.setFont(F.get(22))
        icon.setStyleSheet(f"color: {color};")
        icon.setFixedWidth(30)
        layout.addWidget(icon)

        # Text
        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        title = QLabel(alert.title)
        title.setFont(F.get(F.SIZE_MD, F.BOLD))
        title.setStyleSheet(f"color: {C.TEXT_PRIMARY};")
        msg = QLabel(f"{alert.message}  •  {alert.camera_name or ''}  •  "
                     f"Seen {alert.seen_count}×  •  "
                     f"{alert.timestamp.strftime('%H:%M:%S')}")
        msg.setFont(F.get(F.SIZE_SM))
        msg.setStyleSheet(f"color: {C.TEXT_SECONDARY};")
        text_col.addWidget(title)
        text_col.addWidget(msg)
        layout.addLayout(text_col)
        layout.addStretch()

        # Actions
        btn_col = QVBoxLayout()
        btn_col.setSpacing(4)
        add_btn = QPushButton("➕ Add to DB")
        add_btn.setFixedHeight(28)
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.SUCCESS}22; color: {C.SUCCESS};
                border: 1px solid {C.SUCCESS}55; border-radius: 6px;
                font-size: 11px; padding: 0 10px;
            }}
            QPushButton:hover {{ background: {C.SUCCESS}44; }}
        """)
        add_btn.clicked.connect(lambda: self.add_to_db.emit(alert.id))

        ign_btn = QPushButton("✕ Ignore")
        ign_btn.setFixedHeight(28)
        ign_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C.DANGER}22; color: {C.DANGER};
                border: 1px solid {C.DANGER}55; border-radius: 6px;
                font-size: 11px; padding: 0 10px;
            }}
            QPushButton:hover {{ background: {C.DANGER}44; }}
        """)
        ign_btn.clicked.connect(lambda: self.dismissed.emit(alert.id))

        btn_col.addWidget(add_btn)
        btn_col.addWidget(ign_btn)
        layout.addLayout(btn_col)

class AlertsPage(Pane):
    def __init__(self, manager: AlertManager, parent=None):
        super().__init__(parent)
        self._manager = manager
        self._cards: dict[str, _AlertCard] = {}
        self._build()
        self._load_existing()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(16)

        # Header
        hdr = QHBoxLayout()
        title = QLabel("Smart Alerts")
        title.setFont(F.get(F.SIZE_XL, F.BOLD))
        title.setStyleSheet(f"color: {C.TEXT_PRIMARY};")
        self._count_lbl = QLabel("0 active")
        self._count_lbl.setFont(F.get(F.SIZE_SM))
        self._count_lbl.setStyleSheet(f"color: {C.TEXT_SECONDARY};")
        clear_btn = QPushButton("Clear All")
        clear_btn.setFixedHeight(32)
        clear_btn.clicked.connect(self._clear_all)
        hdr.addWidget(title)
        hdr.addWidget(self._count_lbl)
        hdr.addStretch()
        hdr.addWidget(clear_btn)
        layout.addLayout(hdr)

        # Scroll feed
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._feed_widget = QWidget()
        self._feed_widget.paintEvent = lambda _e: None
        self._feed_layout = QVBoxLayout(self._feed_widget)
        self._feed_layout.setContentsMargins(0, 0, 0, 0)
        self._feed_layout.setSpacing(8)
        self._feed_layout.addStretch()
        scroll.setWidget(self._feed_widget)
        layout.addWidget(scroll)

    def _load_existing(self):
        for alert in self._manager.get_all():
            self._add_card(alert)

    def push_alert(self, alert: Alert):
        self._add_card(alert)

    def _add_card(self, alert: Alert):
        card = _AlertCard(alert)
        card.add_to_db.connect(self._on_add_to_db)
        card.dismissed.connect(self._on_dismiss)
        self._cards[alert.id] = card
        # Insert before the stretch
        self._feed_layout.insertWidget(0, card)
        self._update_count()

    def _on_dismiss(self, alert_id: str):
        self._manager.dismiss(alert_id)
        card = self._cards.pop(alert_id, None)
        if card:
            card.deleteLater()
        self._update_count()

    def _on_add_to_db(self, alert_id: str):
        # Hook: open "Add Person" dialog — placeholder
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(self, "Add to Database",
                                "Integration hook: open enrollment dialog here.")
        self._on_dismiss(alert_id)

    def _clear_all(self):
        for aid in list(self._cards.keys()):
            self._on_dismiss(aid)

    def _update_count(self):
        n = len(self._cards)
        self._count_lbl.setText(f"{n} active")
