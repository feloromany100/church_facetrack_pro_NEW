"""
Identity lock manager to prevent identity swaps
"""

import numpy as np
import faiss
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

class IdentityLock:
    """Lock identity only when very confident + consistent."""

    def __init__(
        self,
        lock_threshold: float = 0.42,
        consensus_frames: int = 3,
        verify_sim: float = 0.38,
    ):
        self.lock_threshold = lock_threshold
        self.consensus_frames = consensus_frames
        self.verify_sim = verify_sim
        self.locked: Dict[int, Tuple[str, float, int, str, np.ndarray]] = {}
        self.lock_candidates: Dict[int, List[Tuple[str, float]]] = defaultdict(list)

    def try_lock(self, track_id: int, name: str, score: float,
                 age: int, gender: str,
                 embedding: Optional[np.ndarray] = None) -> bool:
        """Lock only after multiple high-confidence recognitions."""
        if name == "Unknown" or score < self.lock_threshold:
            self.lock_candidates[track_id] = []
            return False

        cand = self.lock_candidates[track_id]
        cand.append((name, score))
        if len(cand) > self.consensus_frames:
            cand.pop(0)

        if len(cand) >= self.consensus_frames and all(c[0] == name for c in cand):
            emb = None
            if embedding is not None:
                emb = embedding.astype(np.float32).reshape(1, -1).copy()
                faiss.normalize_L2(emb)
            self.locked[track_id] = (name, score, age, gender, emb)
            self.lock_candidates[track_id] = []
            return True
        return False

    def get_locked(self, track_id: int,
                   current_embedding: Optional[np.ndarray] = None
                   ) -> Optional[Tuple[str, float, int, str]]:
        """Return locked identity, verifying current face matches stored embedding."""
        val = self.locked.get(track_id)
        if val is None:
            return None
        name, score, age, gender, stored_emb = val
        if stored_emb is not None and current_embedding is not None:
            cur = current_embedding.astype(np.float32).reshape(1, -1)
            faiss.normalize_L2(cur)
            sim = float(np.dot(stored_emb, cur.T)[0, 0])
            if sim < self.verify_sim:
                self.locked.pop(track_id, None)
                return None
        return name, score, age, gender

    def is_locked(self, track_id: int) -> bool:
        return track_id in self.locked

    def clear_track(self, track_id: int):
        self.locked.pop(track_id, None)
        self.lock_candidates.pop(track_id, None)
