"""
Alert manager — collects unknown-face alerts and system events.
Emits via a simple callback list (UI registers listeners).
"""
import uuid
import threading
from datetime import datetime
from typing import List, Callable

from facetrack.models.alert import Alert, AlertSeverity

class AlertManager:
    def __init__(self):
        self._alerts: List[Alert] = []
        self._listeners: List[Callable[[Alert], None]] = []
        self._lock = threading.Lock()

    def subscribe(self, fn: Callable[[Alert], None]):
        with self._lock:
            if fn not in self._listeners:
                self._listeners.append(fn)

    def unsubscribe(self, fn: Callable[[Alert], None]):
        with self._lock:
            try:
                self._listeners.remove(fn)
            except ValueError:
                pass

    def push(self, title: str, message: str,
             severity: AlertSeverity = AlertSeverity.WARNING,
             camera_id: int = None, camera_name: str = None,
             face_snapshot_path: str = None, seen_count: int = 1) -> Alert:
        alert = Alert(
            id=str(uuid.uuid4()),
            title=title,
            message=message,
            severity=severity,
            timestamp=datetime.now(),
            camera_id=camera_id,
            camera_name=camera_name,
            face_snapshot_path=face_snapshot_path,
            seen_count=seen_count,
        )
        with self._lock:
            self._alerts.append(alert)
            listeners_copy = list(self._listeners)

        # Fire callbacks outside the lock to prevent deadlocks
        for fn in listeners_copy:
            try:
                fn(alert)
            except Exception:
                pass
        return alert

    def get_all(self) -> List[Alert]:
        with self._lock:
            return list(reversed(self._alerts))

    def get_unread_count(self) -> int:
        with self._lock:
            return sum(1 for a in self._alerts if not a.dismissed)

    def dismiss(self, alert_id: str):
        with self._lock:
            for a in self._alerts:
                if a.id == alert_id:
                    a.dismissed = True
                    break