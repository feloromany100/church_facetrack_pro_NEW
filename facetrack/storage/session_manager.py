"""
Session management utilities
"""

import os
from datetime import datetime
from typing import Tuple

try:
    from config import SESSIONS_BASE_DIR
except ImportError:
    SESSIONS_BASE_DIR = None

def create_session() -> Tuple[str, str, str]:
    """
    Create a new session folder with timestamp.
    Returns: (session_folder, unknowns_dir, csv_path)
    """
    session_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
    base = SESSIONS_BASE_DIR if SESSIONS_BASE_DIR else os.getcwd()
    session_folder = os.path.join(base, "Sessions", session_id)
    unknowns_dir = os.path.join(session_folder, "Unknowns")

    os.makedirs(unknowns_dir, exist_ok=True)

    csv_path = os.path.join(session_folder, f"attendance_{session_id}.csv")
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("Name,Timestamp,Confidence,Age,Gender,TrackID\n")

    return session_folder, unknowns_dir, csv_path
