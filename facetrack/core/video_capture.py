"""
facetrack/core/video_capture.py

Transport-agnostic frame capture.
Extracted from src/processes/video_capture.py so that BOTH the PySide6
CameraWorker and the headless inference_process share the same capture logic.

Usage (iterator style — works in any thread or process)
-------------------------------------------------------
    with FrameCapture(source=0) as cap:
        for frame_bgr in cap:
            results = processor.process(frame_bgr)

Or as a generator that the caller drains:
    cap = FrameCapture(source="rtsp://...")
    for frame in cap.frames():
        ...
    cap.close()
"""

import sys
import time
import logging
from typing import Generator, Optional, Union

import numpy as np

logger = logging.getLogger(__name__)

# Frames per second cap applied to all sources.
# Prevents CPU/GPU overload on high-fps cameras; inference is the bottleneck anyway.
_DEFAULT_TARGET_FPS = 30


def _suppress_cv2_logs() -> None:
    """
    Silence OpenCV's verbose internal warnings (DirectShow / MSMF on Windows).

    cv2.setLogLevel() exists in OpenCV 4.5+ but is absent in some distribution
    builds.  Fall back to the environment variable approach which works across
    all versions.
    """
    import os
    import cv2
    # Environment variable works in all OpenCV versions
    os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
    # API call works in 4.5+; skip silently if absent
    if hasattr(cv2, "setLogLevel"):
        try:
            cv2.setLogLevel(3)   # 3 = LOG_LEVEL_ERROR
        except Exception:
            pass


