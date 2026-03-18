"""
Service for loading/building the FAISS database asynchronously.
Prevents the PySide6 UI from blocking during heavy I/O operations.
"""
import logging
from PySide6.QtCore import QObject, Signal, QThread

from facetrack.core.database import load_database
from facetrack.services.config_service import ConfigService

logger = logging.getLogger("IndexingService")

class IndexingWorker(QObject):
    """
    Background worker that executes load_database().
    """
    finished = Signal(object, list, dict)  # (index, labels, face_app)
    error = Signal(str)

    def __init__(self, cfg=None):
        super().__init__()
        self.cfg = cfg or ConfigService().load()

    def run(self):
        logger.info("Starting background FAISS indexing...")
        try:
            # 1. Initialize FaceAnalysis provider exactly as FrameProcessor does
            try:
                import onnxruntime as ort
                available = ort.get_available_providers()
                configured = list(getattr(self.cfg, "EXECUTION_PROVIDERS", ["CPUExecutionProvider"]))
                providers = [p for p in configured if p in available] or ["CPUExecutionProvider"]
            except Exception:
                providers = ["CPUExecutionProvider"]

            try:
                from insightface.app import FaceAnalysis
                face_app = FaceAnalysis(name="buffalo_l", providers=providers)
                face_app.prepare(ctx_id=0, det_size=tuple(getattr(self.cfg, "DETECTION_SIZE", (640, 640))))
            except Exception as e:
                self.error.emit(f"Failed to initialize InsightFace for indexing: {str(e)}")
                return

            # 2. Run the heavy blocking database load
            index, labels, _ = load_database(face_app)
            
            # Emit success
            self.finished.emit(index, labels, face_app)

        except Exception as e:
            logger.exception("Background indexing failed")
            self.error.emit(str(e))


class IndexingService:
    """Manager to spawn and connect the IndexingWorker."""
    def __init__(self):
        self._thread = None
        self._worker = None

    def start_indexing(self, on_finished_callback, on_error_callback):
        self._thread = QThread()
        self._worker = IndexingWorker()
        
        self._worker.moveToThread(self._thread)
        
        self._worker.finished.connect(on_finished_callback)
        self._worker.error.connect(on_error_callback)
        
        # Cleanup
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.error.connect(self._thread.quit)
        self._worker.error.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        
        self._thread.started.connect(self._worker.run)
        self._thread.start()
