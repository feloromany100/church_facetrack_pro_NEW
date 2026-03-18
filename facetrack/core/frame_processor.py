"""
facetrack/core/frame_processor.py

Stateful per-camera inference engine.
Extracted from src/processes/inference.py so that BOTH the PySide6 UI
(CameraWorker) and the headless mode (inference_process) share the same
logic without duplication.

Contract
--------
    processor = FrameProcessor(cam_id=0)
    processor.initialize()                 # loads models once; call from worker thread
    results = processor.process(frame_bgr) # call on every frame
    processor.cleanup()                    # release GPU / file handles

No queues, no Qt, no multiprocessing.  Pure frame-in / detections-out.
"""

import os
import sys
import time
import gc
import logging
import numpy as np
import faiss

from collections import defaultdict, deque
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# ── project root on path (removed once pyproject.toml / pip install -e . is used) ──

EMBEDDING_DIM = 512  # default; overridden via injected cfg where applicable
from facetrack.managers.temporal_consensus import TemporalConsensus
from facetrack.managers.identity_lock import IdentityLock
from facetrack.managers.unknown_manager import UnknownManager
from facetrack.managers.adaptive_threshold import AdaptiveThreshold
from facetrack.managers.identity_persistence import IdentityPersistence
from facetrack.managers.track_confidence import TrackConfidence
from facetrack.core.quality_assessment import assess_face_quality
from facetrack.core.database import load_database
from facetrack.infra.metrics import record_frame_processed
from facetrack.services.config_service import ConfigService

# scipy is optional — fall back to greedy matching if not installed
try:
    from scipy.optimize import linear_sum_assignment as _lsa
    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False

logger = logging.getLogger(__name__)

# Sentinel embedding used when no face is detected for a track
_NO_EMBEDDING = np.zeros(EMBEDDING_DIM, dtype=np.float32)
_NO_EMBEDDING[0] = 1.0

# ---------------------------------------------------------------------------
# Pure helper functions (no state)
# ---------------------------------------------------------------------------

def safe_embedding(emb: np.ndarray) -> np.ndarray:
    """Return L2-normalised embedding, or _NO_EMBEDDING if invalid."""
    if emb is None or not isinstance(emb, np.ndarray):
        return _NO_EMBEDDING.copy()
    emb = np.asarray(emb, dtype=np.float32).ravel()
    if emb.size != EMBEDDING_DIM or not np.isfinite(emb).all():
        return _NO_EMBEDDING.copy()
    norm = np.linalg.norm(emb)
    if norm <= 0:
        return _NO_EMBEDDING.copy()
    return (emb / norm).astype(np.float32)

def clip_bbox_to_frame(
    x1: int, y1: int, w: int, h: int, width: int, height: int,
    min_bbox_pixels: int = 8,
) -> Optional[List[int]]:
    """Clip bbox to frame bounds; return [l, t, w, h] or None if too small."""
    x1 = max(0, min(x1, width - 1))
    y1 = max(0, min(y1, height - 1))
    x2 = max(x1 + 1, min(x1 + w, width))
    y2 = max(y1 + 1, min(y1 + h, height))
    w_clip, h_clip = x2 - x1, y2 - y1
    if w_clip < min_bbox_pixels or h_clip < min_bbox_pixels:
        return None
    return [x1, y1, w_clip, h_clip]

