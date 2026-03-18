"""
Data models for Person and Attendance.
Pure Python dataclasses — zero Qt / CV dependency.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
from enum import Enum

class PersonGroup(Enum):
    SERVANT  = "Servant"
    YOUTH    = "Youth"
    VISITOR  = "Visitor"
    UNKNOWN  = "Unknown"

@dataclass
class Person:
    id: str
    name: str
    group: PersonGroup = PersonGroup.VISITOR
    photo_path: Optional[str] = None
    notes: str = ""
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    total_visits: int = 0

@dataclass
class AttendanceRecord:
    id: str
    person_id: str
    person_name: str
    camera_id: int
    camera_name: str
    timestamp: datetime
    confidence: float          # 0.0 – 1.0
    group: PersonGroup = PersonGroup.VISITOR
    is_unknown: bool = False
    face_snapshot_path: Optional[str] = None

@dataclass
class Detection:
    """Single face detection result from the recognition engine."""
    track_id: int
    person_id: Optional[str]
    name: str
    confidence: float
    bbox: tuple          # (x1, y1, x2, y2) in frame pixels
    age: int = 0
    gender: str = "Unknown"
    group: PersonGroup = PersonGroup.UNKNOWN
    is_unknown: bool = False
