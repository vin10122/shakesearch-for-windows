import os
import unittest
from unittest.mock import Mock, patch
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from overlay import AnimatedScreenOverlay


class ScreenTextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.guard = patch('overlay.AnimatedScreenOverlay.start_text_recognition').start()
        self.addCleanup(patch.stopall)
        image = QPixmap(1200, 800)
        image.fill('white')
        self.manager = Mock()
        self.overlay = AnimatedScreenOverlay(dict(pixmap=image, geometry=QRect(-600, 0, 600, 400)), self.manager)
        self.overlay.show()
        self.app.processEvents()
        self.addCleanup(self.overlay.close)
        # Native coordinates are scaled 2x relative to the logical screen.
        self.overlay.apply_screen_text(dict(text='Ciao mondo', words=[
            dict(start=0, end=4, x=40, y=400, width=160, height=60),
            dict(start=5, end=10, x=240, y=400, width=200, height=60)]))

    def test_drag_copy_directly_on_shake_overlay_without_chat_or_lens(self):
        with patch('lens_process.LensProcessClient') as lens:
            QTest.mousePress(self.overlay, Qt.MouseButton.LeftButton, pos=QPoint(21, 215))
            QTest.mouseMove(self.overlay, QPoint(219, 215))
            QTest.mouseRelease(self.overlay, Qt.MouseButton.LeftButton, pos=QPoint(219, 215))
            QTest.keyClick(self.overlay, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
            self.assertEqual(self.app.clipboard().text(), 'Ciao mondo')
            self.manager.on_confirm_crop.assert_not_called()
            lens.assert_not_called()
            self.assertIsNone(self.overlay.pending_bbox)

    def test_copy_button_and_select_all_are_available_on_overlay(self):
        self.overlay.select_all_text.click()
        self.overlay.copy_screen_text.click()
        self.assertEqual(self.app.clipboard().text(), 'Ciao mondo')
        self.manager.on_confirm_crop.assert_not_called()

    def test_area_mode_does_not_select_text(self):
        self.overlay.text_toggle.setChecked(False)
        QTest.mousePress(self.overlay, Qt.MouseButton.LeftButton, pos=QPoint(21, 215))
        QTest.mouseRelease(self.overlay, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier, pos=QPoint(219, 260))
        self.assertIsNotNone(self.overlay.pending_bbox)
        self.assertFalse(self.overlay.text_layer.selected_text())

    def test_late_ocr_after_close_is_ignored(self):
        self.overlay.close()
        self.overlay.apply_screen_text(dict(text='late', words=[]))
        self.assertEqual(self.overlay.text_layer.text_content, 'Ciao mondo')

    def test_worker_receives_original_screen_pixels(self):
        # Call the real method explicitly: no screenshot of the overlay itself.
        with patch('overlay.ScreenOcrTask') as factory:
            # The class method is patched; call its original implementation.
            original_start(self.overlay)
            data = factory.call_args.args[0]
            decoded = QPixmap()
            self.assertTrue(decoded.loadFromData(data))
            self.assertEqual(decoded.size(), self.overlay.background.size())
            factory.return_value.start.assert_called_once()


original_start = AnimatedScreenOverlay.start_text_recognition
