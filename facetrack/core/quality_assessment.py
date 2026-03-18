"""
Quality assessment utilities for face detection
"""

import cv2
import numpy as np
from typing import Tuple

def assess_face_quality(
    face_img: np.ndarray,
    face_obj,
    *,
    face_min_size: int = 40,
    face_blur_threshold: float = 10.0,
    face_angle_threshold: float = 60.0,
) -> Tuple[bool, float]:
    """
    Assess face quality with early exit optimization.
    Returns: (is_good_quality, quality_score)
    """
    if face_img.size == 0:
        return False, 0.0

    h, w = face_img.shape[:2]

    # Size check (fastest - check first)
    if h < face_min_size or w < face_min_size:
        return False, 0.0  # Early exit

    # Detection confidence (already available - check second)
    det_score = getattr(face_obj, 'det_score', 0.5)
    if det_score < 0.3:
        return False, 0.0  # Early exit

    # Blur detection (expensive - check third)
    gray = cv2.cvtColor(face_img, cv2.COLOR_BGR2GRAY)
    blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()

    if blur_score < face_blur_threshold:
        return False, max(0.0, blur_score / max(face_blur_threshold, 1))  # Early exit

    # Face angle check (most expensive - check last)
    angle_score = 1.0
    if hasattr(face_obj, 'kps') and face_obj.kps is not None:
        kps = face_obj.kps
        if len(kps) >= 2:
            eye_left = kps[0]
            eye_right = kps[1]
            angle = np.arctan2(
                eye_right[1] - eye_left[1],
                eye_right[0] - eye_left[0]
            ) * 180 / np.pi
            if abs(angle) > face_angle_threshold:
                angle_score = max(
                    0.0,
                    1.0 - (abs(angle) - face_angle_threshold) / face_angle_threshold
                )

    # Combined quality score
    # Blur normalised against threshold*3 so scores stay meaningful when threshold changes
    blur_norm = min(1.0, blur_score / max(face_blur_threshold * 3.0, 1.0))
    quality_score = blur_norm * 0.4 + angle_score * 0.3 + det_score * 0.3
    quality_score = min(1.0, quality_score)

    return quality_score > 0.28, quality_score
