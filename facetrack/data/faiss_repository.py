from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

import cv2
import faiss
import numpy as np

from facetrack.infra.errors import ErrorCode

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FaissArtifacts:
    index: Optional[Any]
    labels: List[str]
    gpu_resources: Optional[Any]


class FaissRepository:
    """
    Owns all filesystem interaction for the FAISS index + labels.
    """

    _DB_VERSION = "v4-heic-native-scale"
    _DB_VERSION_FILE = "faces_index.version"

    def __init__(self, cfg):
        self._cfg = cfg

    def _labels_file(self) -> str:
        labels_file = self._cfg.LABELS_FILE
        return labels_file if labels_file.endswith(".json") else os.path.splitext(labels_file)[0] + ".json"

    def _db_version_matches(self) -> bool:
        if not os.path.exists(self._DB_VERSION_FILE):
            return False
        try:
            with open(self._DB_VERSION_FILE, "r", encoding="utf-8") as f:
                return f.read().strip() == self._DB_VERSION
        except Exception:
            return False

    def _write_db_version(self) -> None:
        with open(self._DB_VERSION_FILE, "w", encoding="utf-8") as f:
            f.write(self._DB_VERSION)

    def load(self, app) -> FaissArtifacts:
        labels_file = self._labels_file()
        index_file = self._cfg.INDEX_FILE

        use_gpu_faiss = bool(getattr(self._cfg, "USE_GPU_FAISS", False)) and faiss.get_num_gpus() > 0
        gpu_res = None

        # Invalidate index if version mismatch
        if not self._db_version_matches() and os.path.exists(index_file):
            logger.warning(
                "Database version mismatch; rebuilding index for embedding compatibility",
                extra={"error_code": ErrorCode.FAISS_REBUILD_FAIL},
            )
            for stale in [index_file, labels_file]:
                try:
                    os.remove(stale)
                except FileNotFoundError:
                    pass

        if os.path.exists(index_file) and os.path.exists(labels_file):
            index = faiss.read_index(index_file)
            if use_gpu_faiss:
                try:
                    gpu_res = faiss.StandardGpuResources()
                    index = faiss.index_cpu_to_gpu(gpu_res, int(getattr(self._cfg, "FAISS_GPU_ID", 0)), index)
                except Exception as e:
                    logger.warning("GPU FAISS failed; using CPU (%s)", e, extra={"error_code": ErrorCode.FAISS_LOAD_FAIL})
                    gpu_res = None
            with open(labels_file, "r", encoding="utf-8") as f:
                labels = json.load(f)
            return FaissArtifacts(index=index, labels=labels, gpu_resources=gpu_res)

        return self.rebuild(app)

    def rebuild(self, app) -> FaissArtifacts:
        photos_dir = self._cfg.PHOTOS_DIR
        os.makedirs(photos_dir, exist_ok=True)

        embeddings: List[np.ndarray] = []
        labels: List[str] = []

        # Initialize CPU provider for offline processing if available
        try:
            from insightface.app import FaceAnalysis
            enroll_app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
            enroll_app.prepare(ctx_id=-1, det_size=(640, 640))
        except Exception:
            enroll_app = app

        # HEIC conversion (optional dependency)
        heic_files = [f for f in os.listdir(photos_dir) if f.lower().endswith((".heic", ".heif"))]
        if heic_files:
            try:
                import pillow_heif
                from PIL import Image
                pillow_heif.register_heif_opener()
                for heic_file in heic_files:
                    heic_path = os.path.join(photos_dir, heic_file)
                    base_name = os.path.splitext(heic_file)[0]
                    jpg_path = os.path.join(photos_dir, f"{base_name}.jpg")
                    try:
                        img = Image.open(heic_path)
                        img.convert("RGB").save(jpg_path, "JPEG")
                        os.remove(heic_path)
                    except Exception:
                        pass
            except ImportError:
                logger.warning("pillow-heif not installed; cannot convert HEIC files")

        for img_name in os.listdir(photos_dir):
            if not img_name.lower().endswith((".jpg", ".png", ".jpeg")):
                continue
            img_path = os.path.join(photos_dir, img_name)
            img = cv2.imread(img_path)
            if img is None:
                continue
            faces = enroll_app.get(img)
            if not faces:
                continue
            face = faces[0]
            embeddings.append(face.embedding)
            labels.append(os.path.splitext(img_name)[0])

        if not embeddings:
            return FaissArtifacts(index=None, labels=[], gpu_resources=None)

        emb_array = np.vstack(embeddings).astype(np.float32)
        faiss.normalize_L2(emb_array)

        cpu_index = faiss.IndexFlatIP(int(self._cfg.EMBEDDING_DIM))
        cpu_index.add(emb_array)

        labels_file = self._labels_file()
        faiss.write_index(cpu_index, self._cfg.INDEX_FILE)
        with open(labels_file, "w", encoding="utf-8") as f:
            json.dump(labels, f, ensure_ascii=False, indent=2)
        self._write_db_version()

        # Optional GPU move
        use_gpu_faiss = bool(getattr(self._cfg, "USE_GPU_FAISS", False)) and faiss.get_num_gpus() > 0
        if use_gpu_faiss:
            try:
                gpu_res = faiss.StandardGpuResources()
                gpu_index = faiss.index_cpu_to_gpu(gpu_res, int(getattr(self._cfg, "FAISS_GPU_ID", 0)), cpu_index)
                return FaissArtifacts(index=gpu_index, labels=labels, gpu_resources=gpu_res)
            except Exception:
                pass

        return FaissArtifacts(index=cpu_index, labels=labels, gpu_resources=None)

    def search(self, index: Any, embeddings: np.ndarray, k: int = 1) -> Tuple[np.ndarray, np.ndarray]:
        if index is None:
            raise RuntimeError(f"{ErrorCode.FAISS_LOAD_FAIL}: index not loaded")
        arr = np.asarray(embeddings, dtype=np.float32)
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        faiss.normalize_L2(arr)
        return index.search(arr, k)

