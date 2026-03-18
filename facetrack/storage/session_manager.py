"""
Session management utilities
"""

import os
from datetime import datetime
from typing import Tuple

from facetrack.services.config_service import ConfigService

def create_session(cfg=None) -> Tuple[str, str, str]:
    """
    Create a new session folder with timestamp.
    Returns: (session_folder, unknowns_dir, csv_path)
    """
    if cfg is None:
        cfg = ConfigService().load()

    session_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
    base_dir = getattr(cfg, "SESSIONS_BASE_DIR", None)
    base = base_dir if base_dir else os.getcwd()
    session_folder = os.path.join(base, "Sessions", session_id)
    unknowns_dir = os.path.join(session_folder, "Unknowns")

    os.makedirs(unknowns_dir, exist_ok=True)

    csv_path = os.path.join(session_folder, f"attendance_{session_id}.csv")
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("Name,Timestamp,Confidence,Age,Gender,TrackID\n")

    return session_folder, unknowns_dir, csv_path
