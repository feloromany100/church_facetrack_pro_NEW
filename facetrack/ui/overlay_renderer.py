from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional, Tuple


@dataclass(frozen=True)
class OverlayStyle:
    known_color_bgr: Tuple[int, int, int] = (0, 255, 0)
    unknown_color_bgr: Tuple[int, int, int] = (0, 0, 255)
    thickness: int = 2


def _get(det: Any, key: str, default=None):
    if isinstance(det, dict):
        return det.get(key, default)
    return getattr(det, key, default)


def _build_label(name: str, confidence: float, quality: float,
                 track_id: Any, is_unknown: bool,
                 show_quality: bool, show_track_id: bool) -> str:
    """Assemble the overlay label string respecting display settings."""
    if is_unknown:
        parts = ["Unknown"]
    else:
        parts = [name, f"{int(confidence * 100)}%"]

    if show_quality and quality > 0:
        parts.append(f"Q:{quality:.2f}")

    if show_track_id and track_id is not None:
        parts.append(f"#{track_id}")

    return "  ".join(parts)


def draw_cv2(frame_bgr, detections: Iterable[Any],
             style: Optional[OverlayStyle] = None,
             show_quality: bool = True,
             show_track_id: bool = True):
    """
    Draw overlays on an OpenCV BGR frame and return it.
    """
    import cv2

    st = style or OverlayStyle()
    out = frame_bgr
    for det in detections or []:
        bbox = _get(det, "bbox")
        if not bbox:
            continue
        x1, y1, x2, y2 = bbox
        name = _get(det, "name", "Unknown")
        score = float(_get(det, "score", 0.0) or 0.0)
        confidence = float(_get(det, "confidence", score) or 0.0)
        quality = float(_get(det, "quality", 0.0) or 0.0)
        track_id = _get(det, "track_id")
        is_unknown = bool(_get(det, "is_unknown", False)) or (
            isinstance(name, str) and name.startswith("Unknown")
        )

        color = st.unknown_color_bgr if is_unknown else st.known_color_bgr
        cv2.rectangle(out, (x1, y1), (x2, y2), color, st.thickness)

        label = _build_label(name, confidence, quality, track_id,
                             is_unknown, show_quality, show_track_id)
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(out, (x1, max(0, y1 - th - 10)), (x1 + tw + 6, y1), color, -1)
        cv2.putText(out, label, (x1 + 3, y1 - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    return out


def draw_qt(
    painter,
    detections: Iterable[Any],
    *,
    frame_size: Tuple[int, int],
    widget_size: Tuple[int, int],
    colors: Optional[dict] = None,
    show_quality: bool = True,
    show_track_id: bool = True,
):
    """
    Draw overlays using a QPainter. Keeps style consistent with headless overlays.
    """
    from PySide6.QtGui import QColor, QPen, QFont
    from PySide6.QtCore import Qt

    fw, fh = frame_size
    ww, wh = widget_size
    sx = ww / max(fw, 1)
    sy = wh / max(fh, 1)

    known = QColor("#00ff7f")
    unknown = QColor("#ff3b30")
    if colors:
        known = QColor(colors.get("known", known.name()))
        unknown = QColor(colors.get("unknown", unknown.name()))

    painter.setRenderHint(painter.RenderHint.Antialiasing)

    for det in detections or []:
        bbox = _get(det, "bbox")
        if not bbox:
            continue
        x1, y1, x2, y2 = bbox
        rx1, ry1 = int(x1 * sx), int(y1 * sy)
        rx2, ry2 = int(x2 * sx), int(y2 * sy)

        name = _get(det, "name", "Unknown")
        confidence = float(_get(det, "confidence", _get(det, "score", 0.0)) or 0.0)
        quality = float(_get(det, "quality", 0.0) or 0.0)
        track_id = _get(det, "track_id")
        is_unknown = bool(_get(det, "is_unknown", False)) or (
            isinstance(name, str) and name.startswith("Unknown")
        )

        color = unknown if is_unknown else known
        pen = QPen(color, 2)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rx1, ry1, rx2 - rx1, ry2 - ry1, 4, 4)

        label = _build_label(name, confidence, quality, track_id,
                             is_unknown, show_quality, show_track_id)
        painter.setFont(QFont("Helvetica Neue", 10, QFont.Weight.Bold))
        fm = painter.fontMetrics()
        lw = fm.horizontalAdvance(label) + 12
        lh = fm.height() + 6
        lx, ly = rx1, max(0, ry1 - lh - 2)
        bg = QColor(color)
        bg.setAlpha(220)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg)
        painter.drawRoundedRect(lx, ly, lw, lh, 4, 4)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(lx + 6, ly + lh - 5, label)