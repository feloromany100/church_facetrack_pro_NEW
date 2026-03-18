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

    csv_path is returned as a constructed path for callers that may want to
    write CSV data, but the file is NOT created here — callers own that decision.
    """
    if cfg is None:
        cfg = ConfigService().load()

    session_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
    base_dir = getattr(cfg, "SESSIONS_BASE_DIR", None)
    base = base_dir if base_dir else os.getcwd()
    session_folder = os.path.join(base, "Sessions", session_id)
    unknowns_dir = os.path.join(session_folder, "Unknowns")

    os.makedirs(unknowns_dir, exist_ok=True)

    # Constructed path — caller writes to it if needed. Not created here.
    csv_path = os.path.join(session_folder, f"attendance_{session_id}.csv")

    return session_folder, unknowns_dir, csv_path