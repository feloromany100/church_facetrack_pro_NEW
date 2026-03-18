"""
headless/processes/inference.py

Thin multiprocessing wrapper around facetrack.core.FrameProcessor.
All inference logic now lives in facetrack/core/frame_processor.py —
this file only owns the multiprocessing boundary (Queue in/out, stop flag).

Before:  ~400 lines of mixed inference + process plumbing
After:   ~50 lines of pure process coordination
"""

import queue
import logging
from typing import Any

from facetrack.core.frame_processor import FrameProcessor
from facetrack.infra.errors import ErrorCode

logger = logging.getLogger(__name__)

def inference_process(
    frame_queue: Any,
    result_queue: Any,
    stop_flag: Any,
    session_folder: str,
    unknowns_dir: str,
    csv_path: str,
):
    """
    Multiprocessing entry point.
    Pulls (cam_id, frame_bgr) from frame_queue, runs FrameProcessor,
    pushes (cam_id, frame_bgr, results) to result_queue.

    One FrameProcessor is created per camera seen in the queue.
    Processors initialize lazily on first frame for that camera.
    """
    processors: dict = {}
    failed_cams: set[int] = set()

    try:
        while not stop_flag.value:
            try:
                cam_id, frame = frame_queue.get(timeout=0.01)
            except queue.Empty:
                continue

            # Skip cameras that have already failed hard
            if cam_id in failed_cams:
                continue

            # Lazy init: one FrameProcessor per camera
            if cam_id not in processors:
                proc = FrameProcessor(
                    cam_id=cam_id,
                    session_folder=session_folder,
                    unknowns_dir=unknowns_dir,
                    csv_path=csv_path,
                )
                ok = proc.initialize()
                if not ok:
                    logger.error(
                        "FrameProcessor init failed for cam %d; disabling this camera",
                        cam_id,
                        extra={"camera_id": cam_id, "error_code": ErrorCode.MODEL_INIT_FAIL},
                    )
                    failed_cams.add(cam_id)
                    # Do not stop the whole pipeline – continue serving other cameras.
                    continue
                processors[cam_id] = proc
                logger.info("FrameProcessor ready for cam %d", cam_id)

            results = processors[cam_id].process(frame)

            try:
                result_queue.put_nowait((cam_id, frame, results))
            except queue.Full:
                pass  # display queue full — drop this result, inference continues

    finally:
        for proc in processors.values():
            proc.cleanup()
