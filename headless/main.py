#!/usr/bin/env python3
"""
Enterprise Face Recognition & Tracking System - Main Entry Point
Modular architecture for better maintainability
"""

import os
import sys
# Avoid MKL duplicate lib errors when using ONNX/NumPy together
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import cv2
import time
import logging
import queue
import warnings
import numpy as np
from multiprocessing import Process, Queue, Value

warnings.filterwarnings("ignore", category=FutureWarning)

# Import configuration (single place for main.py)
from config import (
    CAMERA_SOURCES,
    WINDOW_NAME,
    FRAME_QUEUE_SIZE,
    RESULT_QUEUE_SIZE,
    PHOTOS_DIR,
    DISPLAY_GRID_WIDTH,
    DISPLAY_GRID_HEIGHT,
    DISPLAY_QUEUE_SIZE,
    BBOX_SMOOTHING_ALPHA,
    MIN_SIMILARITY_THRESHOLD,
    BASE_SIMILARITY_THRESHOLD,
    MAX_SIMILARITY_THRESHOLD,
    FACE_MIN_SIZE,
)

# Import utilities
from facetrack.storage.session_manager import create_session

# Central logging setup
from facetrack.infra.logging import setup_logging

# Import processes
from headless.processes.video_capture import video_process
from headless.processes.inference import inference_process

setup_logging()
logger = logging.getLogger(__name__)

def validate_config():
    """Validate configuration parameters."""
    errors = []

    if not 0.0 <= BBOX_SMOOTHING_ALPHA <= 1.0:
        errors.append(f"BBOX_SMOOTHING_ALPHA must be between 0 and 1, got {BBOX_SMOOTHING_ALPHA}")
    
    if MIN_SIMILARITY_THRESHOLD > BASE_SIMILARITY_THRESHOLD:
        errors.append(f"MIN_SIMILARITY_THRESHOLD ({MIN_SIMILARITY_THRESHOLD}) cannot be greater than BASE_SIMILARITY_THRESHOLD ({BASE_SIMILARITY_THRESHOLD})")
    
    if BASE_SIMILARITY_THRESHOLD > MAX_SIMILARITY_THRESHOLD:
        errors.append(f"BASE_SIMILARITY_THRESHOLD ({BASE_SIMILARITY_THRESHOLD}) cannot be greater than MAX_SIMILARITY_THRESHOLD ({MAX_SIMILARITY_THRESHOLD})")
    
    if FACE_MIN_SIZE < 20:
        errors.append(f"FACE_MIN_SIZE too small ({FACE_MIN_SIZE}), minimum recommended is 20")
    
    if not CAMERA_SOURCES:
        errors.append("CAMERA_SOURCES is empty, at least one camera source is required")
    
    if len(CAMERA_SOURCES) > 4:
        logger.warning(f"⚠️ More than 4 cameras configured ({len(CAMERA_SOURCES)}), only first 4 will be used")
    
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
    """Stitch per-camera frames into a 1x1 / 1x2 / 2x2 mosaic.

    Expects frames with keys 0..N-1 for N cameras; missing keys render as black.
    """
    width = width if width is not None else DISPLAY_GRID_WIDTH
    height = height if height is not None else DISPLAY_GRID_HEIGHT
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

def _is_unknown_name(name) -> bool:
    """True if name represents an unknown (unrecognized) identity."""
    return name is None or (
        isinstance(name, str) and name.startswith("Unknown")
    )

