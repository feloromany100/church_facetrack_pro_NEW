"""
DEPRECATED: use facetrack.data.faiss_repository.FaissRepository.

This module remains as a thin compatibility wrapper so existing imports keep
working while filesystem logic is moved into the data layer.
"""

from typing import Any, List, Optional, Tuple

from facetrack.data.faiss_repository import FaissRepository
from facetrack.services.config_service import ConfigService


def load_database(app, cfg=None) -> Tuple[Optional[Any], List[str], Optional[Any]]:
    if cfg is None:
        cfg = ConfigService().load()
    repo = FaissRepository(cfg)
    art = repo.load(app)
    return art.index, art.labels, art.gpu_resources
