"""Packaged-app smoke check, run by the Windows build before release."""
import time


def check_screen_text():
    from PySide6.QtCore import QPoint, QRect, Qt
    from PySide6.QtGui import QFont, QPainter, QPixmap
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from overlay import AnimatedScreenOverlay
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    image = QPixmap(1000, 500)
    image.fill('white')
    painter = QPainter(image)
    painter.setFont(QFont('Arial', 56))
    painter.setPen(Qt.GlobalColor.black)
    painter.drawText(50, 260, 'SHAKE SEARCH 123')
    painter.end()

    class Manager:
        def on_confirm_crop(self, *args):
            raise AssertionError('Copying text must not open the chat')
        def cancel(self):
            pass

    overlay = AnimatedScreenOverlay(dict(pixmap=image, geometry=QRect(0, 0, 1000, 500)), Manager())
    overlay.show()
    try:
        deadline = time.monotonic() + 55
        while time.monotonic() < deadline and not overlay.text_layer.words:
            app.processEvents()
            time.sleep(.02)
        words = overlay.text_layer.words
        if not words:
            raise RuntimeError('Packaged screen OCR failed: ' + overlay.text_status.text())
        word = next((word for word in words if overlay.text_layer.text_content[word['start']:word['end']].upper() == 'SEARCH'), None)
        if word is None:
            raise RuntimeError('Expected SEARCH in actual OCR: ' + overlay.text_layer.text_content)
        rect = overlay.text_layer.word_rect(word)
        QTest.mousePress(overlay, Qt.MouseButton.LeftButton, pos=QPoint(round(rect.left()+1), round(rect.center().y())))
        QTest.mouseMove(overlay, QPoint(round(rect.right()-1), round(rect.center().y())))
        QTest.mouseRelease(overlay, Qt.MouseButton.LeftButton, pos=QPoint(round(rect.right()-1), round(rect.center().y())))
        QTest.keyClick(overlay, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
        if app.clipboard().text().upper() != 'SEARCH':
            raise RuntimeError('Packaged image selection/clipboard failed: ' + app.clipboard().text())
        print('PASS: frozen EXE, real offline Windows OCR, selection on capture overlay, Ctrl+C', flush=True)
        return 0
    finally:
        overlay.close()
