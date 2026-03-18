"""
facetrack/types.py

Shared type aliases for the entire package.
Change TrackId here and every annotation updates automatically.
"""
from typing import NewType, Tuple, Union

# Stable string identifier produced by ByteTrack (str(box.id[0])).
# Declared as NewType so mypy can distinguish it from arbitrary strings.
TrackId = NewType("TrackId", str)

# Integer camera index or RTSP source identifier.
CamId = int

# Composite key used by UnknownManager: (cam_id, track_id).
TrackKey = Tuple[CamId, TrackId]