def match_faces_to_persons(
    person_boxes: List[Tuple],
    face_detections: List[Dict],
    min_ioa: float = 0.3,
) -> Dict[int, int]:
    """
    Optimal 1-to-1 face → person box assignment (Hungarian if scipy available,
    greedy otherwise).  Returns {person_idx: face_idx}.
    """
    if not person_boxes or not face_detections:
        return {}

    pb = np.asarray(person_boxes, dtype=np.float64)
    fb = np.array([f["bbox"] for f in face_detections], dtype=np.float64)

    px1, py1, px2, py2 = pb[:, 0], pb[:, 1], pb[:, 2], pb[:, 3]
    fx1, fy1, fx2, fy2 = fb[:, 0], fb[:, 1], fb[:, 2], fb[:, 3]

    ix1 = np.maximum(px1[:, None], fx1[None, :])
    iy1 = np.maximum(py1[:, None], fy1[None, :])
    ix2 = np.minimum(px2[:, None], fx2[None, :])
    iy2 = np.minimum(py2[:, None], fy2[None, :])

    inter = np.maximum(0, ix2 - ix1) * np.maximum(0, iy2 - iy1)
    face_area = (fx2 - fx1) * (fy2 - fy1)
    ioa = np.where(face_area > 0, inter / face_area, 0.0)

    if _HAS_SCIPY:
        p_idx, f_idx = _lsa(-ioa)
    else:
        # greedy: sort by ioa descending
        order = np.dstack(np.unravel_index(np.argsort(-ioa, axis=None), ioa.shape))[0]
        used_p, used_f = set(), set()
        p_idx, f_idx = [], []
        for pi, fi in order:
            if pi not in used_p and fi not in used_f:
                p_idx.append(pi)
                f_idx.append(fi)
                used_p.add(pi)
                used_f.add(fi)
        p_idx = np.array(p_idx)
        f_idx = np.array(f_idx)

    return {
        int(pi): int(fi)
        for pi, fi in zip(p_idx, f_idx)
        if ioa[pi, fi] >= min_ioa
    }

def result_priority(r: Dict) -> Tuple:
    """Sort key: known identity > high confidence > high FAISS score."""
    is_known = 1 if not str(r.get("name", "")).startswith("Unknown") else 0
    return (is_known, float(r.get("confidence", 0.5)), float(r.get("score", 0.0)))

# ---------------------------------------------------------------------------
# FrameProcessor
# ---------------------------------------------------------------------------

