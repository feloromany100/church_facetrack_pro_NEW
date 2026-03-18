"""
CameraScanner — background worker that probes for available cameras.

Local scan:  tries cv2.VideoCapture(0..9), reports which indices open.
RTSP scan:   pings a user-supplied subnet (e.g. 192.168.1.x) on port 554
             using a fast TCP connect, then tries common RTSP path patterns.

Runs entirely in a QThread so the UI never blocks.
"""
import socket
import time
import logging

from PySide6.QtCore import QThread, Signal

logger = logging.getLogger("CameraScanner")

# Common RTSP path patterns tried per host
_RTSP_PATHS = [
    "/Streaming/Channels/101",
    "/Streaming/Channels/1",
    "/stream1",
    "/live/ch00_0",
    "/cam/realmonitor?channel=1&subtype=0",
    "/h264/ch1/main/av_stream",
    "/video1",
    "/live",
    "/",
]

class CameraScanner(QThread):
    """
    Signals
    -------
    found_local(index, label)   — a local webcam index that opened successfully
    found_rtsp(url, label)      — an RTSP URL that responded on port 554
    scan_progress(pct)          — 0–100 progress
    scan_done()                 — scan finished
    """
    found_local    = Signal(int, str)    # index, label
    found_rtsp     = Signal(str, str)    # url, label
    scan_progress  = Signal(int)         # 0-100
    scan_done      = Signal()

    def __init__(self, rtsp_subnet: str = "", rtsp_user: str = "",
                 rtsp_pass: str = "", rtsp_port: int = 554,
                 max_local: int = 10, parent=None):
        super().__init__(parent)
        self._subnet    = rtsp_subnet.strip()   # e.g. "192.168.1"
        self._user      = rtsp_user
        self._pass      = rtsp_pass
        self._port      = rtsp_port
        self._max_local = max_local
        self._stop      = False

    def stop_scan(self):
        self._stop = True

    def run(self):
        self._stop = False
        steps = self._max_local + (254 if self._subnet else 0)
        done  = 0

        # ── 1. Local webcam scan ──────────────────────────────────────────────
        import cv2
        logger.info("Scanning local cameras…")
        for idx in range(self._max_local):
            if self._stop:
                break
            cap = cv2.VideoCapture(idx)
            if cap.isOpened():
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                label = f"Local Camera {idx}  ({w}×{h})"
                logger.info(f"  ✓ {label}")
                self.found_local.emit(idx, label)
            cap.release()
            done += 1
            self.scan_progress.emit(int(done / steps * 100))

        # ── 2. RTSP subnet scan ───────────────────────────────────────────────
        if self._subnet and not self._stop:
            logger.info(f"Scanning RTSP subnet {self._subnet}.1-254 …")
            creds = f"{self._user}:{self._pass}@" if self._user else ""
            for host_byte in range(1, 255):
                if self._stop:
                    break
                host = f"{self._subnet}.{host_byte}"
                if self._tcp_ping(host, self._port, timeout=0.25):
                    # Host responded on 554 — try common paths
                    for path in _RTSP_PATHS:
                        url = f"rtsp://{creds}{host}:{self._port}{path}"
                        if self._rtsp_probe(url):
                            label = f"RTSP  {host}{path}"
                            logger.info(f"  ✓ {label}")
                            self.found_rtsp.emit(url, label)
                            break   # one URL per host is enough
                done += 1
                self.scan_progress.emit(int(done / steps * 100))

        self.scan_progress.emit(100)
        self.scan_done.emit()
        logger.info("Camera scan complete.")

    # ── Helpers ───────────────────────────────────────────────────────────────
    @staticmethod
    def _tcp_ping(host: str, port: int, timeout: float = 0.3) -> bool:
        """Return True if TCP port is open (fast, no RTSP handshake)."""
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            return False

    @staticmethod
    def _rtsp_probe(url: str, timeout: float = 1.5) -> bool:
        """
        Send a minimal RTSP OPTIONS request and check for '200 OK'.
        Much faster than opening a full cv2.VideoCapture.
        """
        try:
            from urllib.parse import urlparse
            p = urlparse(url)
            host, port = p.hostname, p.port or 554
            with socket.create_connection((host, port), timeout=timeout) as s:
                req = (
                    f"OPTIONS {url} RTSP/1.0\r\n"
                    f"CSeq: 1\r\n"
                    f"User-Agent: FaceTrackScanner/1.0\r\n\r\n"
                )
                s.sendall(req.encode())
                resp = s.recv(512).decode(errors="ignore")
                return "200" in resp
        except Exception:
            return False
