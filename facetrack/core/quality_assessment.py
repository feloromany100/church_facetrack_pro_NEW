"""
Quality assessment utilities for face detection
"""

import cv2
import numpy as np
from typing import Tuple

# Import config
import sys
import os
from config import FACE_MIN_SIZE, FACE_BLUR_THRESHOLD, FACE_ANGLE_THRESHOLD

def assess_face_quality(face_img: np.ndarray, face_obj) -> Tuple[bool, float]:
    """
    Assess face quality with early exit optimization.
    Returns: (is_good_quality, quality_score)
    """
    if face_img.size == 0:
        return False, 0.0

    h, w = face_img.shape[:2]

    # Size check (fastest - check first)
    if h < FACE_MIN_SIZE or w < FACE_MIN_SIZE:
        return False, 0.0  # Early exit

    # Detection confidence (already available - check second)
    det_score = getattr(face_obj, 'det_score', 0.5)
    if det_score < 0.3:
        return False, 0.0  # Early exit

    # Blur detection (expensive - check third)
    gray = cv2.cvtColor(face_img, cv2.COLOR_BGR2GRAY)
    blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()

    if blur_score < FACE_BLUR_THRESHOLD:
        return False, max(0.0, blur_score / max(FACE_BLUR_THRESHOLD, 1))  # Early exit

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
            if abs(angle) > FACE_ANGLE_THRESHOLD:
                angle_score = max(
                    0.0,
                    1.0 - (abs(angle) - FACE_ANGLE_THRESHOLD) / FACE_ANGLE_THRESHOLD
                )

    # Combined quality score
    # Blur normalised against threshold*3 so scores stay meaningful when threshold changes
    blur_norm = min(1.0, blur_score / max(FACE_BLUR_THRESHOLD * 3.0, 1.0))
    quality_score = blur_norm * 0.4 + angle_score * 0.3 + det_score * 0.3
    quality_score = min(1.0, quality_score)

    return quality_score > 0.28, quality_score
