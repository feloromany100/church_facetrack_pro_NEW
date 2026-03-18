"""
MainWindow — shell that owns the sidebar, top bar, page router,
workers, and wires all signals together.
Cameras are loaded from config.py (CAMERA_SOURCES) when available.
"""
import os
import sys
import logging

from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget
from PySide6.QtCore import Qt, QThread, Slot

from facetrack.ui.theme import C, Pane
from facetrack.ui.components.sidebar import Sidebar
from facetrack.ui.components.top_bar import TopBar
from facetrack.ui.components.toast import show_toast
from facetrack.ui.pages.dashboard import DashboardPage
from facetrack.ui.pages.cameras import CamerasPage
from facetrack.ui.pages.logs import LogsPage
from facetrack.ui.pages.insights import InsightsPage
from facetrack.ui.pages.alerts import AlertsPage
from facetrack.ui.pages.settings import SettingsPage

from facetrack.storage.attendance_store import AttendanceStore
from facetrack.core.alert_manager import AlertManager
from facetrack.models.camera import CameraConfig, CameraState, CameraStatus
from facetrack.models.alert import AlertSeverity
from facetrack.workers.camera_worker import CameraWorker
from facetrack.workers.stats_worker import StatsWorker
from facetrack.services.indexing_service import IndexingService

logger = logging.getLogger("MainWindow")

# Ensure project root on path for v5 config

PAGE_TITLES = {
    "dashboard": "Dashboard",
    "cameras":   "Live Cameras",
    "logs":      "Attendance Logs",
    "insights":  "Ministry Insights",
    "alerts":    "Smart Alerts",
    "settings":  "Settings",
}

def _load_cameras_from_config() -> list:
    """
    Load camera sources from v5 config.py (CAMERA_SOURCES).
    Falls back to a single webcam (index 0) if config is unavailable.
    """
    try:
        from facetrack.services.config_service import ConfigService
        CAMERA_SOURCES = ConfigService().load().CAMERA_SOURCES
        cameras = []
        for idx, src in enumerate(CAMERA_SOURCES[:4]):
            name = f"Camera {idx + 1}"
            location = "Main Hall" if idx == 0 else f"Location {idx + 1}"
            cameras.append(CameraConfig(
                id=idx,
                name=name,
                source=str(src) if isinstance(src, int) else src,
                location=location,
            ))
        logger.info(f"Loaded {len(cameras)} camera(s) from config.py")
        return cameras
    except Exception as e:
        logger.warning(f"Could not load config.py cameras: {e}. Using default webcam.")
        return [CameraConfig(id=0, name="Main Hall", source="0", location="Main Hall")]

