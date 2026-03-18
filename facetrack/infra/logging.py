from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional


_LOGGING_INITIALIZED = False


@dataclass(frozen=True)
class LoggingConfig:
    level: int = logging.INFO
    json: bool = False


class _ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Ensure structured fields exist for all records.
        if not hasattr(record, "camera_id"):
            record.camera_id = None
        if not hasattr(record, "session_id"):
            record.session_id = None
        if not hasattr(record, "error_code"):
            record.error_code = None
        return True


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "message": record.getMessage(),
        }
        if getattr(record, "camera_id", None) is not None:
            payload["camera_id"] = record.camera_id
        if getattr(record, "session_id", None) is not None:
            payload["session_id"] = record.session_id
        if getattr(record, "error_code", None) is not None:
            payload["error_code"] = record.error_code

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


def setup_logging(config: Optional[LoggingConfig] = None) -> None:
    """
    Central logging setup (call once at startup).

    Structured fields supported in all logs:
    - camera_id
    - session_id
    - error_code
    """
    global _LOGGING_INITIALIZED
    if _LOGGING_INITIALIZED:
        return

    cfg = config or LoggingConfig(
        level=logging.INFO,
        json=os.environ.get("FACETRACK_LOG_JSON", "").strip().lower() in {"1", "true", "yes"},
    )

    root = logging.getLogger()
    root.setLevel(cfg.level)

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_ContextFilter())

    if cfg.json:
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s [%(levelname)s] %(name)s"
                " cam=%(camera_id)s session=%(session_id)s code=%(error_code)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    # Replace any existing handlers (prevents duplicate logs).
    root.handlers.clear()
    root.addHandler(handler)
    _LOGGING_INITIALIZED = True


def bind_logger(
    logger: logging.Logger,
    *,
    camera_id: Optional[int] = None,
    session_id: Optional[str] = None,
) -> logging.LoggerAdapter:
    """
    Return a logger adapter that injects context fields into all log records.
    """
    extra = {"camera_id": camera_id, "session_id": session_id}
    return logging.LoggerAdapter(logger, extra)

