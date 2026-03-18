"""
Camera configuration and runtime state models.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

class CameraStatus(Enum):
    OFFLINE   = "Offline"
    CONNECTING = "Connecting"
    LIVE      = "Live"
    ERROR     = "Error"

@dataclass
class CameraConfig:
    id: int
    name: str
    source: str          # RTSP URL, file path, or int index
    location: str = ""   # e.g. "Main Hall", "Entrance"
    enabled: bool = True
    # Map position (0.0–1.0 relative coords)
    map_x: float = 0.5
    map_y: float = 0.5

@dataclass
class CameraState:
    config: CameraConfig
    status: CameraStatus = CameraStatus.OFFLINE
    fps: float = 0.0
    active_tracks: int = 0
    last_error: Optional[str] = None
