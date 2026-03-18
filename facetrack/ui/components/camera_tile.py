"""
CameraTile — live video tile with overlay bounding boxes.
Renders frame via QLabel pixmap swap (zero OpenGL needed).
Bounding boxes drawn with QPainter on a transparent overlay widget.
"""
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QSizePolicy
from PySide6.QtCore import Qt, Signal, QRect
from PySide6.QtGui import (QPainter, QColor, QPen, QFont, QPixmap,
                            QImage, QBrush, QLinearGradient)

from facetrack.models.camera import CameraState, CameraStatus
from facetrack.models.person import Detection
from facetrack.ui.theme import C, F

class _OverlayWidget(QWidget):
    """Transparent widget drawn on top of the video label."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._detections: list = []
        self._frame_w = 1
        self._frame_h = 1

    def update_detections(self, detections: list, frame_w: int, frame_h: int):
        self._detections = detections
        self._frame_w = max(frame_w, 1)
        self._frame_h = max(frame_h, 1)
        self.update()

    def paintEvent(self, event):
        if not self._detections:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        sx = w / self._frame_w
        sy = h / self._frame_h

        for det in self._detections:
            x1, y1, x2, y2 = det.bbox
            rx1, ry1 = int(x1 * sx), int(y1 * sy)
            rx2, ry2 = int(x2 * sx), int(y2 * sy)

            color = QColor(C.DANGER) if det.is_unknown else QColor(C.NEON_BLUE)
            glow  = QColor(color)
            glow.setAlpha(60)

            # Glow fill
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(glow)
            p.drawRoundedRect(rx1, ry1, rx2 - rx1, ry2 - ry1, 4, 4)

            # Border
            pen = QPen(color, 2)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rx1, ry1, rx2 - rx1, ry2 - ry1, 4, 4)

            # Label background
            label = f"{det.name}  {int(det.confidence * 100)}%" if not det.is_unknown else "Unknown"
            font = QFont("Helvetica Neue", 10, QFont.Weight.Bold)
            p.setFont(font)
            fm = p.fontMetrics()
            lw = fm.horizontalAdvance(label) + 12
            lh = fm.height() + 6
            lx, ly = rx1, max(0, ry1 - lh - 2)
            bg = QColor(color)
            bg.setAlpha(220)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(lx, ly, lw, lh, 4, 4)
            p.setPen(QColor("#000000") if not det.is_unknown else QColor("#ffffff"))
            p.drawText(lx + 6, ly + lh - 5, label)

        p.end()

class CameraTile(QWidget):
    clicked = Signal(int)   # emits camera id on click

    def __init__(self, state: CameraState, parent=None):
        super().__init__(parent)
        self.state = state
        self._detections = []
        self.setMinimumSize(280, 200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Video container (stacked: label + overlay)
        self._video_container = QWidget()
        self._video_container.setStyleSheet("background: #050810; border-radius: 10px;")
        self._video_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._video_lbl = QLabel(self._video_container)
        self._video_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._video_lbl.setStyleSheet("background: transparent;")
        self._video_lbl.setText("⏳  Connecting…")
        self._video_lbl.setFont(F.get(F.SIZE_SM))
        self._video_lbl.setStyleSheet(f"color: {C.TEXT_MUTED}; background: transparent;")

        self._overlay = _OverlayWidget(self._video_container)

        root.addWidget(self._video_container)

        # Info bar
        bar = QWidget()
        bar.setFixedHeight(36)
        bar.setStyleSheet(f"background: {C.BG_ELEVATED}; border-radius: 0 0 10px 10px;")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(10, 0, 10, 0)

        self._name_lbl = QLabel(self.state.config.name)
        self._name_lbl.setFont(F.get(F.SIZE_SM, F.MEDIUM))
        self._name_lbl.setStyleSheet(f"color: {C.TEXT_PRIMARY};")

        self._status_dot = QLabel("●")
        self._status_dot.setFont(F.get(F.SIZE_SM))
        self._status_dot.setStyleSheet(f"color: {C.TEXT_MUTED};")

        self._fps_lbl = QLabel("— fps")
        self._fps_lbl.setFont(F.get(F.SIZE_XS))
        self._fps_lbl.setStyleSheet(f"color: {C.TEXT_SECONDARY};")

        bar_layout.addWidget(self._status_dot)
        bar_layout.addWidget(self._name_lbl)
        bar_layout.addStretch()
        bar_layout.addWidget(self._fps_lbl)
        root.addWidget(bar)

        self.setStyleSheet(f"""
            CameraTile {{
                background: {C.BG_SURFACE};
                border: 1px solid {C.BORDER};
                border-radius: 12px;
            }}
            CameraTile:hover {{
                border: 1px solid {C.NEON_BLUE};
            }}
        """)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        vc = self._video_container
        self._video_lbl.setGeometry(0, 0, vc.width(), vc.height())
        self._overlay.setGeometry(0, 0, vc.width(), vc.height())

    def update_frame(self, qimg: QImage):
        pixmap = QPixmap.fromImage(qimg).scaled(
            self._video_container.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._video_lbl.setPixmap(pixmap)
        self._overlay.update_detections(
            self._detections, qimg.width(), qimg.height())

    def update_detections(self, detections: list):
        self._detections = detections
        self._overlay.update()

    def update_fps(self, fps: float):
        self._fps_lbl.setText(f"{fps:.1f} fps")

    def update_status(self, status_str: str):
        colors = {
            CameraStatus.LIVE.value:       C.SUCCESS,
            CameraStatus.CONNECTING.value: C.WARNING,
            CameraStatus.OFFLINE.value:    C.TEXT_MUTED,
            CameraStatus.ERROR.value:      C.DANGER,
        }
        self._status_dot.setStyleSheet(
            f"color: {colors.get(status_str, C.TEXT_MUTED)};")

    def mousePressEvent(self, event):
        self.clicked.emit(self.state.config.id)
