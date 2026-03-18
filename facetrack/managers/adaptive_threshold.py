"""
Adaptive threshold manager with caching
"""

import numpy as np
from typing import Dict

from facetrack.types import TrackId


class AdaptiveThreshold:
    """Manages adaptive similarity thresholds with caching optimization."""

    def __init__(
        self,
        base_similarity_threshold: float = 0.42,
        min_similarity_threshold: float = 0.35,
        max_similarity_threshold: float = 0.60,
    ):
        self._base = float(base_similarity_threshold)
        self._min = float(min_similarity_threshold)
        self._max = float(max_similarity_threshold)
        self.track_thresholds: Dict[TrackId, float] = {}
        # Optimization: Cache last quality and frame count to avoid recalculation
        self.track_last_quality: Dict[TrackId, float] = {}
        self.track_last_frame_count: Dict[TrackId, int] = {}

    def get_threshold(self, track_id: TrackId, quality_score: float,
                      frame_count: int) -> float:
        """
        Get threshold with caching optimization.
        Higher quality → lower threshold (more lenient).
        Older tracks → slightly lower threshold (more confident).
        """
        # Optimization: Check if we can use cached value
        if track_id in self.track_thresholds:
            last_quality = self.track_last_quality.get(track_id, 0.0)
            last_frame = self.track_last_frame_count.get(track_id, 0)

            # If quality and frame count haven't changed much, use cached value
            if abs(quality_score - last_quality) < 0.05 and abs(frame_count - last_frame) < 5:
                return self.track_thresholds[track_id]

        # Recalculate threshold (Quality > 0.90 is considered high)
        quality_adjustment = (float(quality_score) - 0.50) * 0.10
        age_factor = min(float(frame_count), 50.0)
        age_adjustment = -0.002 * age_factor

        # High quality -> lower threshold (easier match). Low quality -> higher threshold.
        threshold = self._base - quality_adjustment + age_adjustment
        threshold = float(np.clip(threshold, self._min, self._max))

        # Cache the result
        self.track_thresholds[track_id] = threshold
        self.track_last_quality[track_id] = quality_score
        self.track_last_frame_count[track_id] = frame_count

        return threshold

    def clear_track(self, track_id: TrackId):
        self.track_thresholds.pop(track_id, None)
        self.track_last_quality.pop(track_id, None)
        self.track_last_frame_count.pop(track_id, None)