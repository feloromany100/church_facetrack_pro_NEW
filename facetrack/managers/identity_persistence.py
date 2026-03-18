"""
Identity persistence manager — maintains recognized identity when face is temporarily lost.
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
import time

from facetrack.types import TrackId


class IdentityPersistence:
    """Maintains identity for a track even when the face is temporarily not detected."""

    def __init__(self, persistence_time: float = 5.0):
        self.persistence_time = persistence_time
        # Dict[TrackId, List[Tuple[name, score, timestamp]]]
        self.track_identities: Dict[TrackId, List[Tuple[str, float, float]]] = {}

    def update(self, track_id: TrackId, name: str, score: float, current_time: float):
        """Record a confirmed identity for this track at the given frame."""
        if track_id not in self.track_identities:
            self.track_identities[track_id] = []

        self.track_identities[track_id].append((name, score, current_time))

        # Prune entries older than persistence window
        cutoff = current_time - self.persistence_time
        self.track_identities[track_id] = [
            (n, s, t) for n, s, t in self.track_identities[track_id]
            if t > cutoff
        ]

    def get_persistent_identity(self, track_id: TrackId,
                                 current_time: float) -> Tuple[Optional[str], float]:
        """
        Return the most confident known identity from recent history.
        Returns (name, score) or (None, 0.0) if nothing usable.
        """
        history = self.track_identities.get(track_id)
        if not history:
            return None, 0.0

        recent = [
            (n, s) for n, s, t in history
            if current_time - t < self.persistence_time
        ]
        if not recent:
            return None, 0.0

        # Prefer known identities over Unknown
        known = [(n, s) for n, s in recent if not n.startswith("Unknown")]
        if not known:
            return None, 0.0

        # Group by name and pick the one with the highest average score
        scores_by_name: Dict[str, List[float]] = {}
        for name, score in known:
            scores_by_name.setdefault(name, []).append(score)

        best_name = max(scores_by_name, key=lambda n: np.mean(scores_by_name[n]))
        best_score = float(np.mean(scores_by_name[best_name]))
        return best_name, best_score

    def clear_track(self, track_id: TrackId):
        """Remove all history for this track."""
        self.track_identities.pop(track_id, None)