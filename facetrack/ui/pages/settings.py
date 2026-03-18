"""
Settings page — clean, professional layout.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSlider, QFrame, QScrollArea, QComboBox,
    QCheckBox, QSpinBox, QFileDialog, QSizePolicy, QProgressBar,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QColor, QPen

from facetrack.ui.theme import C, F, Card, Pane
from facetrack.models.camera import CameraConfig
from facetrack.workers.camera_scanner import CameraScanner

# ── Section card ──────────────────────────────────────────────────────────────

class _Section(Card):
    """Card with a title header — children are transparent."""
    def __init__(self, title: str, parent=None):
        super().__init__(parent, radius=10, bg=C.BG_SURFACE, border=C.BORDER)
        self._inner = QVBoxLayout(self)
        self._inner.setContentsMargins(20, 16, 20, 20)
        self._inner.setSpacing(0)

        # Title row
        hdr = QHBoxLayout()
        hdr.setSpacing(8)
        dot = QLabel("▸")
        dot.setFont(F.get(10))
        dot.setStyleSheet(f"color: {C.NEON_BLUE};")
        lbl = QLabel(title)
        lbl.setFont(F.get(F.SIZE_SM, F.BOLD))
        lbl.setStyleSheet(f"color: {C.TEXT_PRIMARY};")
        hdr.addWidget(dot)
        hdr.addWidget(lbl)
        hdr.addStretch()
        self._inner.addLayout(hdr)
        self._inner.addSpacing(12)

        # Divider
        self._inner.addWidget(_Divider())
        self._inner.addSpacing(14)

    def add(self, w):
        self._inner.addWidget(w)

    def add_layout(self, l):
        self._inner.addLayout(l)

    def add_spacing(self, n: int):
        self._inner.addSpacing(n)

# ── Primitives ────────────────────────────────────────────────────────────────

class _Divider(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(1)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setPen(QPen(QColor(C.BORDER), 1))
        p.drawLine(0, 0, self.width(), 0)
        p.end()

class _Transparent(QWidget):
    """Layout-only container — paintEvent does nothing so parent shows through."""
    def __init__(self, parent=None):
        super().__init__(parent)

    def paintEvent(self, _e):
        pass  # intentionally empty — no background painted

class _Row(_Transparent):
    """Label + control + optional hint."""
    def __init__(self, label: str, control: QWidget, hint: str = "", parent=None):
        super().__init__(parent)
        self.setFixedHeight(36)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        lbl = QLabel(label)
        lbl.setFont(F.get(F.SIZE_SM))
        lbl.setStyleSheet(f"color: {C.TEXT_SECONDARY};")
        lbl.setFixedWidth(220)
        lay.addWidget(lbl)

        lay.addWidget(control)

        if hint:
            h = QLabel(hint)
            h.setFont(F.get(9))
            h.setStyleSheet(f"color: {C.TEXT_MUTED};")
            h.setContentsMargins(10, 0, 0, 0)
            lay.addWidget(h)

        lay.addStretch()

class _SliderRow(_Transparent):
    """Label | slider | value — single clean line."""
    value_changed = Signal(float)

    def __init__(self, label: str, min_v, max_v, current,
                 step=0.01, hint: str = "", parent=None):
        super().__init__(parent)
        self.setFixedHeight(32)
        self._scale = round(1 / step)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        lbl = QLabel(label)
        lbl.setFont(F.get(F.SIZE_SM))
        lbl.setStyleSheet(f"color: {C.TEXT_SECONDARY};")
        lbl.setFixedWidth(220)
        lay.addWidget(lbl)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(int(min_v * self._scale), int(max_v * self._scale))
        self._slider.setValue(int(current * self._scale))
        self._slider.setFixedWidth(200)
        lay.addWidget(self._slider)

        lay.addSpacing(10)

        self._val_lbl = QLabel(f"{current:.2f}")
        self._val_lbl.setFont(F.get(F.SIZE_SM, F.BOLD))
        self._val_lbl.setStyleSheet(f"color: {C.NEON_BLUE};")
        self._val_lbl.setFixedWidth(38)
        lay.addWidget(self._val_lbl)

        if hint:
            h = QLabel(hint)
            h.setFont(F.get(9))
            h.setStyleSheet(f"color: {C.TEXT_MUTED};")
            h.setContentsMargins(8, 0, 0, 0)
            lay.addWidget(h)

        lay.addStretch()
        self._slider.valueChanged.connect(self._on_change)

    def _on_change(self, v):
        real = v / self._scale
        self._val_lbl.setText(f"{real:.2f}")
        self.value_changed.emit(real)

class _Toggle(QCheckBox):
    def __init__(self, checked=True, parent=None):
        super().__init__(parent)
        self.setChecked(checked)
        self.setStyleSheet(f"""
            QCheckBox::indicator {{
                width: 34px; height: 18px;
                border-radius: 9px;
                border: 1px solid {C.BORDER};
                background: {C.BG_OVERLAY};
            }}
            QCheckBox::indicator:checked {{
                background: {C.NEON_BLUE};
                border-color: {C.NEON_BLUE};
            }}
        """)

# ── Camera card ───────────────────────────────────────────────────────────────

class _CameraCard(Card):
    launch_requested = Signal(object)
    stop_requested   = Signal(int)
    remove_requested = Signal(int)

    def __init__(self, config: CameraConfig, is_running: bool = False, parent=None):
        super().__init__(parent, radius=8, bg=C.BG_ELEVATED, border=C.BORDER)
        self.config = config
        self.setFixedHeight(50)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 12, 0)
        lay.setSpacing(10)

        # Status dot
        self._dot = QLabel("●")
        self._dot.setFont(F.get(9))
        self._dot.setFixedWidth(12)
        lay.addWidget(self._dot)

        # Name + source (stacked)
        info = QVBoxLayout()
        info.setSpacing(1)
        info.setContentsMargins(0, 0, 0, 0)
        self._name_lbl = QLabel(config.name)
        self._name_lbl.setFont(F.get(F.SIZE_SM, F.BOLD))
        self._name_lbl.setStyleSheet(f"color: {C.TEXT_PRIMARY};")
        self._src_lbl = QLabel(str(config.source)[:48])
        self._src_lbl.setFont(F.get(9))
        self._src_lbl.setStyleSheet(f"color: {C.TEXT_MUTED};")
        info.addWidget(self._name_lbl)
        info.addWidget(self._src_lbl)
        lay.addLayout(info, 1)

        # Location — text only, gold
        if config.location:
            loc = QLabel(config.location)
            loc.setFont(F.get(9))
            loc.setStyleSheet(f"color: {C.GOLD_DIM};")
            lay.addWidget(loc)

        # Buttons
        self._launch_btn = QPushButton("▶ Launch")
        self._launch_btn.setFixedHeight(28)
        self._launch_btn.setProperty("role", "success")
        self._launch_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.SUCCESS};
                border: 1px solid {C.SUCCESS}55; border-radius: 6px;
                font-size: 11px; font-weight: 600; padding: 0 10px;
            }}
            QPushButton:hover {{ background: {C.SUCCESS}18; }}
            QPushButton:disabled {{ color: {C.TEXT_MUTED}; border-color: {C.BG_OVERLAY}; }}
        """)
        self._launch_btn.clicked.connect(lambda: self.launch_requested.emit(self.config))

        self._stop_btn = QPushButton("■ Stop")
        self._stop_btn.setFixedHeight(28)
        self._stop_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.DANGER};
                border: 1px solid {C.DANGER}55; border-radius: 6px;
                font-size: 11px; font-weight: 600; padding: 0 10px;
            }}
            QPushButton:hover {{ background: {C.DANGER}18; }}
            QPushButton:disabled {{ color: {C.TEXT_MUTED}; border-color: {C.BG_OVERLAY}; }}
        """)
        self._stop_btn.clicked.connect(lambda: self.stop_requested.emit(self.config.id))

        rm = QPushButton("✕")
        rm.setFixedSize(26, 26)
        rm.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MUTED};
                border: none; font-size: 12px;
            }}
            QPushButton:hover {{ color: {C.DANGER}; }}
        """)
        rm.clicked.connect(lambda: self.remove_requested.emit(self.config.id))

        lay.addWidget(self._launch_btn)
        lay.addWidget(self._stop_btn)
        lay.addWidget(rm)

        self.set_running(is_running)

    def set_running(self, running: bool):
        self._launch_btn.setEnabled(not running)
        self._stop_btn.setEnabled(running)
        color = C.SUCCESS if running else C.TEXT_MUTED
        self._dot.setStyleSheet(f"color: {color};")

