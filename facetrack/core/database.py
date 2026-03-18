"""
Face database management with FAISS
"""

import os
import json
import logging
import numpy as np
import faiss
import cv2
from typing import Tuple, Optional, Any, List

# Import config
import sys
from config import (
    PHOTOS_DIR, INDEX_FILE, LABELS_FILE, EMBEDDING_DIM,
    USE_GPU_FAISS, FAISS_GPU_ID
)

logger = logging.getLogger("Database")

# Database version marker
_DB_VERSION = "v4-heic-native-scale"
_DB_VERSION_FILE = "faces_index.version"

def _db_version_matches() -> bool:
    """Return True if the on-disk index was built with the current embedding pipeline."""
    if not os.path.exists(_DB_VERSION_FILE):
        return False
    try:
        with open(_DB_VERSION_FILE) as f:
            return f.read().strip() == _DB_VERSION
    except Exception:
        return False

def _write_db_version():
    with open(_DB_VERSION_FILE, "w") as f:
        f.write(_DB_VERSION)

def load_database(app) -> Tuple[Optional[Any], List[str], Optional[Any]]:
    """
    Load or create face recognition database with GPU acceleration.
    Returns: (index, labels, gpu_resources)
    """
    labels_file = LABELS_FILE if LABELS_FILE.endswith(".json") else \
        os.path.splitext(LABELS_FILE)[0] + ".json"

    use_gpu_faiss = USE_GPU_FAISS and faiss.get_num_gpus() > 0
    gpu_res = None

    # Invalidate index if version mismatch
    if not _db_version_matches() and os.path.exists(INDEX_FILE):
        logger.warning(
            "⚠️  Database version mismatch — rebuilding index to ensure "
            "embedding compatibility."
        )
        for stale in [INDEX_FILE, labels_file]:
            try:
                os.remove(stale)
            except FileNotFoundError:
                pass

    if os.path.exists(INDEX_FILE) and os.path.exists(labels_file):
        logger.info("📂 Loading existing database...")
        index = faiss.read_index(INDEX_FILE)

        if use_gpu_faiss:
            try:
                gpu_res = faiss.StandardGpuResources()
                index = faiss.index_cpu_to_gpu(gpu_res, FAISS_GPU_ID, index)
                logger.info("✅ Database moved to GPU")
            except Exception as e:
                logger.warning(f"GPU FAISS failed, using CPU: {e}")
                gpu_res = None
                use_gpu_faiss = False

        with open(labels_file, "r", encoding="utf-8") as f:
            labels = json.load(f)

        logger.info(f"✅ Loaded {len(labels)} faces from database")
        return index, labels, gpu_res

    logger.info("📂 Creating new database from photos folder...")
    embeddings: List[np.ndarray] = []
    labels: List[str] = []

    if not os.path.exists(PHOTOS_DIR):
        os.makedirs(PHOTOS_DIR)
        logger.warning(f"Created '{PHOTOS_DIR}' folder. Please add face images.")
        return None, [], None

    # Initialize CPU provider for offline processing
    try:
        from insightface.app import FaceAnalysis
        enroll_app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        enroll_app.prepare(ctx_id=-1, det_size=(640, 640))
    except Exception as e:
        logger.warning(f"Failed to load standalone FaceAnalysis: {e}")
        enroll_app = app

    # Pre-process HEIC files
    heic_files = [f for f in os.listdir(PHOTOS_DIR) if f.lower().endswith((".heic", ".heif"))]
    if heic_files:
        logger.info(f"Found {len(heic_files)} HEIC files. Converting to JPG...")
        try:
            import pillow_heif
            from PIL import Image
            pillow_heif.register_heif_opener()
            
            for heic_file in heic_files:
                heic_path = os.path.join(PHOTOS_DIR, heic_file)
                base_name = os.path.splitext(heic_file)[0]
                jpg_path = os.path.join(PHOTOS_DIR, f"{base_name}.jpg")
                
                try:
                    img = Image.open(heic_path)
                    img.convert('RGB').save(jpg_path, "JPEG")
                    os.remove(heic_path)
                    logger.info(f"Converted {heic_file} to {base_name}.jpg")
                except Exception as e:
                    logger.warning(f"Failed to convert {heic_file}: {e}")
        except ImportError:
            logger.warning("pillow-heif not installed. Run 'pip install pillow-heif'")

    # Process images
    for img_name in os.listdir(PHOTOS_DIR):
        if not img_name.lower().endswith((".jpg", ".png", ".jpeg")):
            continue

        img_path = os.path.join(PHOTOS_DIR, img_name)
        img = cv2.imread(img_path)

        if img is None:
            logger.warning(f"Could not read image: {img_name}")
            continue

        faces = enroll_app.get(img)
        if faces:
            face = faces[0]
            embeddings.append(face.embedding)
            name = os.path.splitext(img_name)[0]
            labels.append(name)
            logger.info(f"Enrolled face: {name}")
        else:
            logger.warning(f"No faces detected in: {img_name}")

    if not embeddings:
        logger.warning("No faces found in photos folder")
        return None, [], None

    emb_array = np.vstack(embeddings).astype(np.float32)
    faiss.normalize_L2(emb_array)

    cpu_index = faiss.IndexFlatIP(EMBEDDING_DIM)
    cpu_index.add(emb_array)

    if use_gpu_faiss:
        try:
            gpu_res = faiss.StandardGpuResources()
            index = faiss.index_cpu_to_gpu(gpu_res, FAISS_GPU_ID, cpu_index)
            logger.info("✅ Database created on GPU")
        except Exception as e:
            logger.warning(f"GPU FAISS failed, using CPU: {e}")
            gpu_res = None
            index = cpu_index
    else:
        index = cpu_index

    # Save database
    faiss.write_index(cpu_index, INDEX_FILE)
    with open(labels_file, "w", encoding="utf-8") as f:
        json.dump(labels, f, ensure_ascii=False, indent=2)
    _write_db_version()

    logger.info(f"✅ Created database with {len(labels)} faces")
    return index, labels, gpu_res
