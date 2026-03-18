"""
facetrack/infra/model_factory.py

Shared factory for InsightFace FaceAnalysis instantiation.

Consolidates the "walk provider list, fall back to CPU" logic that was
previously duplicated between frame_processor.py and indexing_service.py.

Usage
-----
    from facetrack.infra.model_factory import build_face_analysis_app
    app = build_face_analysis_app(cfg, label="cam-0")
    # app is a ready-to-use insightface.app.FaceAnalysis, or None on failure.

Each caller that needs its own inference session should call this function
independently — InsightFace ONNX sessions are NOT thread-safe for concurrent
.get() calls, so every thread/process must own its own instance.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def build_face_analysis_app(cfg: Any, label: str = "") -> Optional[Any]:
    """
    Construct and prepare a ``FaceAnalysis`` application object.

    Parameters
    ----------
    cfg:
        Application config object (``SimpleNamespace`` or typed model).
        Must expose ``EXECUTION_PROVIDERS`` and ``DETECTION_SIZE``.
    label:
        Human-readable identifier used in log messages (e.g. ``"cam-0"``
        or ``"indexer"``).

    Returns
    -------
    Initialised ``FaceAnalysis`` app, or ``None`` if all providers failed.
    """
    prefix = f"[{label}] " if label else ""

    # 1. Discover which ONNX providers are actually installed
    try:
        import onnxruntime as ort
        available: set = set(ort.get_available_providers())
    except Exception as exc:
        logger.warning("%sonnxruntime unavailable (%s) — falling back to CPU", prefix, exc)
        available = {"CPUExecutionProvider"}

    configured = list(getattr(cfg, "EXECUTION_PROVIDERS", ["CPUExecutionProvider"]))

    # Always keep CPU in the chain as the final fallback
    if "CPUExecutionProvider" not in configured:
        configured.append("CPUExecutionProvider")

    det_size = tuple(getattr(cfg, "DETECTION_SIZE", (640, 640)))

    # 2. Build candidate provider sets:  [GPU + CPU] first, then [CPU only]
    candidate_sets = []
    gpu_providers = [p for p in configured if p in available and p != "CPUExecutionProvider"]
    if gpu_providers:
        candidate_sets.append(gpu_providers + ["CPUExecutionProvider"])
    candidate_sets.append(["CPUExecutionProvider"])

    # 3. Try each candidate set in order
    from insightface.app import FaceAnalysis
    for providers in candidate_sets:
        try:
            # Suppress the low-level ORT C++ stderr spam that appears when a
            # GPU provider DLL is absent.  Python-level warnings still fire via
            # the logger so our own logs remain clean.
            import os as _os
            _prev = _os.environ.get("ORT_LOGGING_LEVEL")
            _os.environ["ORT_LOGGING_LEVEL"] = "3"   # 3 = ERROR (hides warnings)
            try:
                app = FaceAnalysis(name="buffalo_l", providers=providers)
                app.prepare(ctx_id=0, det_size=det_size)
            finally:
                if _prev is None:
                    _os.environ.pop("ORT_LOGGING_LEVEL", None)
                else:
                    _os.environ["ORT_LOGGING_LEVEL"] = _prev

            logger.info("%sInsightFace ready  providers=%s", prefix, providers)
            return app
        except Exception as exc:
            logger.warning(
                "%sInsightFace failed with providers=%s: %s — trying next",
                prefix, providers, exc,
            )

    logger.error("%sInsightFace could not initialise with any provider", prefix)
    return None
