"""
Unknown face manager with FAISS-accelerated re-identification and async image saving.
"""

import os
import cv2
import time
import logging
import numpy as np
import faiss
from datetime import datetime
from threading import Thread
from queue import Queue as ThreadQueue
from typing import Dict, List, Optional, Any

from facetrack.types import TrackKey

logger = logging.getLogger("UnknownManager")


class UnknownManager:
    """
    Manages unknown identity consolidation.

    Uses a FAISS flat index for O(log N) embedding search instead of O(N) linear
    scan, which matters when many unknowns accumulate over a long session.
    Image saving is non-blocking via a background thread queue.
    """

    def __init__(self, unknowns_dir: str, max_images: int = 5, match_threshold: float = 0.45):
        self.unknowns_dir = unknowns_dir
        self.max_images = max_images
        self.match_threshold = match_threshold

        # Active identity records (id → metadata)
        self.unknown_identities: List[Dict[str, Any]] = []
        # Keyed by (cam_id, track_id) tuples — see facetrack.types.TrackKey
        self.track_to_unknown_id: Dict[TrackKey, int] = {}
        self.next_unknown_id = 1

        # FAISS flat index for fast embedding search (inner product = cosine after L2-norm)
        self._faiss_dim = 512
        self._faiss_index: Optional[faiss.IndexFlatIP] = None  # built lazily
        self._faiss_id_map: List[int] = []   # faiss row → unknown_id
        self._faiss_dirty = False            # True when index needs rebuild

        self.last_save_time: Dict[TrackKey, float] = {}

        # Async image saving
        self.save_queue: ThreadQueue = ThreadQueue(maxsize=100)
        self._save_thread = Thread(target=self._save_worker, daemon=True)
        self._save_thread.start()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _save_worker(self):
        """Background thread: write face crops to disk without blocking inference."""
        while True:
            try:
                item = self.save_queue.get(timeout=1.0)
                if item is None:               # shutdown sentinel — exit cleanly
                    break
                img_path, face_crop = item
                cv2.imwrite(img_path, face_crop)
            except Exception as e:
                logger.debug(f"Save worker skipped frame: {e}")

    def _build_faiss_index(self):
        """Rebuild FAISS index from current identity embeddings."""
        if not self.unknown_identities:
            self._faiss_index = None
            self._faiss_id_map = []
            return

        embeddings = np.vstack([uid["embedding"] for uid in self.unknown_identities]).astype(np.float32)
        faiss.normalize_L2(embeddings)

        index = faiss.IndexFlatIP(self._faiss_dim)
        index.add(embeddings)

        self._faiss_index = index
        self._faiss_id_map = [uid["id"] for uid in self.unknown_identities]
        self._faiss_dirty = False

    def _search_similar(self, embedding: np.ndarray) -> tuple:
        """
        Search for the most similar known unknown identity.

        Returns: (best_unknown_id, best_sim) or (None, 0.0) if no match above threshold.
        """
        if self._faiss_dirty or self._faiss_index is None:
            self._build_faiss_index()

        if self._faiss_index is None or self._faiss_index.ntotal == 0:
            return None, 0.0

        query = embedding.astype(np.float32).reshape(1, -1).copy()
        faiss.normalize_L2(query)

        sims, indices = self._faiss_index.search(query, 1)
        sim = float(sims[0, 0])
        idx = int(indices[0, 0])

        if sim >= self.match_threshold and idx >= 0:
            return self._faiss_id_map[idx], sim

        return None, 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_unknown(self, track_id: TrackKey, current_embedding: Optional[np.ndarray],
                        face_crop: np.ndarray, uid_prefix: str) -> Optional[int]:
        """Process and optionally save an unknown face image (non-blocking)."""
        unknown_id = self.resolve_unknown(track_id, current_embedding)

        # Rate limiting per track FIRST (2 s between saves for the same track)
        now = time.time()
        if track_id in self.last_save_time and (now - self.last_save_time[track_id]) < 2.0:
            return unknown_id

        if not self.can_save_image(unknown_id):
            return unknown_id

        unknown_folder = os.path.join(self.unknowns_dir, f"Unknown_{unknown_id}")
        os.makedirs(unknown_folder, exist_ok=True)

        timestamp = datetime.now().strftime("%H-%M-%S-%f")
        img_path = os.path.join(unknown_folder, f"Unknown_{uid_prefix}_{timestamp}.jpg")

        try:
            self.save_queue.put_nowait((img_path, face_crop.copy()))
        except Exception:
            pass  # Queue full — skip this save

        self.last_save_time[track_id] = now
        return unknown_id

    def resolve_unknown(self, track_id: TrackKey,
                        current_embedding: Optional[np.ndarray]) -> int:
        """
        Assign (or re-use) an unknown identity ID for this track.

        If the track already has an ID, return it.
        If embedding is provided, search for an existing similar unknown via FAISS.
        If no embedding yet, create a placeholder entry so the track gets a stable ID
        even before a good face crop is captured; the embedding will be filled in later.
        """
        if track_id in self.track_to_unknown_id:
            return self.track_to_unknown_id[track_id]

        if current_embedding is not None:
            # Try to match against existing unknowns
            best_id, best_sim = self._search_similar(current_embedding)
            if best_id is not None:
                self.track_to_unknown_id[track_id] = best_id
                return best_id

        # Create a new unknown identity
        new_id = self.next_unknown_id
        self.next_unknown_id += 1

        emb_to_store = None
        if current_embedding is not None:
            emb_to_store = current_embedding.astype(np.float32).reshape(1, -1).copy()
            faiss.normalize_L2(emb_to_store)

        self.unknown_identities.append({
            "id": new_id,
            "embedding": emb_to_store,
            "img_count": 0,
        })
        self.track_to_unknown_id[track_id] = new_id
        self._faiss_dirty = True  # Rebuild index on next search

        os.makedirs(os.path.join(self.unknowns_dir, f"Unknown_{new_id}"), exist_ok=True)
        return new_id

    def update_embedding(self, track_id: TrackKey, embedding: np.ndarray):
        """
        Fill in the embedding for a track whose identity was created without one.
        Called whenever we get a valid embedding for a previously embedding-less unknown.
        """
        unknown_id = self.track_to_unknown_id.get(track_id)
        if unknown_id is None:
            return
        for identity in self.unknown_identities:
            if identity["id"] == unknown_id and identity["embedding"] is None:
                emb = embedding.astype(np.float32).reshape(1, -1).copy()
                faiss.normalize_L2(emb)
                identity["embedding"] = emb
                self._faiss_dirty = True
                break

    def can_save_image(self, unknown_id: int) -> bool:
        """Return True (and increment count) if this unknown hasn't hit its image cap."""
        for identity in self.unknown_identities:
            if identity["id"] == unknown_id:
                if identity["img_count"] < self.max_images:
                    identity["img_count"] += 1
                    return True
                return False
        # Unknown not yet registered (edge case) — allow one save
        return True

    def close(self) -> None:
        """
        Flush all pending face-crop saves and stop the background writer thread.
        Call this before process exit to avoid losing the last few saves.
        """
        try:
            self.save_queue.put_nowait(None)   # sentinel triggers worker break
        except Exception:
            pass
        self._save_thread.join(timeout=3.0)
        if self._save_thread.is_alive():
            logger.warning("UnknownManager save thread did not exit within the 3 s timeout")

    def clear_track(self, track_id: TrackKey):
        """Remove the track→unknown_id mapping (identity record is kept)."""
        self.track_to_unknown_id.pop(track_id, None)
        self.last_save_time.pop(track_id, None)