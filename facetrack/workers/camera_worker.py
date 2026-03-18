"""
facetrack/workers/camera_worker.py

QThread worker for the PySide6 UI.
Now delegates directly to the shared core classes:
  - facetrack.core.FrameCapture  — frame acquisition
  - facetrack.core.FrameProcessor — inference

Before this refactor, CameraWorker had its own capture loop AND called
RecognitionEngine which was a partial re-implementation of inference.py.
Both of those are gone — this file is now pure Qt plumbing.
"""

import logging
import numpy as np

from PySide6.QtCore import QObject, Signal, QThread
from PySide6.QtGui import QImage

from facetrack.core.video_capture import FrameCapture
from facetrack.core.frame_processor import FrameProcessor
from facetrack.models.camera import CameraConfig, CameraStatus

logger = logging.getLogger(__name__)

class CameraWorker(QObject):
    """
    Runs in a QThread.  Emits signals to the UI — never touches widgets directly.

    Signals
    -------
    frame_ready(cam_id, QImage)
    detection_ready(cam_id, list[dict])
    fps_updated(cam_id, float)
    status_changed(cam_id, str)
    error(cam_id, str)
    """

    frame_ready     = Signal(int, QImage)
    detection_ready = Signal(int, list)
    status_changed  = Signal(int, str)
    fps_updated     = Signal(int, float)
    error           = Signal(int, str)

    def __init__(
        self,
        config: CameraConfig,
        session_folder: str = "",
        unknowns_dir: str = "",
        csv_path: str = "",
        detect_every_n: int = 3,
        cfg=None,
        shared_faiss_index=None,
        shared_faiss_labels=None,
    ):
        super().__init__()
        self.config = config
        self._detect_every_n = detect_every_n
        self._active = False

        self._shared_faiss_index = shared_faiss_index
        self._shared_faiss_labels = shared_faiss_labels or []

        # Core objects — created in start_capture (worker thread)
        self._capture: FrameCapture = None
        self._processor: FrameProcessor = None

        # Session paths forwarded to FrameProcessor for CSV + unknown crops
        self._session_folder = session_folder
        self._unknowns_dir = unknowns_dir
        self._csv_path = csv_path
        if cfg is None:
            from facetrack.services.config_service import ConfigService
            cfg = ConfigService().load()
        self._cfg = cfg

    # ------------------------------------------------------------------ #
    # Lifecycle (called from QThread)                                      #
    # ------------------------------------------------------------------ #

    def start_capture(self):
        """Entry point called by thread.started signal."""
        self._active = True
        cam_id = self.config.id
        source = self.config.source

        self.status_changed.emit(cam_id, CameraStatus.CONNECTING.value)

        # Initialise the shared FrameProcessor
        self._processor = FrameProcessor(
            cam_id=cam_id,
            cfg=self._cfg,
            session_folder=self._session_folder,
            unknowns_dir=self._unknowns_dir,
            csv_path=self._csv_path,
        )
        ok = self._processor.initialize(
            shared_faiss_index=self._shared_faiss_index,
            shared_faiss_labels=self._shared_faiss_labels,
        )
        if not ok:
            msg = f"FrameProcessor init failed for cam {cam_id}"
            logger.error(msg)
            self.status_changed.emit(cam_id, CameraStatus.ERROR.value)
            self.error.emit(cam_id, msg)
            return

        # Initialise the shared FrameCapture
        self._capture = FrameCapture(source=source, target_fps=30.0)

        self.status_changed.emit(cam_id, CameraStatus.LIVE.value)
        self._run_loop()

    def stop(self):
        """Signal the capture loop to exit."""
        self._active = False
        if self._capture:
            self._capture.stop()

    # ------------------------------------------------------------------ #
    # Main loop                                                            #
    # ------------------------------------------------------------------ #

    def _run_loop(self):
        import time
        cam_id = self.config.id
        frame_count = 0
        fps_timer = time.time()
        fps_frames = 0

        try:
            for frame_bgr in self._capture.frames():
                if not self._active:
                    break

                # Emit frame for live display
                self._emit_frame(cam_id, frame_bgr)

                frame_count += 1
                fps_frames += 1

                # FPS counter — emit every second
                elapsed = time.time() - fps_timer
                if elapsed >= 1.0:
                    self.fps_updated.emit(cam_id, round(fps_frames / elapsed, 1))
                    fps_frames = 0
                    fps_timer = time.time()

                # Inference every N frames
                n = max(1, self._detect_every_n)
                if frame_count % n == 0:
                    detections = self._processor.process(frame_bgr)
                    self.detection_ready.emit(cam_id, detections)

                # Yield control to the Qt event loop so signals can be processed
                QThread.msleep(1)

        except Exception as e:
            logger.error("CameraWorker loop error cam %d: %s", cam_id, e)
            self.error.emit(cam_id, str(e))
        finally:
            if self._processor:
                self._processor.cleanup()
            self.status_changed.emit(cam_id, CameraStatus.OFFLINE.value)

    # ------------------------------------------------------------------ #
    # Frame conversion                                                     #
    # ------------------------------------------------------------------ #

    def _emit_frame(self, cam_id: int, frame_bgr: np.ndarray):
        """Convert BGR → QImage and emit without double-copying."""
        import cv2
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        h, w, ch = frame_rgb.shape
        # Pass strides[0] as bytes-per-line to handle non-contiguous arrays correctly.
        # Keep a reference to frame_rgb alive until after the copy so Qt doesn't
        # read freed memory.
        qimg = QImage(
            frame_rgb.data, w, h,
            frame_rgb.strides[0],
            QImage.Format.Format_RGB888,
        )
        self.frame_ready.emit(cam_id, qimg.copy())
