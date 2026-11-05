"""Selectable OCR text at its original position on an image."""
import math
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFontMetricsF, QPainter
from PySide6.QtWidgets import QApplication, QLabel, QMenu


class SelectableImage(QLabel):
    selectionChanged = Signal(str)

    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.text_content = ''
        self.words = []
        self.source_size = (1, 1)
        self.anchor = None
        self.position = None
        self.dragging = False

    def set_ocr(self, text, words, source_size):
        self.text_content = text
        self.words = words
        self.source_size = source_size
        self.clear_selection()

    def clear_selection(self):
        self.anchor = self.position = None
        self.selectionChanged.emit('')
        self.update()

    def selected_text(self):
        if self.anchor is None or self.position is None:
            return ''
        start, end = sorted((self.anchor, self.position))
        return self.text_content[start:end]

    def word_rect(self, word):
        sx = self.width() / self.source_size[0]
        sy = self.height() / self.source_size[1]
        return QRectF(word['x'] * sx, word['y'] * sy, word['width'] * sx, word['height'] * sy)

    def boundaries(self, word):
        text = self.text_content[word['start']:word['end']]
        metrics = QFontMetricsF(self.font())
        widths = [metrics.horizontalAdvance(text[:index]) for index in range(len(text) + 1)]
        total = widths[-1] if widths else 0
        return [width / total for width in widths] if total else [0]

    def hit_position(self, point, nearest=False):
        best = None
        distance = math.inf
        for word in self.words:
            rect = self.word_rect(word)
            dx = max(rect.left() - point.x(), 0, point.x() - rect.right())
            dy = max(rect.top() - point.y(), 0, point.y() - rect.bottom())
            score = dx * dx + dy * dy
            if score < distance:
                distance, best = score, word
        if best is None or (distance > 4 and not nearest):
            return None
        rect = self.word_rect(best)
        ratio = max(0, min(1, (point.x() - rect.left()) / max(1, rect.width())))
        boundary = min(enumerate(self.boundaries(best)), key=lambda pair: abs(pair[1] - ratio))[0]
        return best['start'] + boundary

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.selected_text():
            return
        painter = QPainter(self)
        start, end = sorted((self.anchor, self.position))
        for word in self.words:
            left, right = max(start, word['start']), min(end, word['end'])
            if left >= right:
                continue
            rect = self.word_rect(word)
            offsets = self.boundaries(word)
            x1, x2 = offsets[left - word['start']], offsets[right - word['start']]
            painter.fillRect(QRectF(rect.left() + x1 * rect.width(), rect.top(),
                                    (x2 - x1) * rect.width(), rect.height()), QColor(70, 125, 245, 105))
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus()
            self.anchor = self.position = self.hit_position(event.position())
            self.dragging = self.anchor is not None
            self.selectionChanged.emit(self.selected_text())
            self.update()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.dragging:
            self.position = self.hit_position(event.position(), nearest=True)
            self.selectionChanged.emit(self.selected_text())
            self.update()
        else:
            self.setCursor(Qt.CursorShape.IBeamCursor if self.hit_position(event.position()) is not None else Qt.CursorShape.ArrowCursor)
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.dragging:
            self.position = self.hit_position(event.position(), nearest=True)
            self.dragging = False
            self.selectionChanged.emit(self.selected_text())
            self.update()
        event.accept()

    def mouseDoubleClickEvent(self, event):
        position = self.hit_position(event.position())
        if position is not None:
            for word in self.words:
                if word['start'] <= position <= word['end']:
                    self.anchor, self.position = word['start'], word['end']
                    self.dragging = False
                    self.selectionChanged.emit(self.selected_text())
                    self.update()
                    break
        event.accept()

    def select_all(self):
        self.anchor, self.position = 0, len(self.text_content)
        self.selectionChanged.emit(self.selected_text())
        self.update()

    def copy_selection(self):
        if self.selected_text():
            QApplication.clipboard().setText(self.selected_text())

    def keyPressEvent(self, event):
        from PySide6.QtGui import QKeySequence
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy_selection()
        elif event.matches(QKeySequence.StandardKey.SelectAll):
            self.select_all()
        elif event.key() == Qt.Key.Key_Escape:
            self.clear_selection()
        else:
            super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        from localization import tr
        menu = QMenu(self)
        copy = menu.addAction(tr('Copia testo'), self.copy_selection)
        copy.setEnabled(bool(self.selected_text()))
        menu.addAction(tr('Seleziona tutto'), self.select_all)
        menu.exec(event.globalPos())
