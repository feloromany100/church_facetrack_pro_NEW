"""
Cameras page — responsive grid of CameraTile widgets.
Click a tile to expand it full-screen.
"""
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                                QGridLayout, QLabel, QPushButton,
                                QScrollArea, QFrame, QSizePolicy, QDialog)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap

from facetrack.ui.theme import C, F, Pane
from facetrack.ui.components.camera_tile import CameraTile
from facetrack.models.camera import CameraState


class _ExpandedDialog(QDialog):
    """Full-screen single camera view."""

    def __init__(self, tile: CameraTile, parent=None):
        super().__init__(parent, Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet(f"background: {C.BG_BASE};")
        self.setMinimumSize(900, 600)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Close bar
        bar = QWidget()
        bar.setFixedHeight(44)
        bar.setStyleSheet(f"background: {C.BG_SURFACE}; border-bottom: 1px solid {C.BORDER};")
        bar_l = QHBoxLayout(bar)
        bar_l.setContentsMargins(16, 0, 16, 0)
        name = QLabel(tile.state.config.name)
        name.setFont(F.get(F.SIZE_MD, F.BOLD))
        name.setStyleSheet(f"color: {C.TEXT_PRIMARY};")
        close_btn = QPushButton("✕  Close")
        close_btn.setFixedHeight(30)
        close_btn.clicked.connect(self.close)
        bar_l.addWidget(name)
        bar_l.addStretch()
        bar_l.addWidget(close_btn)
        layout.addWidget(bar)

        # Expanded tile (independent widget — shares state but not identity)
        self._big_tile = CameraTile(tile.state)
        layout.addWidget(self._big_tile)

    def update_frame(self, qimg: QImage):
        self._big_tile.update_frame(qimg)

    def update_detections(self, dets: list):
        self._big_tile.update_detections(dets)


class CamerasPage(Pane):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._tiles: dict[int, CameraTile] = {}
        self._expanded: _ExpandedDialog = None
        self._expanded_cam_id: int = -1
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = QWidget()
        toolbar.setFixedHeight(50)
        toolbar.setStyleSheet(f"background: {C.BG_SURFACE}; border-bottom: 1px solid {C.BORDER};")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(20, 0, 20, 0)
        tb_layout.setSpacing(12)

        self._cam_count_lbl = QLabel("0 cameras active")
        self._cam_count_lbl.setFont(F.get(F.SIZE_SM))
        self._cam_count_lbl.setStyleSheet(f"color: {C.TEXT_SECONDARY};")
        tb_layout.addWidget(self._cam_count_lbl)
        tb_layout.addStretch()

        layout.addWidget(toolbar)

        # Grid scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        self._grid_container = Pane()
        self._grid_container.setStyleSheet("background: transparent;")
        self._grid = QGridLayout(self._grid_container)
        self._grid.setContentsMargins(20, 20, 20, 20)
        self._grid.setSpacing(16)

        scroll.setWidget(self._grid_container)
        layout.addWidget(scroll)

    def add_camera(self, state: CameraState):
        tile = CameraTile(state)
        tile.clicked.connect(self._on_tile_clicked)
        self._tiles[state.config.id] = tile
        self._relayout()
        n = len(self._tiles)
        self._cam_count_lbl.setText(f"{n} camera{'s' if n != 1 else ''} active")

    def _relayout(self):
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        tiles = list(self._tiles.values())
        n = len(tiles)
        cols = 1 if n == 1 else 2 if n <= 4 else 3
        for i, tile in enumerate(tiles):
            self._grid.addWidget(tile, i // cols, i % cols)

    def update_frame(self, cam_id: int, qimg: QImage):
        if cam_id in self._tiles:
            self._tiles[cam_id].update_frame(qimg)
        if self._expanded and self._expanded_cam_id == cam_id:
            self._expanded.update_frame(qimg)

    def update_detections(self, cam_id: int, detections: list):
        if cam_id in self._tiles:
            self._tiles[cam_id].update_detections(detections)
        if self._expanded and self._expanded_cam_id == cam_id:
            self._expanded.update_detections(detections)

    def update_fps(self, cam_id: int, fps: float):
        if cam_id in self._tiles:
            self._tiles[cam_id].update_fps(fps)

    def update_status(self, cam_id: int, status: str):
        if cam_id in self._tiles:
            self._tiles[cam_id].update_status(status)

    def _on_tile_clicked(self, cam_id: int):
        if cam_id not in self._tiles:
            return
        tile = self._tiles[cam_id]
        self._expanded_cam_id = cam_id
        self._expanded = _ExpandedDialog(tile, self)
        self._expanded.exec()
        self._expanded = None
        self._expanded_cam_id = -1