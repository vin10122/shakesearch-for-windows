"""Local, conservative rectangle snapping against the original screen pixels."""
import logging
import math

from PySide6.QtCore import QObject, QRunnable, QRectF, Signal
from PySide6.QtGui import QImage

logger = logging.getLogger('shakesearch')


def find_rectangle(image, selection, view_size):
    """Return a nearby axis-aligned rectangle in logical pixels, or None.

    Inspect only the selected neighbourhood. Require four rectangular sides,
    substantial overlap and nearby edges so unrelated UI elements are ignored.
    """
    import cv2
    import numpy as np

    view_width, view_height = view_size
    sx, sy = image.width() / view_width, image.height() / view_height
    tx = min(128, max(18, selection.width() * .22))
    ty = min(128, max(18, selection.height() * .22))
    left = max(0, math.floor((selection.left() - tx - 12) * sx))
    top = max(0, math.floor((selection.top() - ty - 12) * sy))
    right = min(image.width(), math.ceil((selection.right() + tx + 12) * sx))
    bottom = min(image.height(), math.ceil((selection.bottom() + ty + 12) * sy))
    if right - left < 24 or bottom - top < 24:
        return None
    region = image.copy(left, top, right - left, bottom - top)
    region = region.convertToFormat(QImage.Format.Format_RGBA8888)
    pixels = np.frombuffer(region.constBits(), dtype=np.uint8)
    pixels = pixels.reshape(region.height(), region.bytesPerLine())
    pixels = pixels[:, :region.width() * 4].reshape(region.height(), region.width(), 4)
    scale = min(1.0, 1000 / max(region.width(), region.height()))
    width, height = round(region.width() * scale), round(region.height() * scale)
    if scale < 1:
        pixels = cv2.resize(pixels, (width, height), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(pixels, cv2.COLOR_RGBA2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(gray, 20, 60)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    best, best_score = None, .60
    for contour in contours:
        perimeter = cv2.arcLength(contour, True)
        if perimeter < 60:
            continue
        corners = cv2.approxPolyDP(contour, .025 * perimeter, True)
        if len(corners) != 4 or not cv2.isContourConvex(corners):
            continue
        points = corners.reshape(4, 2).astype(float)
        sides = np.roll(points, -1, axis=0) - points
        # Reject rotated rectangles and irregular quadrilaterals.
        if np.any(np.min(np.abs(sides), axis=1) > .15 * np.max(np.abs(sides), axis=1)):
            continue
        x, y, w, h = cv2.boundingRect(contour)
        if x <= 1 or y <= 1 or x + w >= width - 1 or y + h >= height - 1:
            continue
        if cv2.contourArea(contour) < .78 * w * h:
            continue
        box = QRectF((left + x * region.width() / width) / sx,
                     (top + y * region.height() / height) / sy,
                     w * region.width() / width / sx,
                     h * region.height() / height / sy)
        if box.width() < 24 or box.height() < 24:
            continue
        errors = (abs(box.left() - selection.left()) / tx,
                  abs(box.right() - selection.right()) / tx,
                  abs(box.top() - selection.top()) / ty,
                  abs(box.bottom() - selection.bottom()) / ty)
        if max(errors) > 1:
            continue
        intersection = box.intersected(selection)
        overlap = intersection.width() * intersection.height()
        union = box.width() * box.height() + selection.width() * selection.height() - overlap
        iou = overlap / union if union else 0
        if iou < .55:
            continue
        score = .65 * iou + .35 * (1 - sum(errors) / 4)
        if score > best_score:
            best, best_score = box, score
    return best


class SnapSignals(QObject):
    finished = Signal(int, object)


class RectangleSnapTask(QRunnable):
    def __init__(self, token, image, selection, view_size):
        super().__init__()
        self.token = token
        self.image = image
        self.selection = QRectF(selection)
        self.view_size = view_size
        self.signals = SnapSignals()

    def run(self):
        result = None
        try:
            result = find_rectangle(self.image, self.selection, self.view_size)
        except Exception:
            logger.exception('Rectangle detection failed; keeping free selection')
        self.signals.finished.emit(self.token, result)