def main():
    """Main entry point. Use Ctrl+C for graceful shutdown (flushes CSV, closes windows)."""
    # Validate configuration
    validate_config()

    try:
        SESSION_FOLDER, UNKNOWNS_DIR, CURRENT_SESSION_CSV = create_session()
    except OSError as e:
        logger.error(f"❌ Failed to create session: {e}")
        sys.exit(1)

    logger.info("🚀 Starting Enterprise Face Recognition System...")
    logger.info(f"📁 Session folder: {SESSION_FOLDER}")

    if not os.path.exists(PHOTOS_DIR) or not os.listdir(PHOTOS_DIR):
        logger.warning(
            f"⚠️ Photos directory is empty! Please add face images to '{PHOTOS_DIR}'."
        )
        logger.warning("⚠️ System will run in detection-only mode until faces are enrolled.")

    num_cameras = min(4, len(CAMERA_SOURCES))
    frame_queue = Queue(maxsize=FRAME_QUEUE_SIZE)
    result_queue = Queue(maxsize=RESULT_QUEUE_SIZE)
    display_queue_size = (
        DISPLAY_QUEUE_SIZE
        if DISPLAY_QUEUE_SIZE is not None
        else num_cameras * 2
    )
    display_queue = Queue(maxsize=display_queue_size)
    stop_flag = Value('b', False)

    # Start video capture processes
    video_processes = []
    for idx, source in enumerate(CAMERA_SOURCES[:4]):
        p = Process(target=video_process, args=(idx, source, frame_queue, display_queue, stop_flag))
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

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)

    live_frames = {}
    overlay_results = {}
    
    # Performance monitoring
    fps_counter = 0
    fps_start_time = time.time()
    current_fps = 0.0
    
    # Track whether inference has produced its first output frame yet
    inference_active = False
    
    try:
        while True:
            loop_start = time.time()
            
            # Get latest results AND the exact frame they were inferenced on
            try:
                while True:
                    cam_idx, inferenced_frame, results = result_queue.get_nowait()
                    live_frames[cam_idx] = inferenced_frame  # Zero-lag sync
                    overlay_results[cam_idx] = results
                    inference_active = True
            except queue.Empty:
                pass

            # Drain display queue so it doesn't block. 
            # If inference is active, we just drop these frames (relying entirely on inferenced_frame).
            # If inference is NOT active (e.g. during warmup), we display these live raw frames.
            try:
                while True:
                    cam_idx, raw_frame = display_queue.get_nowait()
                    if not inference_active:
                        live_frames[cam_idx] = raw_frame
            except queue.Empty:
                pass

            # Show placeholder if no frames yet
            if not live_frames:
                placeholder = np.zeros((480, 640, 3), dtype=np.uint8)
                label = "Initializing models..." if p_inference.is_alive() else "Waiting for frames..."
                cv2.putText(placeholder, label, (20, 240),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
                cv2.imshow(WINDOW_NAME, placeholder)
                if cv2.waitKey(10) == 27:
                    break
                continue

            # Build annotated frames
            annotated_frames = {}
            total_tracks = 0

            for cam_idx, f in live_frames.items():
                f_draw = f.copy()
                res_list = overlay_results.get(cam_idx, [])
                total_tracks += len(res_list)

                for res in res_list:
                    x1, y1, x2, y2 = res["bbox"]
                    name = res.get("name", "Unknown")
                    score = res.get("score", 0.0)
                    gender = res.get("gender", "Unknown")
                    age = res.get("age", 0)
                    quality = res.get("quality", 0.0)

                    color = (0, 255, 0) if not _is_unknown_name(name) else (0, 0, 255)
                    cv2.rectangle(f_draw, (x1, y1), (x2, y2), color, 2)

                    if not _is_unknown_name(name):
                        label = f"{name} {int(score * 100)}%"
                        sub_label = f"{gender}, {age}y | Q:{quality:.2f}"
                    else:
                        label = name
                        sub_label = f"Q:{quality:.2f}"

                    (text_w, text_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
                    cv2.rectangle(f_draw, (x1, y1 - text_h - 25), (x1 + text_w, y1), color, -1)
                    cv2.putText(f_draw, label, (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                    cv2.putText(f_draw, sub_label, (x1, y2 + 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

                cv2.putText(f_draw, f"CAM {cam_idx}", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
                annotated_frames[cam_idx] = f_draw

            # Calculate FPS
            fps_counter += 1
            if time.time() - fps_start_time >= 1.0:
                current_fps = fps_counter / (time.time() - fps_start_time)
                fps_counter = 0
                fps_start_time = time.time()

            # Stitch grid and render
            mosaic = build_grid(annotated_frames)
            fps_str = f"{current_fps:.1f}" if current_fps > 0 else "—"
            status_text = f"Tracks: {total_tracks} | FPS: {fps_str} | Session: {os.path.basename(SESSION_FOLDER)}"
            cv2.putText(mosaic, status_text, (10, mosaic.shape[0] - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

            cv2.imshow(WINDOW_NAME, mosaic)
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
