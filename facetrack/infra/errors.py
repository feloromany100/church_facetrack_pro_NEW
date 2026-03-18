from __future__ import annotations

import sys

# StrEnum was added in Python 3.11.  For earlier versions we build a compatible
# shim that makes enum members compare equal to their string values.
if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from enum import Enum

    class StrEnum(str, Enum):
        """Backport-compatible StrEnum: members ARE strings (str subclass)."""

        def __str__(self) -> str:
            return self.value

        def __repr__(self) -> str:
            return f"{type(self).__name__}.{self.name}"


class ErrorCode(StrEnum):
    CAMERA_CONNECT_FAIL  = "CAMERA_CONNECT_FAIL"
    MODEL_INIT_FAIL      = "MODEL_INIT_FAIL"
    FAISS_LOAD_FAIL      = "FAISS_LOAD_FAIL"
    FAISS_REBUILD_FAIL   = "FAISS_REBUILD_FAIL"
    QUEUE_OVERFLOW       = "QUEUE_OVERFLOW"
    FRAME_PROCESS_FAIL   = "FRAME_PROCESS_FAIL"
    CONFIG_LOAD_FAIL     = "CONFIG_LOAD_FAIL"
    IO_WRITE_FAIL        = "IO_WRITE_FAIL"
