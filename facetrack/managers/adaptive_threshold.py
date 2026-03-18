"""
Adaptive threshold manager with caching
"""

import numpy as np
from typing import Dict

# Import config
import sys
import os
from config import BASE_SIMILARITY_THRESHOLD, MIN_SIMILARITY_THRESHOLD, MAX_SIMILARITY_THRESHOLD

class AdaptiveThreshold:
    """Manages adaptive similarity thresholds with caching optimization."""

    def __init__(self):
        self.track_thresholds: Dict[int, float] = {}
        # Optimization: Cache last quality and frame count to avoid recalculation
        self.track_last_quality: Dict[int, float] = {}
        self.track_last_frame_count: Dict[int, int] = {}

    def get_threshold(self, track_id: int, quality_score: float,
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

        # High quality -> lower threshold (easier match). Low quality -> higher threshold (harder match to prevent FP).
        threshold = BASE_SIMILARITY_THRESHOLD - quality_adjustment + age_adjustment
        threshold = float(np.clip(threshold, MIN_SIMILARITY_THRESHOLD, MAX_SIMILARITY_THRESHOLD))

        # Cache the result
        self.track_thresholds[track_id] = threshold
        self.track_last_quality[track_id] = quality_score
        self.track_last_frame_count[track_id] = frame_count
        
        return threshold

    def clear_track(self, track_id: int):
        self.track_thresholds.pop(track_id, None)
        self.track_last_quality.pop(track_id, None)
        self.track_last_frame_count.pop(track_id, None)
