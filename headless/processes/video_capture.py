"""
headless/processes/video_capture.py

Thin multiprocessing wrapper around facetrack.core.FrameCapture.
All capture logic now lives in facetrack/core/video_capture.py —
this file only owns the multiprocessing boundary (Queue push, stop flag).

Before:  ~100 lines of mixed capture + process plumbing
After:   ~30 lines of pure process coordination
"""

import queue
import logging
from typing import Any

from facetrack.core.video_capture import FrameCapture
from facetrack.infra.metrics import record_queue_drop
from facetrack.infra.errors import ErrorCode

logger = logging.getLogger(__name__)

def video_process(
    cam_idx: int,
    source: Any,
    frame_queue: Any,
    display_queue: Any,
    stop_flag: Any,
    target_fps: float = 30.0,
):
    """
    Multiprocessing entry point — one process per camera.
    Reads frames via FrameCapture and pushes them to both queues.
    Stops when stop_flag is set.
    """
    cap = FrameCapture(source=source, target_fps=target_fps)

    try:
        for frame in cap.frames():
            if stop_flag.value:
                break

            # Push to inference queue (drop oldest if inference is busy)
            try:
                frame_queue.put_nowait((cam_idx, frame))
            except queue.Full:
                try:
                    frame_queue.get_nowait()
                    frame_queue.put_nowait((cam_idx, frame))
                except queue.Empty:
                    pass
                record_queue_drop("frame")

            # Push to display queue (drop oldest if UI is busy)
            try:
                display_queue.put_nowait((cam_idx, frame))
            except queue.Full:
                try:
                    display_queue.get_nowait()
                    display_queue.put_nowait((cam_idx, frame))
                except queue.Empty:
                    pass
                record_queue_drop("display")

    finally:
        cap.close()
        logger.info("video_process exited for cam %d", cam_idx)
