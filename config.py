"""
Configuration file for Enterprise Face Recognition System
Modify these settings to adjust system behavior
"""

import os

# ================= CAMERA CONFIGURATION =================
# Add up to 4 cameras. Can be integer (local webcam) or RTSP string.
# SECURITY: Use environment variables for credentials in production, e.g.:
#   os.environ.get("RTSP_CAM1_URL", "rtsp://user:password@host:554/path")
CAMERA_SOURCES = [
    # "/path/to/demo_vid.mp4",  # Simulated Test Stream
    #"rtsp://admin:Ehab2468@192.168.1.70:554/Streaming/Channels/101"  # Cam 1 (set RTSP_CAM1_URL in env)
    # os.environ.get("RTSP_CAM2_URL"),  # Cam 2
    0,  # USB webcam (Camera 1)
]
# ================= DATABASE SETTINGS =================
PHOTOS_DIR = "photos"
INDEX_FILE = "faces_index.bin"
LABELS_FILE = "labels.json"          # JSON (safe) – replaces pickle
EMBEDDING_DIM = 512

# ================= RECOGNITION THRESHOLDS =================
# Base similarity threshold (0.0 to 1.0, higher = stricter). Lower = more recognition hits.
BASE_SIMILARITY_THRESHOLD = 0.42

# Adaptive threshold bounds
MIN_SIMILARITY_THRESHOLD = 0.35   # Minimum threshold (lenient for clear faces)
MAX_SIMILARITY_THRESHOLD = 0.60   # Maximum threshold

# Marginal threshold to prevent enrolled personnel at bad angles from being saved as new unknown strangers
MARGINAL_SIMILARITY_THRESHOLD = 0.38

# ================= QUALITY THRESHOLDS =================
# Relaxed for easier recognition (smaller faces, more angle, some blur OK)
FACE_MIN_SIZE = 40              # Minimum face size (allow more distant faces)
FACE_BLUR_THRESHOLD = 10.0      # Laplacian variance (lowered for <30cm faces and blur)
FACE_ANGLE_THRESHOLD = 60.0     # Maximum face angle in degrees (more lenient)

# ================= TEMPORAL SMOOTHING =================
VOTING_WINDOW_SIZE = 10         # Frames to consider for voting
CONFIDENCE_DECAY = 0.90         # Decay factor for old votes
MIN_CONSENSUS_FRAMES = 1        # Show name after 1 vote (was 2; every-frame detection gives quick consensus)
# Bounding box smoothing (0-1, higher = less smoothing, more responsive to fast movement)
BBOX_SMOOTHING_ALPHA = 1.0

# ================= TRACKING SETTINGS =================
COOLDOWN_SECONDS = 300          # Seconds between attendance logs (5 minutes)
UNKNOWN_COOLDOWN = 5            # Seconds between unknown face saves per track
UNKNOWN_SESSION_LIMIT = 60      # Maximum number of unknown face images to save per session
UNKNOWN_SESSION_WINDOW = 300    # Seconds before unknown_session_count resets (5 minutes)
PERSISTENCE_RECOVERY_THRESHOLD = 0.35  # Min score to recover identity from history

# ================= TRACKING SETTINGS =================
TRACKER_MAX_AGE = 45            # Frames before track expires (higher = less flicker)
MIN_IOU_THRESHOLD = 0.20       # Minimum IoU for detection-to-track association (display/recognition)
# Note: For DeepSort legacy, MIN_BBOX_PIXELS was used. ByteTrack handles minimum boxes internally.
MIN_BBOX_PIXELS = 8            # Reject detections smaller than this (avoids degenerate state)

# ================= IDENTITY LOCK =================
# Higher threshold + embedding check = prevents wrong person (e.g. friend labeled as you)
IDENTITY_LOCK_THRESHOLD = 0.42   # Must be confident to lock (lowered for better recognition)
LOCK_CONSENSUS_FRAMES = 3        # Same name for N frames before locking (reduced for faster lock)
LOCK_EMBEDDING_VERIFY = 0.38     # When using lock: current face must match stored embedding (more lenient)

# ================= PERFORMANCE SETTINGS =================
FRAME_QUEUE_SIZE = 5            # Maximum frames in queue
RESULT_QUEUE_SIZE = 5           # Maximum results in queue

# Maximum resolution byte size for Shared Memory buffers (1080p = 1920*1080*3)
MAX_SHM_FRAME_SIZE = 1920 * 1080 * 3

# ================= DISPLAY SETTINGS =================
WINDOW_NAME = "Enterprise Face Recognition System"
SHOW_QUALITY_SCORE = True       # Show quality score in display
SHOW_TRACK_ID = True            # Show track ID in display
DISPLAY_GRID_WIDTH = 1280       # Mosaic width (build_grid)
DISPLAY_GRID_HEIGHT = 960       # Mosaic height (build_grid)
# Display queue: max frames buffered for UI. None = num_cameras * 2
DISPLAY_QUEUE_SIZE = None

# ================= SESSION SETTINGS =================
# Base directory for Sessions folder. None = current working directory.
SESSIONS_BASE_DIR = None

# ================= MODEL SETTINGS =================
PERSON_DETECTION_MODEL = "yolov8n.pt"  # YOLOv8 model for fast person detection
PERSON_CONF_THRESHOLD = 0.35           # Confidence threshold for person detection (more lenient)

# Execution providers (order matters - first available will be used)
# Removed CoreML per user request. TensorRT will accelerate RTX 3050 laptops/desktops.
EXECUTION_PROVIDERS = [
    "TensorrtExecutionProvider",
    "CUDAExecutionProvider", 
    "CPUExecutionProvider"
]

# GPU-optimized detection size (larger = more accurate, uses more GPU memory)
# (640, 640) = faster processing, lower latency for responsive tracking
DETECTION_SIZE = (640, 640)     # Optimized for speed and responsiveness

# GPU FAISS settings
USE_GPU_FAISS = True            # Use GPU-accelerated FAISS for faster search
FAISS_GPU_ID = 0                # GPU device ID (0 for first GPU)