class FrameProcessor:
    """
    All inference state for a single camera stream.

    Lifecycle
    ---------
    1. Construct:   FrameProcessor(cam_id, session_folder, unknowns_dir, csv_path)
    2. Initialize:  processor.initialize()   — loads YOLO, InsightFace, FAISS
    3. Per-frame:   results = processor.process(frame_bgr)
    4. Teardown:    processor.cleanup()
    """

    def __init__(
        self,
        cam_id: int,
        cfg=None,
        session_folder: str = "",
        unknowns_dir: str = "",
        csv_path: str = "",
    ):
        self.cam_id = cam_id
        if cfg is None:
            cfg = ConfigService().load()
        self.cfg = cfg
        self.session_folder = session_folder
        self.unknowns_dir = unknowns_dir
        self.csv_path = csv_path

        self._ready = False

        # Models (set in initialize())
        self._app = None          # InsightFace FaceAnalysis
        self._yolo = None         # YOLO ByteTrack tracker
        self._index = None        # FAISS index
        self._labels: List[str] = []

        # Per-track state managers
        self._consensus = TemporalConsensus(
            voting_window_size=int(getattr(self.cfg, "VOTING_WINDOW_SIZE", 10)),
            min_consensus_frames=int(getattr(self.cfg, "MIN_CONSENSUS_FRAMES", 1)),
        )
        self._id_lock = IdentityLock(
            lock_threshold=float(getattr(self.cfg, "IDENTITY_LOCK_THRESHOLD", 0.42)),
            consensus_frames=int(getattr(self.cfg, "LOCK_CONSENSUS_FRAMES", 3)),
            verify_sim=float(getattr(self.cfg, "LOCK_EMBEDDING_VERIFY", 0.38)),
        )
        self._adaptive_thresh = AdaptiveThreshold(
            base_similarity_threshold=float(getattr(self.cfg, "BASE_SIMILARITY_THRESHOLD", 0.42)),
            min_similarity_threshold=float(getattr(self.cfg, "MIN_SIMILARITY_THRESHOLD", 0.35)),
            max_similarity_threshold=float(getattr(self.cfg, "MAX_SIMILARITY_THRESHOLD", 0.60)),
        )
        self._id_persistence = IdentityPersistence(persistence_time=5.0)
        self._track_confidence = TrackConfidence()
        self._unknown_manager: Optional[UnknownManager] = None
        self._track_emb_history: Dict[str, Dict] = defaultdict(
            lambda: {"embeddings": deque(maxlen=10), "last_good": None}
        )

        # Session state (unknown handling only; attendance persistence lives outside)
        self._unknown_session_count = 0
        self._unknown_session_reset_time = time.time()

        # Performance counters
        self._frame_count = 0
        self._perf: Dict[str, deque] = {
            k: deque(maxlen=500)
            for k in ("yolo", "face", "recog", "total")
        }

        # Subscribe to live config updates (thread-safe inside ConfigService)
        if isinstance(self.cfg, ConfigService) or hasattr(self.cfg, "subscribe"):
            self._cfg_svc = self.cfg
        else:
            self._cfg_svc = ConfigService()
        self._cfg_svc.subscribe(self._on_config_updated)

    def _on_config_updated(self, new_cfg: Any):
        """Callback fired by ConfigService when UI sliders change."""
        self.cfg = new_cfg
        try:
            # Update temporal consensus
            if hasattr(self._consensus, "voting_window_size"):
                self._consensus.voting_window_size = int(getattr(new_cfg, "VOTING_WINDOW_SIZE", 10))
            if hasattr(self._consensus, "min_consensus_frames"):
                self._consensus.min_consensus_frames = int(getattr(new_cfg, "MIN_CONSENSUS_FRAMES", 1))

            # Update identity lock
            if hasattr(self._id_lock, "lock_threshold"):
                self._id_lock.lock_threshold = float(getattr(new_cfg, "IDENTITY_LOCK_THRESHOLD", 0.42))
            if hasattr(self._id_lock, "consensus_frames"):
                self._id_lock.consensus_frames = int(getattr(new_cfg, "LOCK_CONSENSUS_FRAMES", 3))
            if hasattr(self._id_lock, "verify_sim"):
                self._id_lock.verify_sim = float(getattr(new_cfg, "LOCK_EMBEDDING_VERIFY", 0.38))

            # Update adaptive threshold
            if hasattr(self._adaptive_thresh, "base_similarity_threshold"):
                self._adaptive_thresh.base_similarity_threshold = float(getattr(new_cfg, "BASE_SIMILARITY_THRESHOLD", 0.42))
            if hasattr(self._adaptive_thresh, "min_similarity_threshold"):
                self._adaptive_thresh.min_similarity_threshold = float(getattr(new_cfg, "MIN_SIMILARITY_THRESHOLD", 0.35))
            if hasattr(self._adaptive_thresh, "max_similarity_threshold"):
                self._adaptive_thresh.max_similarity_threshold = float(getattr(new_cfg, "MAX_SIMILARITY_THRESHOLD", 0.60))

            logger.info(f"[cam {self.cam_id}] Processed live config update.")
        except Exception as e:
            logger.error(f"[cam {self.cam_id}] Failed to apply live config update: {e}")

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    def initialize(self, shared_face_app=None, shared_faiss_index=None, shared_faiss_labels=None) -> bool:
        """
        Load models and open the CSV log.
        Safe to call from any thread; returns True on success.
        """
        logger.info(f"[cam {self.cam_id}] Initializing FrameProcessor...")

        # ── 1. InsightFace (use shared instance if provided) ────────────────
        if shared_face_app is not None:
            self._app = shared_face_app
            logger.info(f"[cam {self.cam_id}] Using pre-loaded InsightFace")
        else:
            self._app = self._init_insightface()
            if self._app is None:
                return False

        # ── 2. YOLO + ByteTrack (one tracker per camera = independent IDs) ──
        try:
            from ultralytics import YOLO
            self._yolo = YOLO(str(getattr(self.cfg, "PERSON_DETECTION_MODEL", "yolov8n.pt")))
            try:
                import torch
                if torch.cuda.is_available():
                    self._yolo.to("cuda")
            except Exception:
                pass
            logger.info(f"[cam {self.cam_id}] YOLO ready")
        except Exception as e:
            logger.error(f"[cam {self.cam_id}] YOLO failed: {e}")
            return False

        # ── 3. FAISS index (use shared instance if provided) ────────────────
        if shared_faiss_index is not None and shared_faiss_labels is not None:
            self._index = shared_faiss_index
            self._labels = shared_faiss_labels
            logger.info(f"[cam {self.cam_id}] Using pre-loaded FAISS index")
        else:
            try:
                self._index, self._labels, _ = load_database(self._app)
                logger.info(
                    f"[cam {self.cam_id}] FAISS ready — "
                    f"{len(self._labels)} enrolled faces"
                )
            except Exception as e:
                logger.warning(f"[cam {self.cam_id}] FAISS load failed: {e} — detection only")

        # ── 4. Unknown manager ──────────────────────────────────────────────
        if self.unknowns_dir:
            self._unknown_manager = UnknownManager(
                self.unknowns_dir, max_images=5, match_threshold=0.45
            )

        # ── 5. Warmup ───────────────────────────────────────────────────────
        try:
            warmup = np.zeros((640, 640, 3), dtype=np.uint8)
            self._yolo.track(
                warmup, classes=[0], conf=float(getattr(self.cfg, "PERSON_CONF_THRESHOLD", 0.35)),
                tracker="custom_bytetrack.yaml", persist=True, verbose=False,
            )
            self._app.get(warmup)
            logger.info(f"[cam {self.cam_id}] Warmup done")
        except Exception as e:
            logger.warning(f"[cam {self.cam_id}] Warmup non-fatal: {e}")

        self._ready = True
        return True

    def _init_insightface(self):
        """
        Initialise InsightFace via the shared model factory.
        Returns a ready FaceAnalysis app, or None on failure.
        """
        from facetrack.infra.model_factory import build_face_analysis_app
        return build_face_analysis_app(self.cfg, label=f"cam-{self.cam_id}")

    def cleanup(self):
        """Release GPU memory."""
        try:
            del self._app
        except Exception:
            pass
        try:
            del self._yolo
        except Exception:
            pass
        try:
            del self._index
        except Exception:
            pass
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
        self._ready = False
        logger.info(f"[cam {self.cam_id}] FrameProcessor cleaned up")

    # ------------------------------------------------------------------ #
    # Main entry point                                                     #
    # ------------------------------------------------------------------ #

    def process(self, frame_bgr: np.ndarray) -> List[Dict[str, Any]]:
        """
        Run full inference pipeline on one BGR frame.
        Returns a list of result dicts:
            {bbox, name, score, age, gender, track_id, quality, confidence}
        Returns [] if not yet initialized or on hard failure.
        """
        if not self._ready:
            return []

        t0 = time.time()
        self._frame_count += 1

        if self._frame_count % 100 == 0:
            self._log_perf()

        # Reset per-frame detection lists
        detections_data: List[Dict] = []

        # ── YOLO person detection + ByteTrack ──────────────────────────
        t1 = time.time()
        try:
            yolo_results = self._yolo.track(
                frame_bgr, classes=[0], conf=float(getattr(self.cfg, "PERSON_CONF_THRESHOLD", 0.35)),
                tracker="custom_bytetrack.yaml", persist=True, verbose=False,
            )
        except Exception as e:
            logger.error(f"[cam {self.cam_id}] YOLO error: {e}")
            return []
        self._perf["yolo"].append(time.time() - t1)

        # ── InsightFace detection ───────────────────────────────────────
        t2 = time.time()
        detected_faces = self._detect_faces(frame_bgr)
        self._perf["face"].append(time.time() - t2)

        # ── Match faces → person boxes ──────────────────────────────────
        h, w = frame_bgr.shape[:2]
        detections_data, matched_face_idx = self._match_and_build(
            yolo_results, detected_faces, w, h
        )

        # Fallback: faces YOLO missed (too close, partial occlusion)
        detections_data = self._add_fallback_faces(
            detections_data, detected_faces, matched_face_idx, w, h
        )

        # Remove fallback entries (track_id == -2) — ByteTrack handles tracking
        detections_data = [d for d in detections_data if d["track_id"] != -2]

        # ── Batch FAISS recognition ─────────────────────────────────────
        t3 = time.time()
        D_map, I_map = self._batch_faiss(detections_data)
        self._perf["recog"].append(time.time() - t3)

        # ── Per-track identity resolution ───────────────────────────────
        results, active_ids = self._resolve_identities(
            detections_data, D_map, I_map, frame_bgr
        )

        # ── Cleanup stale tracks ────────────────────────────────────────
        self._cleanup_stale_tracks(active_ids)

        # ── Periodic GC ────────────────────────────────────────────────
        if self._frame_count % 500 == 0:
            gc.collect(0)
        if self._frame_count % 1000 == 0:
            gc.collect()

        total = time.time() - t0
        self._perf["total"].append(total)
        record_frame_processed(self.cam_id, total)
        return sorted(results, key=result_priority, reverse=True)

    # ------------------------------------------------------------------ #
    # Internal pipeline steps                                              #
    # ------------------------------------------------------------------ #

    def _detect_faces(self, frame_bgr: np.ndarray) -> List[Dict]:
        """Run InsightFace, quality-filter, return list of face dicts."""
        h, w = frame_bgr.shape[:2]
        try:
            raw_faces = self._app.get(frame_bgr)
        except Exception as e:
            logger.warning(f"[cam {self.cam_id}] Face detection error: {e}")
            self._try_recover_insightface(e)
            return []

        faces = []
        for face in raw_faces:
            x1, y1, x2, y2 = face.bbox.astype(int)
            crop = frame_bgr[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
            if crop.size == 0:
                continue
            if face.det_score >= 0.9:
                is_good, quality = True, 0.9
            else:
                is_good, quality = assess_face_quality(
                    crop,
                    face,
                    face_min_size=int(getattr(self.cfg, "FACE_MIN_SIZE", 40)),
                    face_blur_threshold=float(getattr(self.cfg, "FACE_BLUR_THRESHOLD", 10.0)),
                    face_angle_threshold=float(getattr(self.cfg, "FACE_ANGLE_THRESHOLD", 60.0)),
                )
            if not is_good or face.det_score < 0.4:
                continue

            if hasattr(face, "sex"):
                gender = face.sex
            elif hasattr(face, "gender"):
                gender = "Male" if face.gender == 1 else "Female"
            else:
                gender = "Unknown"

            faces.append({
                "bbox": (x1, y1, x2, y2),
                "embedding": face.embedding,
                "age": int(face.age) if hasattr(face, "age") else 0,
                "gender": gender,
                "quality": quality,
                "det_score": face.det_score,
                "face_crop": crop,
            })
        return faces

    def _try_recover_insightface(self, error: Exception):
        """Attempt to switch to CPU if a hardware acceleration error occurs."""
        msg = str(error)
        if any(k in msg for k in ("CUDA failure", "CUDNN", "ONNXRuntimeError")):
            logger.warning("[cam %d] Hardware error — switching InsightFace to CPU", self.cam_id)
            try:
                from insightface.app import FaceAnalysis
                self._app = FaceAnalysis(name="buffalo_l",
                                         providers=["CPUExecutionProvider"])
                self._app.prepare(ctx_id=0, det_size=tuple(getattr(self.cfg, "DETECTION_SIZE", (640, 640))))
                logger.info("[cam %d] Switched to CPUExecutionProvider", self.cam_id)
            except Exception as e2:
                logger.error("[cam %d] CPU fallback failed: %s", self.cam_id, e2)
                self._ready = False

    def _match_and_build(
        self,
        yolo_results,
        detected_faces: List[Dict],
        w: int, h: int,
    ) -> Tuple[List[Dict], set]:
        """
        For each valid YOLO person box, find its matched face (if any) and
        build a flat detection_data list.  Returns (data_list, matched_face_indices).
        """
        detections_data: List[Dict] = []
        matched_face_idx: set = set()

        if not (len(yolo_results) > 0 and len(yolo_results[0].boxes) > 0):
            return detections_data, matched_face_idx

        boxes = yolo_results[0].boxes
        person_boxes = [
            tuple(box.xyxy[0].cpu().numpy().astype(int))
            for box in boxes
        ]

        # Filter sub-boxes (a head bbox fully inside a body bbox)
        valid = self._filter_subboxes(person_boxes)
        filtered_boxes = [b for i, b in enumerate(boxes) if i in valid]
        filtered_pb   = [b for i, b in enumerate(person_boxes) if i in valid]

        face_to_person = match_faces_to_persons(filtered_pb, detected_faces, min_ioa=0.3)

        for p_idx, box in enumerate(filtered_boxes):
            track_id = int(box.id[0]) if box.id is not None else -1
            if track_id == -1:
                continue

            px1, py1, px2, py2 = filtered_pb[p_idx]
            clipped = clip_bbox_to_frame(
                px1, py1, px2 - px1, py2 - py1, w, h,
                min_bbox_pixels=int(getattr(self.cfg, "MIN_BBOX_PIXELS", 8)))
            if clipped is None:
                continue
            l, t, bw, bh = clipped
            bbox_xyxy = (l, t, l + bw, t + bh)

            if p_idx in face_to_person:
                fi = face_to_person[p_idx]
                matched_face_idx.add(fi)
                fd = detected_faces[fi]
                detections_data.append({
                    "bbox": bbox_xyxy, "track_id": track_id,
                    "embedding": fd["embedding"], "age": fd["age"],
                    "gender": fd["gender"], "quality": fd["quality"],
                    "det_score": fd["det_score"], "face_crop": fd["face_crop"],
                })
            else:
                detections_data.append({
                    "bbox": bbox_xyxy, "track_id": track_id,
                    "embedding": None, "age": 0,
                    "gender": "Unknown", "quality": 0.0,
                    "det_score": 0.0, "face_crop": None,
                })

        return detections_data, matched_face_idx

    def _filter_subboxes(self, person_boxes: List[Tuple]) -> set:
        """
        Remove boxes that are heavily contained within a larger sibling box.

        Vectorized with numpy: O(n) array operations replace the O(n²) nested
        Python loop.  Result is identical to the original algorithm.
        """
        if len(person_boxes) < 2:
            return set(range(len(person_boxes)))

        pb = np.array(person_boxes, dtype=np.float32)       # (N, 4) — x1 y1 x2 y2
        areas = np.maximum(1.0, (pb[:, 2] - pb[:, 0]) * (pb[:, 3] - pb[:, 1]))

        # Intersection corners — broadcast (N, 1) vs (1, N) → (N, N)
        ix1 = np.maximum(pb[:, 0, None], pb[None, :, 0])
        iy1 = np.maximum(pb[:, 1, None], pb[None, :, 1])
        ix2 = np.minimum(pb[:, 2, None], pb[None, :, 2])
        iy2 = np.minimum(pb[:, 3, None], pb[None, :, 3])
        inter = np.maximum(0.0, ix2 - ix1) * np.maximum(0.0, iy2 - iy1)

        # ioa[i, j] = fraction of box-i's area covered by box-j's overlap
        ioa = inter / areas[:, None]

        # Box i is a sub-box of j when >80% of i lies inside j AND j is at least as large
        contained = (ioa > 0.8) & (areas[:, None] <= areas[None, :])
        np.fill_diagonal(contained, False)

        return {int(i) for i in np.where(~contained.any(axis=1))[0]}

    def _add_fallback_faces(
        self,
        detections_data: List[Dict],
        detected_faces: List[Dict],
        matched_idx: set,
        w: int, h: int,
    ) -> List[Dict]:
        """Add detections for faces YOLO missed (e.g. too close to lens)."""
        for fi, fd in enumerate(detected_faces):
            if fi in matched_idx:
                continue
            fx1, fy1, fx2, fy2 = fd["bbox"]
            fw, fh = fx2 - fx1, fy2 - fy1
            px1 = max(0, fx1 - int(fw * 0.1))
            px2 = min(w, fx2 + int(fw * 0.1))
            py1 = max(0, fy1 - int(fh * 0.2))
            py2 = min(h, fy2 + int(fh * 0.5))
            clipped = clip_bbox_to_frame(
                px1, py1, px2 - px1, py2 - py1, w, h,
                min_bbox_pixels=int(getattr(self.cfg, "MIN_BBOX_PIXELS", 8)))
            if clipped is None:
                continue
            l, t, bw, bh = clipped
            detections_data.append({
                "bbox": (l, t, l + bw, t + bh),
                "track_id": -2,   # sentinel — filtered out after matching
                "embedding": fd["embedding"], "age": fd["age"],
                "gender": fd["gender"], "quality": fd["quality"],
                "det_score": fd["det_score"], "face_crop": fd["face_crop"],
            })
        return detections_data

    def _batch_faiss(
        self, detections_data: List[Dict]
    ) -> Tuple[Dict[int, float], Dict[int, int]]:
        """Run a single batched FAISS search for all embeddings in the frame."""
        D_map: Dict[int, float] = {}
        I_map: Dict[int, int] = {}

        if self._index is None or not self._labels:
            return D_map, I_map

        valid = [
            (i, d["embedding"])
            for i, d in enumerate(detections_data)
            if d["embedding"] is not None
        ]
        if not valid:
            return D_map, I_map

        idxs, embs = zip(*valid)
        arr = np.array(embs, dtype=np.float32)
        faiss.normalize_L2(arr)
        sub_D, sub_I = self._index.search(arr, 1)

        for vi, orig_i in enumerate(idxs):
            D_map[orig_i] = float(sub_D[vi][0])
            I_map[orig_i] = int(sub_I[vi][0])

        return D_map, I_map

    def _resolve_identities(
        self,
        detections_data: List[Dict],
        D_map: Dict[int, float],
        I_map: Dict[int, int],
        frame_bgr: np.ndarray,
    ) -> Tuple[List[Dict], set]:
        """
        For each detection, run:
          adaptive threshold → temporal consensus → identity lock →
          identity persistence → unknown manager → CSV log

        Returns (results_list, active_track_id_set).
        """
        results: List[Dict] = []
        active_ids: set = set()
        now = time.time()

        # Reset unknown session counter on time-window boundary
        if now - self._unknown_session_reset_time > float(getattr(self.cfg, "UNKNOWN_SESSION_WINDOW", 300)):
            self._unknown_session_count = 0
            self._unknown_session_reset_time = now

        for i, det in enumerate(detections_data):
            track_id = str(det["track_id"])
            active_ids.add(track_id)

            name, score = "Unknown", 0.0
            age, gender = det["age"], det["gender"]
            current_emb = det.get("embedding")

            # ── embedding history + FAISS match ────────────────────────
            if current_emb is not None:
                hist = self._track_emb_history[track_id]
                hist["embeddings"].append(current_emb)
                hist["last_good"] = np.mean(list(hist["embeddings"]), axis=0)

                if i in D_map:
                    score = D_map[i]
                    track_hits = len(hist["embeddings"])
                    threshold = self._adaptive_thresh.get_threshold(
                        track_id, det["quality"], track_hits
                    )
                    if score >= threshold and I_map.get(i, -1) >= 0:
                        name = self._labels[I_map[i]]

                self._consensus.add_vote(
                    track_id, name, score, age, gender, det["quality"]
                )

            self._track_confidence.update(
                track_id,
                has_face=(current_emb is not None),
                face_quality=det["quality"],
                track_age=len(self._track_emb_history[track_id]["embeddings"]),
                iou_score=1.0,
            )

            # ── consensus ──────────────────────────────────────────────
            final_name, final_score, final_age, final_gender, _ = \
                self._consensus.get_consensus(track_id)

            # ── identity lock ───────────────────────────────────────────
            self._id_lock.try_lock(
                track_id, final_name, final_score,
                final_age, final_gender, embedding=current_emb
            )
            locked = self._id_lock.get_locked(track_id, current_embedding=current_emb)
            if locked:
                final_name, final_score, final_age, final_gender = locked

            # ── identity persistence ────────────────────────────────────
            if final_name != "Unknown":
                self._id_persistence.update(track_id, final_name, final_score, now)
            else:
                p_name, p_score = self._id_persistence.get_persistent_identity(
                    track_id, now
                )
                if p_name and p_score > float(getattr(self.cfg, "PERSISTENCE_RECOVERY_THRESHOLD", 0.35)):
                    final_name, final_score = p_name, p_score

            # ── unknown handling ────────────────────────────────────────
            final_name = self._handle_unknown(
                det, track_id, current_emb, final_name, now
            )

            # Persistence is handled outside FrameProcessor (service/data layers).

            confidence_score = self._track_confidence.get_confidence(track_id)
            _, _, _, _, avg_quality = self._consensus.get_consensus(track_id)

            results.append({
                "bbox": tuple(map(int, det["bbox"])),
                "name": final_name,
                "score": final_score,
                "age": final_age,
                "gender": final_gender,
                "track_id": track_id,
                "quality": avg_quality,
                "confidence": confidence_score,
            })

        return results, active_ids

    def _handle_unknown(
        self,
        det: Dict,
        track_id: str,
        current_emb: Optional[np.ndarray],
        final_name: str,
        now: float,
    ) -> str:
        """Save unknown face crops and assign a stable Unknown_N identity."""
        if not final_name.startswith("Unknown"):
            return final_name

        if self._unknown_manager is None:
            return final_name

        global_tid = (self.cam_id, track_id)
        face_crop = det.get("face_crop")

        if face_crop is not None and face_crop.size > 0:
            uid_prefix = os.path.basename(self.session_folder).split("_")[-1] \
                         if self.session_folder else "0"
            if self._unknown_session_count < int(getattr(self.cfg, "UNKNOWN_SESSION_LIMIT", 60)):
                uid = self._unknown_manager.process_unknown(
                    global_tid, current_emb, face_crop, uid_prefix=uid_prefix
                )
                if current_emb is not None:
                    self._unknown_manager.update_embedding(global_tid, current_emb)
                self._unknown_session_count += 1
                return f"Unknown_{uid}"
        elif global_tid in self._unknown_manager.track_to_unknown_id:
            return f"Unknown_{self._unknown_manager.track_to_unknown_id[global_tid]}"

        return final_name

    def _cleanup_stale_tracks(self, active_ids: set):
        """Remove state for tracks that are no longer in the frame."""
        all_ids = (
            set(self._consensus.track_votes.keys())
            | set(self._id_lock.locked.keys())
            | set(self._track_emb_history.keys())
            | set(self._id_persistence.track_identities.keys())
            | set(self._track_confidence.track_scores.keys())
        )
        for tid in all_ids - active_ids:
            self._consensus.clear_track(tid)
            self._id_lock.clear_track(tid)
            self._adaptive_thresh.clear_track(tid)
            self._id_persistence.clear_track(tid)
            self._track_confidence.clear_track(tid)
            self._track_emb_history.pop(tid, None)
            if self._unknown_manager:
                self._unknown_manager.clear_track((self.cam_id, tid))

    def _log_perf(self):
        if not self._perf["total"]:
            return
        avg = lambda k: np.mean(self._perf[k]) * 1000 if self._perf[k] else 0
        logger.info(
            "[cam %d] frame %d | total %.1fms | yolo %.1fms | "
            "face %.1fms | recog %.1fms",
            self.cam_id, self._frame_count,
            avg("total"), avg("yolo"), avg("face"), avg("recog"),
        )
