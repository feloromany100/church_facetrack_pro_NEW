"""
Alert manager — collects unknown-face alerts and system events.
Emits via a simple callback list (UI registers listeners).
"""
import uuid
from datetime import datetime
from typing import List, Callable

from facetrack.models.alert import Alert, AlertSeverity

class AlertManager:
    def __init__(self):
        self._alerts: List[Alert] = []
        self._listeners: List[Callable[[Alert], None]] = []

    def subscribe(self, fn: Callable[[Alert], None]):
        self._listeners.append(fn)

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
        self._alerts.append(alert)
        for fn in self._listeners:
            try:
                fn(alert)
            except Exception:
                pass
        return alert

    def get_all(self) -> List[Alert]:
        return list(reversed(self._alerts))

    def get_unread_count(self) -> int:
        return sum(1 for a in self._alerts if not a.dismissed)

    def dismiss(self, alert_id: str):
        for a in self._alerts:
            if a.id == alert_id:
                a.dismissed = True