class MainWindow(QMainWindow):
    def __init__(self, demo_mode: bool = False):
        super().__init__()
        self.setWindowTitle("Church FaceTrack Pro")
        self.setMinimumSize(1200, 750)
        self.resize(1440, 860)

        # ── Core services ─────────────────────────────────────────────────────
        self._store   = AttendanceStore(seed_dummy=demo_mode)
        self._alerts  = AlertManager()
        from facetrack.services.config_service import ConfigService
        self._cfg = ConfigService().load()
        # FrameProcessor is instantiated per-camera inside CameraWorker.
        # MainWindow no longer holds a shared engine — each worker owns its own.

        # Per-camera unknown alert cooldown: cam_id → last alert timestamp
        self._unknown_alert_last: dict = {}
        self._unknown_alert_cooldown: float = 30.0  # seconds between unknown alerts per camera

        # Background loaded models
        self._shared_face_app = None
        self._shared_faiss_index = None
        self._shared_faiss_labels = []
        self._models_ready = False
        self._pending_cameras: list[CameraConfig] = []

        # ── Workers ───────────────────────────────────────────────────────────
        self._cam_workers: dict[int, tuple] = {}   # id → (worker, thread)
        self._stats_worker = StatsWorker()
        self._stats_worker.stats_update.connect(self._on_stats)
        self._stats_worker.start()

        # ── Build UI ──────────────────────────────────────────────────────────
        self._default_cameras = _load_cameras_from_config()
        self._build_ui()

        # ── Wire alert manager → UI ───────────────────────────────────────────
        self._alerts.subscribe(self._on_new_alert)

        # ── Start Async Indexing ──────────────────────────────────────────────
        self._indexer = IndexingService()
        self._indexer.start_indexing(self._on_indexing_finished, self._on_indexing_error)

        # ── Queue cameras to start ────────────────────────────────────────────
        for cfg in self._default_cameras:
            self._start_camera(cfg)

    # ── UI Construction ───────────────────────────────────────────────────────
    def _build_ui(self):
        root = Pane()
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self._top_bar = TopBar()
        self._top_bar.alerts_clicked.connect(lambda: self._navigate("alerts"))
        root_layout.addWidget(self._top_bar)

        body = Pane()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self._sidebar = Sidebar()
        self._sidebar.page_selected.connect(self._navigate)
        body_layout.addWidget(self._sidebar)

        self._stack = QStackedWidget()
        body_layout.addWidget(self._stack)
        root_layout.addWidget(body)

        # Instantiate pages
        self._pages: dict[str, QWidget] = {}
        self._dashboard     = DashboardPage(self._store)
        self._cameras_page  = CamerasPage()
        self._logs_page     = LogsPage(self._store)
        self._insights_page = InsightsPage(self._store)
        self._alerts_page   = AlertsPage(self._alerts)
        self._settings_page = SettingsPage(self._default_cameras)

        for pid, page in [
            ("dashboard", self._dashboard),
            ("cameras",   self._cameras_page),
            ("logs",      self._logs_page),
            ("insights",  self._insights_page),
            ("alerts",    self._alerts_page),
            ("settings",  self._settings_page),
        ]:
            self._stack.addWidget(page)
            self._pages[pid] = page

        # Settings → camera lifecycle
        self._settings_page.camera_added.connect(self._start_camera)
        self._settings_page.camera_launch.connect(self._start_camera)
        self._settings_page.camera_stop.connect(self._stop_camera)
        self._settings_page.camera_removed.connect(self._stop_camera)

        # Settings → store (the only runtime target that still exists here)
        # NOTE: FrameProcessor is owned per-camera inside each CameraWorker.
        # Per-processor config changes require a worker restart; that is a
        # future enhancement.  For now we wire only what we can act on.
        sp = self._settings_page
        sp.cooldown_changed.connect(self._store.set_cooldown)

        self._navigate("dashboard")

    # ── Navigation ────────────────────────────────────────────────────────────
    @Slot(str)
    def _navigate(self, page_id: str):
        page = self._pages.get(page_id)
        if page:
            self._stack.setCurrentWidget(page)
            self._top_bar.set_title(PAGE_TITLES.get(page_id, page_id.title()))

    # ── Camera lifecycle ──────────────────────────────────────────────────────
    def _start_camera(self, cfg: CameraConfig):
        if cfg.id in self._cam_workers:
            return
            
        # Defer launch until models are fully loaded in background
        if not self._models_ready:
            self._pending_cameras.append(cfg)
            state = CameraState(config=cfg)
            self._cameras_page.add_camera(state)
            self._cameras_page.update_status(cfg.id, "Wait Init...")
            return
            
        state = CameraState(config=cfg)
        self._cameras_page.add_camera(state)
        count = len(self._cam_workers) + 1
        self._dashboard.set_camera_count(count)
        self._top_bar.set_camera_count(count)

        # Create a dedicated session for this camera so each worker writes
        # to its own CSV and unknowns folder — no cross-thread file sharing.
        try:
            from facetrack.storage.session_manager import create_session
            session_folder, unknowns_dir, csv_path = create_session(self._cfg)
        except Exception as e:
            logger.warning("Could not create session for cam %d: %s", cfg.id, e)
            session_folder = unknowns_dir = csv_path = ""

        worker = CameraWorker(
            cfg,
            session_folder=session_folder,
            unknowns_dir=unknowns_dir,
            csv_path=csv_path,
            cfg=self._cfg,
            shared_face_app=self._shared_face_app,
            shared_faiss_index=self._shared_faiss_index,
            shared_faiss_labels=self._shared_faiss_labels,
        )
        thread = QThread(self)

        worker.moveToThread(thread)

        worker.frame_ready.connect(self._cameras_page.update_frame)
        worker.detection_ready.connect(self._on_detections)
        worker.fps_updated.connect(self._cameras_page.update_fps)
        worker.status_changed.connect(self._cameras_page.update_status)
        worker.error.connect(self._on_cam_error)

        # Delete worker object once thread finishes
        thread.finished.connect(worker.deleteLater)

        thread.started.connect(worker.start_capture)
        thread.start()

        self._cam_workers[cfg.id] = (worker, thread)
        self._settings_page.notify_camera_started(cfg.id)

    def _stop_camera(self, cam_id: int):
        pair = self._cam_workers.pop(cam_id, None)
        if pair:
            worker, thread = pair
            worker.stop()          # sets _active = False in the worker loop
            thread.quit()          # ask event loop to exit (no-op for run() loops, but safe)
            thread.wait(3000)      # wait up to 3s for the loop to notice _active=False
        count = len(self._cam_workers)
        self._top_bar.set_camera_count(count)
        self._dashboard.set_camera_count(count)
        self._settings_page.notify_camera_stopped(cam_id)

    # ── Slots ─────────────────────────────────────────────────────────────────
    @Slot(object, list, object)
    def _on_indexing_finished(self, index, labels, face_app):
        logger.info("Background indexing finished. Releasing pending cameras.")
        self._shared_faiss_index = index
        self._shared_faiss_labels = labels
        self._shared_face_app = face_app
        self._models_ready = True
        
        # Start any cameras that users tried to launch while indexing
        for cfg in self._pending_cameras:
            self._start_camera(cfg)
        self._pending_cameras.clear()

    @Slot(str)
    def _on_indexing_error(self, err_msg):
        logger.error(f"Background indexing failed: {err_msg}")
        show_toast("Init Error", f"FAISS DB Failed to load: {err_msg}", AlertSeverity.DANGER, self)
        # Even if indexing fails, let cameras start (YOLO will still work)
        self._models_ready = True
        for cfg in self._pending_cameras:
            self._start_camera(cfg)
        self._pending_cameras.clear()

    @Slot(dict)
    def _on_stats(self, stats: dict):
        self._top_bar.update_stats(stats)

    @Slot(int, list)
    def _on_detections(self, cam_id: int, detections: list):
        """
        Receives list[dict] from CameraWorker (FrameProcessor output).
        Each dict has keys: bbox, name, score, age, gender, track_id,
                            quality, confidence.
        Attendance logging is delegated entirely to AttendanceStore.log()
        which owns the cooldown gate — no duplicate gate here.
        """
        import time
        self._cameras_page.update_detections(cam_id, detections)
        cam_name = (self._cam_workers[cam_id][0].config.name
                    if cam_id in self._cam_workers else f"Cam {cam_id}")

        has_unknown = False
        for det in detections:
            name        = det.get("name", "Unknown")
            score       = det.get("score", 0.0)
            confidence  = det.get("confidence", 0.0)
            is_unknown  = name.startswith("Unknown")

            # Determine group from name_to_group mapping if available
            from facetrack.models.person import PersonGroup
            group = PersonGroup.UNKNOWN if is_unknown else PersonGroup.VISITOR

            self._store.log(
                person_name=name,
                person_id=None,
                camera_id=cam_id,
                camera_name=cam_name,
                confidence=confidence,
                group=group,
                is_unknown=is_unknown,
            )

            if is_unknown:
                has_unknown = True

        # Fire at most one unknown alert per camera per cooldown window
        if has_unknown:
            now = time.time()
            last = self._unknown_alert_last.get(cam_id, 0.0)
            if now - last >= self._unknown_alert_cooldown:
                self._unknown_alert_last[cam_id] = now
                self._alerts.push(
                    title="Unknown Face Detected",
                    message=f"Unrecognized person on {cam_name}",
                    severity=AlertSeverity.WARNING,
                    camera_id=cam_id,
                    camera_name=cam_name,
                )

    def _on_new_alert(self, alert):
        self._alerts_page.push_alert(alert)
        self._top_bar.set_alert_count(self._alerts.get_unread_count())
        self._sidebar.set_alert_badge(self._alerts.get_unread_count())
        show_toast(alert.title, alert.message, alert.severity, self)

    @Slot(int, str)
    def _on_cam_error(self, cam_id: int, msg: str):
        show_toast(f"Camera {cam_id} Error", msg, AlertSeverity.DANGER, self)

    # ── Cleanup ───────────────────────────────────────────────────────────────
    def closeEvent(self, event):
        # Stop stats worker (has its own quit+wait)
        self._stats_worker.stop()

        # Stop all camera workers
        for cam_id in list(self._cam_workers.keys()):
            self._stop_camera(cam_id)

        self._store.close()
        super().closeEvent(event)
