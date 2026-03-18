import threading
import time
from collections import defaultdict
from typing import Dict


class MetricsRegistry:
    """
    Very small in-process metrics registry.

    For now this is intentionally minimal: it keeps counters and gauges in
    memory and can be inspected by debug tools or logged periodically.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: Dict[str, float] = defaultdict(float)
        self._gauges: Dict[str, float] = defaultdict(float)

    def inc(self, name: str, value: float = 1.0) -> None:
        with self._lock:
            self._counters[name] += value

    def set_gauge(self, name: str, value: float) -> None:
        with self._lock:
            self._gauges[name] = value

    def snapshot(self) -> Dict[str, Dict[str, float]]:
        with self._lock:
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
            }


metrics = MetricsRegistry()


def record_frame_processed(cam_id: int, latency_sec: float) -> None:
    metrics.inc(f"cam.{cam_id}.frames")
    metrics.set_gauge(f"cam.{cam_id}.latency_ms", latency_sec * 1000.0)


def record_queue_drop(queue_name: str) -> None:
    metrics.inc(f"queue.{queue_name}.dropped")

