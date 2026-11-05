"""Packaged-app smoke check, run by the Windows build before release."""
import time


def check_screen_text():
    from PySide6.QtCore import QPoint, QRect, Qt
    from PySide6.QtGui import QFont, QPainter, QPixmap
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from overlay import AnimatedScreenOverlay
    print('CHECK: SCREEN_APP_STARTED', flush=True)
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
            status = overlay.text_status.text().lower()
            if 'lingua' in status or 'language' in status:
                print('CHECK: OCR_LANGUAGE_MISSING', flush=True)
            elif 'tempo' in status or 'timed out' in status:
                print('CHECK: OCR_TIMEOUT', flush=True)
            else:
                print('CHECK: OCR_BACKEND_FAILED', flush=True)
            raise RuntimeError('Packaged screen OCR failed')
        print('CHECK: SCREEN_OCR_WORDS_READY', flush=True)
        word = next((word for word in words if overlay.text_layer.text_content[word['start']:word['end']].upper() == 'SEARCH'), None)
        if word is None:
            print('CHECK: OCR_SEARCH_NOT_FOUND', flush=True)
            raise RuntimeError('Expected word not found')
        print('CHECK: SCREEN_WORD_FOUND', flush=True)
        rect = overlay.text_layer.word_rect(word)
        QTest.mousePress(overlay, Qt.MouseButton.LeftButton, pos=QPoint(round(rect.left()+1), round(rect.center().y())))
        QTest.mouseMove(overlay, QPoint(round(rect.right()-1), round(rect.center().y())))
        QTest.mouseRelease(overlay, Qt.MouseButton.LeftButton, pos=QPoint(round(rect.right()-1), round(rect.center().y())))
        QTest.keyClick(overlay, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
        if app.clipboard().text().upper() != 'SEARCH':
            print('CHECK: CLIPBOARD_MISMATCH', flush=True)
            raise RuntimeError('Packaged image selection/clipboard failed')
        print('CHECK: SCREEN_COPY_READY', flush=True)
        print('PASS: frozen EXE, real offline Windows OCR, selection on capture overlay, Ctrl+C', flush=True)
        return 0
    finally:
        overlay.close()
