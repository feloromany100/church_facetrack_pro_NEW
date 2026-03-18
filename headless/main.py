#!/usr/bin/env python3
"""
Enterprise Face Recognition & Tracking System - Headless Entry Point
OpenCV mosaic mode — no PySide6 UI required.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import cv2
import time
import logging
import queue
import warnings
import numpy as np
from multiprocessing import Process, Queue, Value

warnings.filterwarnings("ignore", category=FutureWarning)

from facetrack.services.config_service import ConfigService
CFG = ConfigService().load()

from facetrack.storage.session_manager import create_session
from facetrack.infra.logging import setup_logging
from headless.processes.video_capture import video_process
from headless.processes.inference import inference_process
from facetrack.ui.overlay_renderer import draw_cv2

setup_logging()
logger = logging.getLogger(__name__)


def validate_config():
    """Validate configuration parameters."""
    errors = []

    if float(CFG.MIN_SIMILARITY_THRESHOLD) > float(CFG.BASE_SIMILARITY_THRESHOLD):
        errors.append(
            f"MIN_SIMILARITY_THRESHOLD ({CFG.MIN_SIMILARITY_THRESHOLD}) cannot be "
            f"greater than BASE_SIMILARITY_THRESHOLD ({CFG.BASE_SIMILARITY_THRESHOLD})"
        )

    if float(CFG.BASE_SIMILARITY_THRESHOLD) > float(CFG.MAX_SIMILARITY_THRESHOLD):
        errors.append(
            f"BASE_SIMILARITY_THRESHOLD ({CFG.BASE_SIMILARITY_THRESHOLD}) cannot be "
            f"greater than MAX_SIMILARITY_THRESHOLD ({CFG.MAX_SIMILARITY_THRESHOLD})"
        )

    if int(CFG.FACE_MIN_SIZE) < 20:
        errors.append(
            f"FACE_MIN_SIZE too small ({CFG.FACE_MIN_SIZE}), minimum recommended is 20"
        )

    if not CFG.CAMERA_SOURCES:
        errors.append("CAMERA_SOURCES is empty, at least one camera source is required")

    if len(CFG.CAMERA_SOURCES) > 4:
        logger.warning(
            f"⚠️ More than 4 cameras configured ({len(CFG.CAMERA_SOURCES)}), "
            "only first 4 will be used"
        )

    if errors:
        for error in errors:
            logger.error(f"❌ Configuration Error: {error}")
        for h in logger.handlers:
            h.flush()
        sys.exit(1)

    logger.info("✅ Configuration validated successfully")


def build_grid(
    frames: dict,
    width: int = None,
    height: int = None,
) -> np.ndarray:
    """Stitch per-camera frames into a 1x1 / 1x2 / 2x2 mosaic."""
    width = width if width is not None else CFG.DISPLAY_GRID_WIDTH
    height = height if height is not None else CFG.DISPLAY_GRID_HEIGHT
    num_cameras = len(frames)
    grid = np.zeros((height, width, 3), dtype=np.uint8)

    if not frames:
        return grid

    if num_cameras == 1:
        if 0 in frames:
            return cv2.resize(frames[0], (width, height))
        return grid
    elif num_cameras == 2:
        w, h = width // 2, height
        for i in range(2):
            if i in frames:
                grid[0:h, i*w:(i+1)*w] = cv2.resize(frames[i], (w, h))
        return grid
    else:  # 3-4 cameras → 2×2
        w, h = width // 2, height // 2
        for i in range(min(4, num_cameras)):
            if i in frames:
                row, col = i // 2, i % 2
                grid[row*h:(row+1)*h, col*w:(col+1)*w] = cv2.resize(frames[i], (w, h))
        return grid


def main():
    """Main entry point. Use Ctrl+C for graceful shutdown."""
    validate_config()

    try:
        SESSION_FOLDER, UNKNOWNS_DIR, CURRENT_SESSION_CSV = create_session(CFG)
    except OSError as e:
        logger.error(f"❌ Failed to create session: {e}")
        sys.exit(1)

    logger.info("🚀 Starting Enterprise Face Recognition System...")
    logger.info(f"📁 Session folder: {SESSION_FOLDER}")

    if not os.path.exists(CFG.PHOTOS_DIR) or not os.listdir(CFG.PHOTOS_DIR):
        logger.warning(
            f"⚠️ Photos directory is empty! Please add face images to '{CFG.PHOTOS_DIR}'."
        )
        logger.warning("⚠️ System will run in detection-only mode until faces are enrolled.")

    # Read display flags once at startup (headless mode doesn't hot-reload)
    show_quality = bool(getattr(CFG, "SHOW_QUALITY_SCORE", True))
    show_track_id = bool(getattr(CFG, "SHOW_TRACK_ID", True))

    num_cameras = min(4, len(CFG.CAMERA_SOURCES))
    frame_queue = Queue(maxsize=int(CFG.FRAME_QUEUE_SIZE))
    result_queue = Queue(maxsize=int(CFG.RESULT_QUEUE_SIZE))
    display_queue_size = (
        CFG.DISPLAY_QUEUE_SIZE
        if CFG.DISPLAY_QUEUE_SIZE is not None
        else num_cameras * 2
    )
    display_queue = Queue(maxsize=display_queue_size)
    stop_flag = Value('b', False)

    # Start video capture processes
    video_processes = []
    for idx, source in enumerate(CFG.CAMERA_SOURCES[:4]):
        p = Process(target=video_process,
                    args=(idx, source, frame_queue, display_queue, stop_flag))
        p.daemon = True
        p.start()
        video_processes.append(p)
        logger.info(f"📹 Started Capture Process for Camera {idx} ({source})")

    # Start inference process
    p_inference = Process(
        target=inference_process,
        args=(
            frame_queue,
            result_queue,
            stop_flag,
            SESSION_FOLDER,
            UNKNOWNS_DIR,
            CURRENT_SESSION_CSV,
        ),
    )
    p_inference.daemon = True
    p_inference.start()

    cv2.namedWindow(CFG.WINDOW_NAME, cv2.WINDOW_NORMAL)

    live_frames = {}
    overlay_results = {}

    fps_counter = 0
    fps_start_time = time.time()
    current_fps = 0.0
    inference_active = False

    try:
        while True:
            try:
                while True:
                    cam_idx, inferenced_frame, results = result_queue.get_nowait()
                    live_frames[cam_idx] = inferenced_frame
                    overlay_results[cam_idx] = results
                    inference_active = True
            except queue.Empty:
                pass

            try:
                while True:
                    cam_idx, raw_frame = display_queue.get_nowait()
                    if not inference_active:
                        live_frames[cam_idx] = raw_frame
            except queue.Empty:
                pass

            if not live_frames:
                placeholder = np.zeros((480, 640, 3), dtype=np.uint8)
                label = "Initializing models..." if p_inference.is_alive() else "Waiting for frames..."
                cv2.putText(placeholder, label, (20, 240),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
                cv2.imshow(CFG.WINDOW_NAME, placeholder)
                if cv2.waitKey(10) == 27:
                    break
                continue

            annotated_frames = {}
            total_tracks = 0

            for cam_idx, f in live_frames.items():
                f_draw = f.copy()
                res_list = overlay_results.get(cam_idx, [])
                total_tracks += len(res_list)

                f_draw = draw_cv2(f_draw, res_list,
                                  show_quality=show_quality,
                                  show_track_id=show_track_id)

                cv2.putText(f_draw, f"CAM {cam_idx}", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
                annotated_frames[cam_idx] = f_draw

            fps_counter += 1
            if time.time() - fps_start_time >= 1.0:
                current_fps = fps_counter / (time.time() - fps_start_time)
                fps_counter = 0
                fps_start_time = time.time()

            mosaic = build_grid(annotated_frames)
            fps_str = f"{current_fps:.1f}" if current_fps > 0 else "—"
            status_text = (
                f"Tracks: {total_tracks} | FPS: {fps_str} | "
                f"Session: {os.path.basename(SESSION_FOLDER)}"
            )
            cv2.putText(mosaic, status_text, (10, mosaic.shape[0] - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

            cv2.imshow(CFG.WINDOW_NAME, mosaic)
            if cv2.waitKey(1) == 27:
                break

    except KeyboardInterrupt:
        logger.info("Interrupted by user (Ctrl+C)")
    finally:
        logger.info("🛑 Shutting down...")
        stop_flag.value = True

        for p in video_processes:
            if p.is_alive():
                p.terminate()
                p.join(timeout=2)
                if p.is_alive():
                    logger.warning(f"Process {p.pid} did not exit in time, killing")
                    p.kill()
                    p.join(timeout=1)

        if p_inference.is_alive():
            p_inference.terminate()
            p_inference.join(timeout=2)
            if p_inference.is_alive():
                logger.warning(f"Inference process {p_inference.pid} did not exit in time, killing")
                p_inference.kill()
                p_inference.join(timeout=1)

        cv2.destroyAllWindows()
        logger.info(f"✅ Session data saved to: {SESSION_FOLDER}")


if __name__ == "__main__":
    main()