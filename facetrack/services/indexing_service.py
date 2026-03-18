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
    Emits only the FAISS index + labels — NOT the FaceAnalysis app.
    Each CameraWorker builds its own FaceAnalysis via model_factory so that
    concurrent .get() calls never share an ONNX session across threads.
    """
    finished = Signal(object, list)   # (faiss_index, labels)
    error = Signal(str)

    def __init__(self, cfg=None):
        super().__init__()
        self.cfg = cfg or ConfigService().load()

    def run(self):
        logger.info("Starting background FAISS indexing...")
        try:
            from facetrack.infra.model_factory import build_face_analysis_app
            # Build a temporary FaceAnalysis only to compute embeddings for the index.
            # This instance is NOT shared — it is released once indexing completes.
            face_app = build_face_analysis_app(self.cfg, label="indexer")
            if face_app is None:
                self.error.emit("Failed to initialize InsightFace: all providers exhausted")
                return

            index, labels, _ = load_database(face_app)
            # face_app goes out of scope here — GPU memory released.
            del face_app

            self.finished.emit(index, labels)

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
