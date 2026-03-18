"""
Alert model for unknown face detections and system events.
"""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

class AlertSeverity(Enum):
    INFO    = "info"
    WARNING = "warning"
    DANGER  = "danger"

@dataclass
class Alert:
    id: str
    title: str
    message: str
    severity: AlertSeverity
    timestamp: datetime
    camera_id: Optional[int] = None
    camera_name: Optional[str] = None
    face_snapshot_path: Optional[str] = None
    seen_count: int = 1          # how many times this unknown appeared
    dismissed: bool = False