class FrameCapture:
    """
    Unified frame reader for:
      - Local webcam / USB camera  (source = int or "0")
      - Video file                 (source = "path/to/file.mp4")
      - RTSP / network stream      (source = "rtsp://...")

    Auto-reconnects on stream loss.  Respects a target FPS cap.
    Yields BGR numpy arrays (H × W × 3, uint8) — same format expected by
    InsightFace and OpenCV.

    Context-manager protocol:
        with FrameCapture(0) as cap:
            for frame in cap:
                ...

    Manual protocol:
        cap = FrameCapture(0)
        cap.open()
        for frame in cap.frames():
            if done: break
        cap.close()
    """

    def __init__(
        self,
        source: Union[int, str],
        target_fps: float = _DEFAULT_TARGET_FPS,
        reconnect_delay: float = 2.0,
    ):
        raw = str(source).strip()
        # Normalise "0", "1", ... → integer index for OpenCV
        self.source: Union[int, str] = int(raw) if raw.isdigit() else source
        self.target_fps = max(1.0, float(target_fps))
        self.reconnect_delay = reconnect_delay

        self._stop = False
        self._cap = None        # cv2.VideoCapture (local/file)
        self._container = None  # av.Container (RTSP)

        self._is_rtsp = isinstance(self.source, str) and (
            self.source.lower().startswith("rtsp")
            or self.source.lower().endswith((".mp4", ".avi", ".mkv", ".mov"))
        )
        self._frame_interval = 1.0 / self.target_fps
        self._last_frame_time = 0.0

    # ------------------------------------------------------------------ #
    # Context manager                                                      #
    # ------------------------------------------------------------------ #

    def open(self):
        """Explicit open — called automatically by __enter__."""
        self._stop = False

    def close(self):
        """Release all resources."""
        self._stop = True
        self._release_cv()
        self._release_av()

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *_):
        self.close()

    def stop(self):
        """Signal the capture loop to exit on the next iteration."""
        self._stop = True

    # ------------------------------------------------------------------ #
    # Public generator                                                     #
    # ------------------------------------------------------------------ #

    def frames(self) -> Generator[np.ndarray, None, None]:
        """
        Yield BGR frames indefinitely until stop() is called.
        Reconnects automatically on stream loss.
        Applies the target-FPS rate cap via sleep.
        """
        if self._is_rtsp:
            yield from self._frames_rtsp()
        else:
            yield from self._frames_local()

    def __iter__(self):
        return self.frames()

    # ------------------------------------------------------------------ #
    # RTSP via PyAV                                                        #
    # ------------------------------------------------------------------ #

    def _frames_rtsp(self) -> Generator[np.ndarray, None, None]:
        while not self._stop:
            try:
                import av
                logger.info("Connecting RTSP: %s", self.source)
                self._container = av.open(
                    str(self.source),
                    options={"rtsp_transport": "tcp", "stimeout": "5000000"},
                )
                stream = self._container.streams.video[0]
                stream.thread_type = "AUTO"
                logger.info("RTSP connected: %s", self.source)

                for av_frame in self._container.decode(stream):
                    if self._stop:
                        return
                    frame = av_frame.to_ndarray(format="bgr24")
                    yield from self._rate_limited(frame)

                # Stream ended naturally — loop to reconnect
                self._release_av()
                logger.warning("RTSP stream ended — reconnecting: %s", self.source)

            except Exception as e:
                logger.warning("RTSP error (%s): %s — reconnecting in %.1fs",
                               self.source, e, self.reconnect_delay)
                self._release_av()
                if not self._stop:
                    time.sleep(self.reconnect_delay)

    def _release_av(self):
        if self._container is not None:
            try:
                self._container.close()
            except Exception:
                pass
            self._container = None

    # ------------------------------------------------------------------ #
    # Local / webcam / file via OpenCV                                     #
    # ------------------------------------------------------------------ #

    def _frames_local(self) -> Generator[np.ndarray, None, None]:
        import cv2
        _suppress_cv2_logs()

        while not self._stop:
            logger.info("Opening local source: %s", self.source)
            if isinstance(self.source, int) and sys.platform.startswith("win"):
                self._cap = cv2.VideoCapture(self.source, cv2.CAP_DSHOW)
            else:
                self._cap = cv2.VideoCapture(self.source)

            if not self._cap.isOpened():
                logger.error(
                    "Cannot open source %s — retrying in %.1fs",
                    self.source, self.reconnect_delay,
                )
                self._release_cv()
                if not self._stop:
                    time.sleep(self.reconnect_delay)
                continue

            fps = self._cap.get(cv2.CAP_PROP_FPS)
            w   = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h   = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            logger.info("Source opened: %s  %dx%d @ %.1f fps", self.source, w, h, fps)

            try:
                while not self._stop:
                    ret, frame = self._cap.read()
                    if not ret:
                        # Video file: loop; live camera: reconnect
                        if isinstance(self.source, str):
                            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                            time.sleep(0.05)
                        else:
                            logger.warning(
                                "Camera %s read failure — reconnecting", self.source
                            )
                            break
                        continue
                    yield from self._rate_limited(frame)
            finally:
                self._release_cv()

            if not self._stop:
                time.sleep(self.reconnect_delay)

    def _release_cv(self):
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None

    # ------------------------------------------------------------------ #
    # Rate limiter                                                         #
    # ------------------------------------------------------------------ #

    def _rate_limited(self, frame: np.ndarray) -> Generator[np.ndarray, None, None]:
        """
        Enforce the target FPS cap.
        Yields the frame exactly once, sleeping only the remaining interval.
        """
        now = time.monotonic()
        elapsed = now - self._last_frame_time
        remaining = self._frame_interval - elapsed
        if remaining > 0:
            time.sleep(remaining)
        self._last_frame_time = time.monotonic()
        yield frame

    # ------------------------------------------------------------------ #
    # Metadata helpers                                                     #
    # ------------------------------------------------------------------ #

    @property
    def is_rtsp(self) -> bool:
        return self._is_rtsp

    def resolution(self) -> Optional[tuple]:
        """Return (width, height) if a local capture is open, else None."""
        if self._cap is not None and self._cap.isOpened():
            import cv2
            return (
                int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            )
        return None