# ── Settings page ─────────────────────────────────────────────────────────────

class SettingsPage(Pane):
    camera_added          = Signal(object)
    camera_removed        = Signal(int)
    camera_launch         = Signal(object)
    camera_stop           = Signal(int)

    threshold_changed         = Signal(float)
    min_threshold_changed     = Signal(float)
    max_threshold_changed     = Signal(float)
    face_min_size_changed     = Signal(int)
    blur_threshold_changed    = Signal(float)
    angle_threshold_changed   = Signal(float)
    consensus_frames_changed  = Signal(int)
    lock_threshold_changed    = Signal(float)
    lock_verify_changed       = Signal(float)

    cooldown_changed           = Signal(int)
    unknown_cooldown_changed   = Signal(int)
    session_limit_changed      = Signal(int)
    persistence_thresh_changed = Signal(float)

    detect_every_n_changed  = Signal(int)
    yolo_conf_changed       = Signal(float)
    detection_size_changed  = Signal(int)

    show_quality_changed    = Signal(bool)
    show_track_id_changed   = Signal(bool)

    photos_dir_changed      = Signal(str)
    rebuild_index_requested = Signal()

    def __init__(self, cameras: list, parent=None):
        super().__init__(parent)
        self._cameras: list[CameraConfig] = list(cameras)
        self._cam_cards: dict[int, _CameraCard] = {}
        self._running_ids: set[int] = set()
        self._scanner = None
        self._load_config()
        self._build()
        self._wire_live_config()

    def _wire_live_config(self):
        """Connect UI signals to the ConfigService hot reload."""
        self.threshold_changed.connect(lambda v: self._push_config("BASE_SIMILARITY_THRESHOLD", v))
        self.min_threshold_changed.connect(lambda v: self._push_config("MIN_SIMILARITY_THRESHOLD", v))
        self.max_threshold_changed.connect(lambda v: self._push_config("MAX_SIMILARITY_THRESHOLD", v))
        self.face_min_size_changed.connect(lambda v: self._push_config("FACE_MIN_SIZE", v))
        self.blur_threshold_changed.connect(lambda v: self._push_config("FACE_BLUR_THRESHOLD", v))
        self.angle_threshold_changed.connect(lambda v: self._push_config("FACE_ANGLE_THRESHOLD", v))
        self.consensus_frames_changed.connect(lambda v: self._push_config("MIN_CONSENSUS_FRAMES", v))
        self.lock_threshold_changed.connect(lambda v: self._push_config("IDENTITY_LOCK_THRESHOLD", v))
        self.lock_verify_changed.connect(lambda v: self._push_config("LOCK_EMBEDDING_VERIFY", v))
        
        self.cooldown_changed.connect(lambda v: self._push_config("COOLDOWN_SECONDS", v))
        self.unknown_cooldown_changed.connect(lambda v: self._push_config("UNKNOWN_COOLDOWN", v))
        self.session_limit_changed.connect(lambda v: self._push_config("UNKNOWN_SESSION_LIMIT", v))
        self.persistence_thresh_changed.connect(lambda v: self._push_config("PERSISTENCE_RECOVERY_THRESHOLD", v))
        
        self.yolo_conf_changed.connect(lambda v: self._push_config("PERSON_CONF_THRESHOLD", v))
        self.detection_size_changed.connect(lambda v: self._push_config("DETECTION_SIZE", (v, v)))
        
        self.show_quality_changed.connect(lambda v: self._push_config("SHOW_QUALITY_SCORE", v))
        self.show_track_id_changed.connect(lambda v: self._push_config("SHOW_TRACK_ID", v))

    def _load_config(self):
        try:
            from facetrack.services.config_service import ConfigService
            cfg = ConfigService().load()
            self._base_thresh      = cfg.BASE_SIMILARITY_THRESHOLD
            self._min_thresh       = cfg.MIN_SIMILARITY_THRESHOLD
            self._max_thresh       = cfg.MAX_SIMILARITY_THRESHOLD
            self._face_min_size    = cfg.FACE_MIN_SIZE
            self._blur_thresh      = cfg.FACE_BLUR_THRESHOLD
            self._angle_thresh     = cfg.FACE_ANGLE_THRESHOLD
            self._consensus_frames = cfg.MIN_CONSENSUS_FRAMES
            self._lock_thresh      = cfg.IDENTITY_LOCK_THRESHOLD
            self._lock_verify      = cfg.LOCK_EMBEDDING_VERIFY
            self._cooldown         = cfg.COOLDOWN_SECONDS
            self._unk_cooldown     = cfg.UNKNOWN_COOLDOWN
            self._session_limit    = cfg.UNKNOWN_SESSION_LIMIT
            self._persist_thresh   = cfg.PERSISTENCE_RECOVERY_THRESHOLD
            self._yolo_conf        = cfg.PERSON_CONF_THRESHOLD
            self._det_size         = cfg.DETECTION_SIZE[0]
            self._show_quality     = cfg.SHOW_QUALITY_SCORE
            self._show_track_id    = cfg.SHOW_TRACK_ID
            self._photos_dir       = cfg.PHOTOS_DIR
        except Exception:
            self._base_thresh=0.42; self._min_thresh=0.35; self._max_thresh=0.60
            self._face_min_size=40; self._blur_thresh=10.0; self._angle_thresh=60.0
            self._consensus_frames=1; self._lock_thresh=0.42; self._lock_verify=0.38
            self._cooldown=300; self._unk_cooldown=5; self._session_limit=60
            self._persist_thresh=0.35; self._yolo_conf=0.35; self._det_size=640
            self._show_quality=True; self._show_track_id=True; self._photos_dir="photos"

    def _build(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = Pane()
        container.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        scroll.setWidget(container)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        lay = QVBoxLayout(container)
        lay.setContentsMargins(28, 24, 28, 32)
        lay.setSpacing(16)

        lay.addWidget(self._build_cameras())
        lay.addWidget(self._build_recognition())
        lay.addWidget(self._build_tracking())
        lay.addWidget(self._build_performance())
        lay.addWidget(self._build_display())
        lay.addWidget(self._build_database())
        lay.addWidget(self._build_role())
        lay.addStretch()

    # ── Camera section ────────────────────────────────────────────────────────
    def _build_cameras(self) -> QWidget:
        sec = _Section("Camera Management")

        # Scan bar
        scan_row = QHBoxLayout()
        scan_row.setSpacing(8)

        self._subnet_input = QLineEdit()
        self._subnet_input.setPlaceholderText("Subnet  e.g. 192.168.1")
        self._subnet_input.setFixedHeight(30)
        self._subnet_input.setFixedWidth(180)

        self._rtsp_user = QLineEdit()
        self._rtsp_user.setPlaceholderText("User")
        self._rtsp_user.setFixedHeight(30)
        self._rtsp_user.setFixedWidth(72)

        self._rtsp_pass = QLineEdit()
        self._rtsp_pass.setPlaceholderText("Password")
        self._rtsp_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self._rtsp_pass.setFixedHeight(30)
        self._rtsp_pass.setFixedWidth(90)

        self._scan_btn = QPushButton("Scan")
        self._scan_btn.setFixedHeight(30)
        self._scan_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.NEON_BLUE};
                border: 1px solid {C.NEON_BLUE}55; border-radius: 7px;
                font-size: 12px; font-weight: 600; padding: 0 14px;
            }}
            QPushButton:hover {{ background: {C.NEON_BLUE}18; }}
            QPushButton:disabled {{ color: {C.TEXT_MUTED}; border-color: {C.BORDER}; }}
        """)
        self._scan_btn.clicked.connect(self._start_scan)

        self._stop_scan_btn = QPushButton("✕")
        self._stop_scan_btn.setFixedSize(30, 30)
        self._stop_scan_btn.setEnabled(False)
        self._stop_scan_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MUTED};
                border: 1px solid {C.BORDER}; border-radius: 7px; font-size: 12px;
            }}
            QPushButton:hover {{ color: {C.DANGER}; border-color: {C.DANGER}55; }}
            QPushButton:disabled {{ color: {C.TEXT_MUTED}; border-color: {C.BORDER}; }}
        """)
        self._stop_scan_btn.clicked.connect(self._abort_scan)

        scan_row.addWidget(self._subnet_input)
        scan_row.addWidget(self._rtsp_user)
        scan_row.addWidget(self._rtsp_pass)
        scan_row.addWidget(self._scan_btn)
        scan_row.addWidget(self._stop_scan_btn)
        scan_row.addStretch()
        sec.add_layout(scan_row)
        sec.add_spacing(6)

        self._scan_progress = QProgressBar()
        self._scan_progress.setRange(0, 100)
        self._scan_progress.setFixedHeight(3)
        self._scan_progress.setTextVisible(False)
        self._scan_progress.hide()
        sec.add(self._scan_progress)

        self._scan_status = QLabel("")
        self._scan_status.setFont(F.get(9))
        self._scan_status.setStyleSheet(f"color: {C.TEXT_MUTED};")
        sec.add(self._scan_status)
        sec.add_spacing(4)

        self._cam_list_layout = QVBoxLayout()
        self._cam_list_layout.setSpacing(6)
        for cfg in self._cameras:
            self._add_cam_card(cfg, running=True)
        sec.add_layout(self._cam_list_layout)
        sec.add_spacing(8)

        sec.add(_Divider())
        sec.add_spacing(10)

        # Manual add
        add_row = QHBoxLayout()
        add_row.setSpacing(8)
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("Camera name")
        self._name_input.setFixedHeight(30)
        self._src_input = QLineEdit()
        self._src_input.setPlaceholderText("RTSP URL or 0")
        self._src_input.setFixedHeight(30)
        self._loc_input = QLineEdit()
        self._loc_input.setPlaceholderText("Location")
        self._loc_input.setFixedHeight(30)
        add_btn = QPushButton("Add")
        add_btn.setFixedHeight(30)
        add_btn.clicked.connect(self._manual_add)
        add_row.addWidget(self._name_input, 1)
        add_row.addWidget(self._src_input, 2)
        add_row.addWidget(self._loc_input, 1)
        add_row.addWidget(add_btn)
        sec.add_layout(add_row)
        return sec

    # ── Recognition section ───────────────────────────────────────────────────
    def _build_recognition(self) -> QWidget:
        sec = _Section("Recognition Thresholds")
        sliders = [
            ("Base Similarity",    0.20, 0.80, self._base_thresh,  0.01, self.threshold_changed,       "Higher = stricter"),
            ("Min Threshold",      0.10, 0.60, self._min_thresh,   0.01, self.min_threshold_changed,   "Adaptive floor"),
            ("Max Threshold",      0.40, 0.90, self._max_thresh,   0.01, self.max_threshold_changed,   "Adaptive ceiling"),
            ("Identity Lock",      0.30, 0.80, self._lock_thresh,  0.01, self.lock_threshold_changed,  "Min score to lock"),
            ("Lock Verify",        0.20, 0.70, self._lock_verify,  0.01, self.lock_verify_changed,     "Re-verify each frame"),
            ("Blur Threshold",     1.0, 100.0, self._blur_thresh,  1.0,  self.blur_threshold_changed,  "Laplacian variance"),
            ("Max Face Angle °",  10.0,  90.0, self._angle_thresh, 1.0,  self.angle_threshold_changed, "Reject tilted faces"),
        ]
        for label, mn, mx, cur, step, sig, hint in sliders:
            row = _SliderRow(label, mn, mx, cur, step, hint)
            row.value_changed.connect(sig)
            sec.add(row)

        sec.add_spacing(4)
        for label, rng, val, suffix, sig, hint in [
            ("Consensus Frames", (1, 20),   self._consensus_frames, "",    self.consensus_frames_changed, "Votes before name"),
            ("Min Face Size",    (20, 200), self._face_min_size,    " px", self.face_min_size_changed,    "Ignore smaller"),
        ]:
            sp = QSpinBox()
            sp.setRange(*rng); sp.setValue(val)
            sp.setFixedWidth(80); sp.setFixedHeight(28)
            if suffix: sp.setSuffix(suffix)
            sp.valueChanged.connect(sig)
            sec.add(_Row(label, sp, hint))
        return sec

    # ── Tracking section ──────────────────────────────────────────────────────
    def _build_tracking(self) -> QWidget:
        sec = _Section("Tracking & Attendance")
        for label, rng, val, suffix, sig, hint in [
            ("Attendance Cooldown",   (10, 3600), self._cooldown,      " s", self.cooldown_changed,         "Min secs between logs"),
            ("Unknown Save Cooldown", (1,  120),  self._unk_cooldown,  " s", self.unknown_cooldown_changed, "Min secs between crops"),
            ("Unknown Session Limit", (1,  500),  self._session_limit, "",   self.session_limit_changed,    "Max unknowns/session"),
        ]:
            sp = QSpinBox()
            sp.setRange(*rng); sp.setValue(val)
            sp.setFixedWidth(90); sp.setFixedHeight(28)
            if suffix: sp.setSuffix(suffix)
            sp.valueChanged.connect(sig)
            sec.add(_Row(label, sp, hint))

        row = _SliderRow("Persistence Recovery", 0.10, 0.80, self._persist_thresh,
                         hint="Min score to recover identity")
        row.value_changed.connect(self.persistence_thresh_changed)
        sec.add(row)
        return sec

    # ── Performance section ───────────────────────────────────────────────────
    def _build_performance(self) -> QWidget:
        sec = _Section("Performance")

        sp = QSpinBox()
        sp.setRange(1, 10); sp.setValue(3)
        sp.setFixedWidth(70); sp.setFixedHeight(28)
        sp.valueChanged.connect(self.detect_every_n_changed)
        sec.add(_Row("Inference Every N Frames", sp, "1=every frame"))

        row = _SliderRow("YOLO Confidence", 0.10, 0.90, self._yolo_conf,
                         hint="Lower = more detections")
        row.value_changed.connect(self.yolo_conf_changed)
        sec.add(row)

        combo = QComboBox()
        combo.addItems(["320  fastest", "480", "640  balanced", "960  accurate"])
        sizes = [320, 480, 640, 960]
        combo.setCurrentIndex(sizes.index(self._det_size) if self._det_size in sizes else 2)
        combo.setFixedHeight(28); combo.setFixedWidth(160)
        combo.currentIndexChanged.connect(lambda i: self.detection_size_changed.emit(sizes[i]))
        sec.add(_Row("Detection Input Size", combo))
        return sec

    # ── Display section ───────────────────────────────────────────────────────
    def _build_display(self) -> QWidget:
        sec = _Section("Display Options")
        for label, val, sig in [
            ("Show Quality Score", self._show_quality, self.show_quality_changed),
            ("Show Track ID",      self._show_track_id, self.show_track_id_changed),
        ]:
            t = _Toggle(val)
            t.stateChanged.connect(lambda s, _s=sig: _s.emit(bool(s)))
            sec.add(_Row(label, t))
        return sec

    # ── Database section ──────────────────────────────────────────────────────
    def _build_database(self) -> QWidget:
        sec = _Section("Database & Enrollment")

        dir_row = QHBoxLayout()
        dir_row.setSpacing(8)
        self._photos_lbl = QLabel(self._photos_dir)
        self._photos_lbl.setFont(F.get(F.SIZE_SM))
        self._photos_lbl.setStyleSheet(f"color: {C.TEXT_SECONDARY};")
        browse_btn = QPushButton("Browse")
        browse_btn.setFixedHeight(28)
        browse_btn.clicked.connect(self._browse_photos)
        dir_row.addWidget(QLabel("Photos Dir"))
        dir_row.addSpacing(8)
        dir_row.addWidget(self._photos_lbl, 1)
        dir_row.addWidget(browse_btn)
        w = QWidget()
        w.paintEvent = lambda _e: None
        w.setLayout(dir_row)
        sec.add(w)

        rebuild_btn = QPushButton("Rebuild Face Index")
        rebuild_btn.setFixedHeight(30)
        rebuild_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.WARNING};
                border: 1px solid {C.WARNING}55; border-radius: 7px;
                font-size: 12px; font-weight: 600; padding: 0 16px;
            }}
            QPushButton:hover {{ background: {C.WARNING}18; }}
        """)
        rebuild_btn.clicked.connect(self.rebuild_index_requested)
        sec.add(rebuild_btn)
        return sec

    # ── Role section ──────────────────────────────────────────────────────────
    def _build_role(self) -> QWidget:
        sec = _Section("Role & Access")
        combo = QComboBox()
        combo.addItems(["Admin", "Servant", "Viewer"])
        combo.setFixedHeight(28); combo.setFixedWidth(140)
        sec.add(_Row("Current Role", combo, "Controls accessible pages"))
        return sec

    # ── Camera helpers ────────────────────────────────────────────────────────
    def _add_cam_card(self, cfg: CameraConfig, running: bool = False):
        if cfg.id in self._cam_cards:
            return
        card = _CameraCard(cfg, is_running=running)
        card.launch_requested.connect(self._on_launch)
        card.stop_requested.connect(self._on_stop)
        card.remove_requested.connect(self._on_remove)
        self._cam_list_layout.addWidget(card)
        self._cam_cards[cfg.id] = card
        if running:
            self._running_ids.add(cfg.id)

    # ── Config syncing ────────────────────────────────────────────────────────
    def _push_config(self, key: str, value):
        from facetrack.services.config_service import ConfigService
        ConfigService().update_config({key: value})

    def notify_camera_started(self, cam_id: int):
        self._running_ids.add(cam_id)
        if cam_id in self._cam_cards:
            self._cam_cards[cam_id].set_running(True)

    def notify_camera_stopped(self, cam_id: int):
        self._running_ids.discard(cam_id)
        if cam_id in self._cam_cards:
            self._cam_cards[cam_id].set_running(False)

    def _on_launch(self, cfg): self.camera_launch.emit(cfg)
    def _on_stop(self, cam_id): self.camera_stop.emit(cam_id)

    def _on_remove(self, cam_id: int):
        card = self._cam_cards.pop(cam_id, None)
        if card: card.deleteLater()
        self._cameras = [c for c in self._cameras if c.id != cam_id]
        self._running_ids.discard(cam_id)
        self.camera_removed.emit(cam_id)

    def _manual_add(self):
        name = self._name_input.text().strip()
        src  = self._src_input.text().strip()
        loc  = self._loc_input.text().strip()
        if not name or not src:
            return
        new_id = max((c.id for c in self._cameras), default=-1) + 1
        cfg = CameraConfig(id=new_id, name=name, source=src, location=loc)
        self._cameras.append(cfg)
        self._add_cam_card(cfg, running=False)
        self._name_input.clear(); self._src_input.clear(); self._loc_input.clear()
        self.camera_added.emit(cfg)

    def _start_scan(self):
        if self._scanner and self._scanner.isRunning():
            return
        self._scan_btn.setEnabled(False)
        self._stop_scan_btn.setEnabled(True)
        self._scan_progress.setValue(0)
        self._scan_progress.show()
        self._scan_status.setText("Scanning…")
        self._scanner = CameraScanner(
            rtsp_subnet=self._subnet_input.text().strip(),
            rtsp_user=self._rtsp_user.text().strip(),
            rtsp_pass=self._rtsp_pass.text().strip(),
        )
        self._scanner.found_local.connect(self._on_found_local)
        self._scanner.found_rtsp.connect(self._on_found_rtsp)
        self._scanner.scan_progress.connect(self._scan_progress.setValue)
        self._scanner.scan_done.connect(self._on_scan_done)
        self._scanner.start()

    def _abort_scan(self):
        if self._scanner: self._scanner.stop_scan()

    def _on_found_local(self, index: int, label: str):
        if str(index) in {str(c.source) for c in self._cameras}: return
        new_id = max((c.id for c in self._cameras), default=-1) + 1
        cfg = CameraConfig(id=new_id, name=f"Local Cam {index}", source=str(index), location="")
        self._cameras.append(cfg)
        self._add_cam_card(cfg, running=False)
        self._scan_status.setText(f"Found: {label}")

    def _on_found_rtsp(self, url: str, label: str):
        if url in {c.source for c in self._cameras}: return
        new_id = max((c.id for c in self._cameras), default=-1) + 1
        cfg = CameraConfig(id=new_id, name=f"IP Cam {new_id}", source=url, location="")
        self._cameras.append(cfg)
        self._add_cam_card(cfg, running=False)
        self._scan_status.setText(f"Found: {label}")

    def _on_scan_done(self):
        self._scan_btn.setEnabled(True)
        self._stop_scan_btn.setEnabled(False)
        self._scan_status.setText(f"Done — {len(self._cam_cards)} camera(s) listed.")
        self._scan_progress.hide()

    def _browse_photos(self):
        path = QFileDialog.getExistingDirectory(self, "Select Photos Directory")
        if path:
            self._photos_lbl.setText(path)
            self.photos_dir_changed.emit(path)
