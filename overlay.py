"""Qt screen selection and orange perimeter-to-center-to-perimeter animation."""
import math

from PIL import Image
from PySide6.QtCore import Qt, QRectF, QPointF, QElapsedTimer, QTimer, QThreadPool, Slot
from PySide6.QtGui import QColor, QConicalGradient, QImage, QPainter, QPainterPath, QPen, QFont, QRegion
from PySide6.QtWidgets import QWidget
from rectangle_snap import RectangleSnapTask

AMBER = QColor('#ff944d')
ANIMATION_MS = 2800
FRAME_INTERVAL_MS = 7  # About 144 updates/s; actual presentation depends on the display.
MIN_SELECTION_SIZE = 25


def plasma_state(progress):
    """Return normalized radius and glow strength; settled state is border only."""
    progress = max(0.0, min(1.0, progress))
    ease = lambda t: t * t * t * (t * (t * 6 - 15) + 10)
    if progress < .4:
        return 1 - .96 * ease(progress / .4), 1.0
    if progress < .48:
        return .04, 1.0
    if progress < .88:
        return .04 + .96 * ease((progress - .48) / .4), 1.0
    return 1.0, 1 - ease((progress - .88) / .12)


class AnimatedScreenOverlay(QWidget):
    def __init__(self, screen_data, manager):
        super().__init__(None, Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.manager = manager
        self.screen_data = screen_data
        self.background = screen_data['pixmap']
        self.setGeometry(screen_data['geometry'])
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.points = []
        self.drawing = False
        self.pending_bbox = None
        self._resize_edge = None
        self._resize_origin = None
        self._resize_start = None
        self.snapped = False
        self._snap_token = 0
        self._snap_pending = False
        self._confirm_after_snap = False
        self._snap_tasks = {}
        self.clock = QElapsedTimer()
        self.progress = 0.0
        self.border_phase = 0.0
        # Only the soft plasma uses a smaller surface. Screenshot, selection and
        # persistent border stay at native resolution, including on 4K monitors.
        self.plasma_scale = min(1.0, 640 / max(self.width(), self.height()))
        self.plasma_buffer = QImage(math.ceil(self.width() * self.plasma_scale),
                                   math.ceil(self.height() * self.plasma_scale),
                                   QImage.Format.Format_ARGB32_Premultiplied)
        # Cache the screenshot, dimming and caption instead of alpha-blending a
        # full desktop every frame. Native pixels remain untouched for cropping.
        self.static_background = self.background.copy()
        painter = QPainter(self.static_background)
        painter.fillRect(self.rect(), QColor(12, 8, 5, 65))
        painter.setFont(QFont('Segoe UI', 12))
        painter.setPen(Qt.GlobalColor.white)
        painter.drawText(QRectF(0, 22, self.width(), 30), Qt.AlignmentFlag.AlignCenter,
                         'Circle anything · Esc to exit')
        painter.end()
        self.border_region = QRegion(self.rect()).subtracted(
            QRegion(self.rect().adjusted(16, 16, -16, -16)))
        self.wave_samples = []
        for step in range(97):
            angle = step * math.tau / 96
            dx, dy = math.cos(angle), math.sin(angle)
            reach = 1 / max(abs(dx), abs(dy))
            self.wave_samples.append((angle, dx * reach, dy * reach))
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(FRAME_INTERVAL_MS)
        self.timer.timeout.connect(self.advance_animation)

    def start_animation(self):
        self.clock.start()
        self.timer.start()
        self.update()

    def advance_animation(self):
        was_transitioning = self.progress < 1
        self.progress = min(1.0, self.clock.elapsed() / ANIMATION_MS)
        self.border_phase = (self.clock.elapsed() / 9000) % 1
        if was_transitioning:
            self.update()
        else:
            # Once the plasma has settled, repaint only the thin perimeter.
            self.update(self.border_region)

    def plasma_path(self, radius, band):
        rect = self.rect().toRectF().adjusted(3, 3, -3, -3)
        cx, cy = rect.center().x(), rect.center().y()
        path = QPainterPath()
        for step, (angle, dx, dy) in enumerate(self.wave_samples):
            # Organic waves disappear as the returning light reaches the edges.
            wave = (math.sin(angle * 7 + self.progress * 17 + band) * .025 +
                    math.sin(angle * 13 - self.progress * 11) * .012)
            wave *= math.sin(math.pi * min(1.0, radius))
            r = max(.01, min(1.0, radius + wave + band * .012 * (1 - radius)))
            point = QPointF(cx + dx * rect.width() / 2 * r,
                            cy + dy * rect.height() / 2 * r)
            if step == 0:
                path.moveTo(point)
            else:
                path.lineTo(point)
        path.closeSubpath()
        return path

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Keep screen pixels in place; selection maps logical to physical pixels.
        painter.drawPixmap(self.rect(), self.static_background)
        radius, strength = plasma_state(self.progress)
        if strength > .001:
            self.plasma_buffer.fill(Qt.GlobalColor.transparent)
            light = QPainter(self.plasma_buffer)
            light.setRenderHint(QPainter.RenderHint.Antialiasing)
            light.scale(self.plasma_scale, self.plasma_scale)
            for band in range(3):
                path = self.plasma_path(radius, band)
                # Layer translucent strokes for a soft glow without CPU image resizes.
                for width, alpha in ((56, 6), (28, 12), (12, 24), (4, 115)):
                    color = QColor(255, 105 + band * 30, 30, round(alpha * strength))
                    pen = QPen(color, width)
                    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                    light.setPen(pen)
                    light.drawPath(path)
            light.end()
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawImage(self.rect(), self.plasma_buffer)
        gradient = QConicalGradient(QPointF(self.width() / 2, self.height() / 2),
                                    self.border_phase * 360)
        for position, color in ((0, '#ffe2b5'), (.07, '#ffc078'), (.22, '#ff944d'),
                                (.65, '#e36b21'), (.88, '#ff944d'), (1, '#ffe2b5')):
            gradient.setColorAt(position, QColor(color))
        painter.setPen(QPen(gradient, 2.5))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(2, 2, -2, -2), 12, 12)
        painter.setFont(QFont('Segoe UI', 12))
        if len(self.points) > 1 and self.drawing:
            trail = QPainterPath(self.points[0])
            for point in self.points[1:]:
                trail.lineTo(point)
            painter.setPen(QPen(QColor(255, 130, 45, 80), 10))
            painter.drawPath(trail)
            painter.setPen(QPen(AMBER, 3))
            painter.drawPath(trail)
        if self.pending_bbox is not None:
            painter.setPen(QPen(AMBER, 2, Qt.PenStyle.DashLine))
            painter.drawRect(self.pending_bbox)
            painter.setPen(QPen(AMBER, 1.5))
            painter.setBrush(QColor('#251910'))
            for point in self.selection_handles().values():
                painter.drawRoundedRect(QRectF(point.x() - 4, point.y() - 4, 8, 8), 2, 2)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            badge = QRectF(0, 0, min(400, self.width() - 24), 38)
            badge.moveCenter(QPointF(self.width() / 2, self.height() - 42))
            painter.fillRect(badge, QColor('#201610'))
            painter.setPen(Qt.GlobalColor.white)
            caption = 'Drag edges to adjust · Enter to confirm'
            if self._snap_pending:
                caption = 'Aligning selection… · Esc to retry'
            painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, caption)
        painter.end()

    def selection_handles(self):
        box = self.pending_bbox
        if box is None:
            return {}
        return {
            'lt': box.topLeft(), 'rt': box.topRight(),
            'rb': box.bottomRight(), 'lb': box.bottomLeft(),
            't': QPointF(box.center().x(), box.top()),
            'r': QPointF(box.right(), box.center().y()),
            'b': QPointF(box.center().x(), box.bottom()),
            'l': QPointF(box.left(), box.center().y()),
        }

    def resize_edge_at(self, point):
        box = self.pending_bbox
        if box is None:
            return None
        # Corners and midpoint handles have generous hit areas in logical pixels.
        handles = sorted(self.selection_handles().items(),
                         key=lambda item: (point - item[1]).manhattanLength())
        for edge, center in handles:
            if abs(point.x() - center.x()) <= 9 and abs(point.y() - center.y()) <= 9:
                return edge
        if box.top() <= point.y() <= box.bottom():
            if abs(point.x() - box.left()) <= 7:
                return 'l'
            if abs(point.x() - box.right()) <= 7:
                return 'r'
        if box.left() <= point.x() <= box.right():
            if abs(point.y() - box.top()) <= 7:
                return 't'
            if abs(point.y() - box.bottom()) <= 7:
                return 'b'
        return None

    def update_resize_cursor(self, point):
        edge = self._resize_edge or self.resize_edge_at(point)
        cursors = {'l': Qt.CursorShape.SizeHorCursor, 'r': Qt.CursorShape.SizeHorCursor,
                   't': Qt.CursorShape.SizeVerCursor, 'b': Qt.CursorShape.SizeVerCursor,
                   'lt': Qt.CursorShape.SizeFDiagCursor, 'rb': Qt.CursorShape.SizeFDiagCursor,
                   'rt': Qt.CursorShape.SizeBDiagCursor, 'lb': Qt.CursorShape.SizeBDiagCursor}
        self.setCursor(cursors.get(edge, Qt.CursorShape.CrossCursor))

    def resize_selection(self, point):
        box = QRectF(self._resize_origin)
        delta = point - self._resize_start
        if 'l' in self._resize_edge:
            box.setLeft(max(0, min(box.right() - MIN_SELECTION_SIZE, box.left() + delta.x())))
        if 'r' in self._resize_edge:
            box.setRight(min(self.width(), max(box.left() + MIN_SELECTION_SIZE, box.right() + delta.x())))
        if 't' in self._resize_edge:
            box.setTop(max(0, min(box.bottom() - MIN_SELECTION_SIZE, box.top() + delta.y())))
        if 'b' in self._resize_edge:
            box.setBottom(min(self.height(), max(box.top() + MIN_SELECTION_SIZE, box.bottom() + delta.y())))
        self.pending_bbox = box
        self.update()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.setFocus()
        edge = self.resize_edge_at(event.position())
        self.reset_snap()
        self._resize_edge = edge
        if edge is not None:
            self._resize_origin = QRectF(self.pending_bbox)
            self._resize_start = event.position()
            self.update_resize_cursor(event.position())
            self.update()
            return
        self.pending_bbox = None
        self.points = [event.position()]
        self.drawing = True
        self.update()

    def mouseMoveEvent(self, event):
        if self._resize_edge is not None:
            self.resize_selection(event.position())
        elif self.drawing:
            self.points.append(event.position())
            self.update()
        else:
            self.update_resize_cursor(event.position())

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._resize_edge is not None:
            self.resize_selection(event.position())
            self._resize_edge = None
            self.update_resize_cursor(event.position())
            # Manual refinements must not trigger another automatic snap.
            return
        if not self.drawing:
            return
        self.points.append(event.position())
        self.drawing = False
        xs, ys = [p.x() for p in self.points], [p.y() for p in self.points]
        bbox = QRectF(QPointF(min(xs), min(ys)), QPointF(max(xs), max(ys)))
        bbox = bbox.intersected(QRectF(self.rect()))
        self.pending_bbox = bbox if bbox.width() >= MIN_SELECTION_SIZE and bbox.height() >= MIN_SELECTION_SIZE else None
        if self.pending_bbox is not None and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self._snap_pending = True
            task = RectangleSnapTask(self._snap_token, self.background.toImage(),
                                     self.pending_bbox, (self.width(), self.height()))
            self._snap_tasks[self._snap_token] = task
            task.signals.finished.connect(self.apply_snap)
            QThreadPool.globalInstance().start(task)
        self.update()

    def reset_snap(self):
        # Results from an older gesture must never replace a newer selection.
        self._snap_token += 1
        self._snap_pending = False
        self._confirm_after_snap = False
        self.snapped = False

    @Slot(int, object)
    def apply_snap(self, token, rectangle):
        self._snap_tasks.pop(token, None)
        if token != self._snap_token or self.pending_bbox is None:
            return
        self._snap_pending = False
        if rectangle is not None:
            self.pending_bbox = rectangle
            self.snapped = True
        self.update()
        if self._confirm_after_snap:
            self._confirm_after_snap = False
            self.confirm_selection()

    def confirm_selection(self):
        image = self.selected_image()
        if image is not None:
            self.manager.on_confirm_crop(image, self.screen_data)

    def selected_image(self):
        if self.pending_bbox is None:
            return None
        image = self.background.toImage()
        sx, sy = image.width() / self.width(), image.height() / self.height()
        box = self.pending_bbox
        crop = image.copy(math.floor(box.left() * sx), math.floor(box.top() * sy),
                          round(box.width() * sx), round(box.height() * sy))
        crop = crop.convertToFormat(crop.Format.Format_RGBA8888)
        return Image.frombytes('RGBA', (crop.width(), crop.height()),
                               bytes(crop.constBits()), 'raw', 'RGBA', crop.bytesPerLine())

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._resize_edge is not None:
                return
            if self._snap_pending:
                self._confirm_after_snap = True
            else:
                self.confirm_selection()
        elif event.key() == Qt.Key.Key_Escape:
            if self.pending_bbox is not None:
                self._resize_edge = None
                self.setCursor(Qt.CursorShape.CrossCursor)
                self.reset_snap()
                self.pending_bbox = None
                self.points = []
                self.update()
            else:
                self.manager.cancel()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        self.reset_snap()
        self.timer.stop()
        super().closeEvent(event)
