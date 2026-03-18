"""
Track confidence scoring — combines detection quality signals into a per-track confidence.
"""

from typing import Dict

class TrackConfidence:
    """Smoothed confidence score aggregating face quality, track age, and IoU signal."""

    def __init__(self):
        self.track_scores: Dict[int, float] = {}

    def update(self, track_id: int, has_face: bool, face_quality: float,
               track_age: int, iou_score: float):
        """
        Update confidence score for a track.

        Args:
            track_id:     Track identifier.
            has_face:     Whether a face was detected this frame.
            face_quality: Quality score of the detected face (0–1).
            track_age:    Number of frames the track has existed.
            iou_score:    IoU score of the track-detection match (0–1).
        """
        # Ramp up over first 10 frames; fully confident after that
        age_confidence = min(1.0, track_age / 10.0)

        face_confidence = 1.0 if has_face else 0.5
        quality_confidence = face_quality if has_face else 0.7
        iou_confidence = min(1.0, iou_score / 0.5) if iou_score > 0 else 0.5

        raw = (
            0.3 * age_confidence
            + 0.3 * face_confidence
            + 0.2 * quality_confidence
            + 0.2 * iou_confidence
        )

        # Exponential moving average with previous score
        prev = self.track_scores.get(track_id, raw)
        self.track_scores[track_id] = 0.7 * prev + 0.3 * raw

    def get_confidence(self, track_id: int) -> float:
        """Return the current confidence score (default 0.5 for unseen tracks)."""
        return self.track_scores.get(track_id, 0.5)

    def clear_track(self, track_id: int):
        """Remove track from scoring."""
        self.track_scores.pop(track_id, None)
