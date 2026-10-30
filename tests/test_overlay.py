"""Run with QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v."""
import os
import threading
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from overlay import ANIMATION_MS, FRAME_INTERVAL_MS, AnimatedScreenOverlay, plasma_state
from shakesearch import MultiScreenOverlayManager, ShakeSearch


class OverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        pixmap = QPixmap(1280, 960)
        pixmap.fill(QColor('#456789'))
        pixmap.setDevicePixelRatio(2)
        self.data = dict(pixmap=pixmap, geometry=QRect(-640, 0, 640, 480),
                         work_area=QRect(-640, 0, 640, 450))
        self.manager = Mock()
        self.overlay = AnimatedScreenOverlay(self.data, self.manager)
        self.overlay.show()
        self.app.processEvents()

    def tearDown(self):
        self.overlay.close()
        self.app.processEvents()

    def test_animation_travels_in_out_and_settles(self):
        self.assertEqual(plasma_state(0), (1, 1))
        self.assertEqual(plasma_state(.4), (.04, 1))
        self.assertAlmostEqual(plasma_state(.88)[0], 1)
        self.assertEqual(plasma_state(1), (1, 0))
        sizes = []
        for progress in (0, .2, .4, .65, .88, 1):
            self.overlay.progress = progress
            radius, _ = plasma_state(progress)
            sizes.append(self.overlay.plasma_path(radius, 0).boundingRect().width())
            # Exercise the actual Qt paint event, not just geometry calculations.
            image = self.overlay.grab().toImage()
            self.assertFalse(image.isNull())
            if progress == 1:
                self.assertGreater(image.pixelColor(2, 240).red(), 200)
                interior = image.pixelColor(35, 240)
                self.assertLess(interior.red(), 100)  # no orange halo remains
        self.assertGreater(sizes[0], sizes[1])
        self.assertGreater(sizes[1], sizes[2])
        self.assertGreater(sizes[3], sizes[2])
        self.assertGreater(sizes[4], sizes[3])

    def select(self):
        QTest.mousePress(self.overlay, Qt.MouseButton.LeftButton, pos=QPoint(100, 120))
        QTest.mouseMove(self.overlay, QPoint(200, 220))
        QTest.mouseRelease(self.overlay, Qt.MouseButton.LeftButton, pos=QPoint(200, 220))

    def test_crop_uses_native_pixels_and_enter_confirms(self):
        self.select()
        image = self.overlay.selected_image()
        self.assertEqual(image.size, (200, 200))
        self.assertEqual(image.getpixel((0, 0)), (69, 103, 137, 255))
        QTest.keyClick(self.overlay, Qt.Key.Key_Return)
        self.manager.on_confirm_crop.assert_called_once()
        self.assertIs(self.manager.on_confirm_crop.call_args.args[1], self.data)

    def test_escape_clears_selection_then_cancels(self):
        self.select()
        QTest.keyClick(self.overlay, Qt.Key.Key_Escape)
        self.assertIsNone(self.overlay.pending_bbox)
        self.manager.cancel.assert_not_called()
        QTest.keyClick(self.overlay, Qt.Key.Key_Escape)
        self.manager.cancel.assert_called_once()

    def test_animation_settles_but_border_keeps_moving(self):
        self.overlay.start_animation()
        QTest.qWait(ANIMATION_MS + 100)
        self.assertTrue(self.overlay.timer.isActive())
        self.assertEqual(self.overlay.progress, 1)
        phase = self.overlay.border_phase
        before = self.overlay.grab().toImage()
        QTest.qWait(150)
        self.assertNotEqual(self.overlay.border_phase, phase)
        after = self.overlay.grab().toImage()
        self.assertNotEqual(before, after)
        self.assertEqual(before.copy(20, 80, 600, 300), after.copy(20, 80, 600, 300))
        self.assertLess(FRAME_INTERVAL_MS, 8)

    def test_close_stops_continuous_animation(self):
        self.overlay.start_animation()
        self.overlay.close()
        self.assertFalse(self.overlay.timer.isActive())

    def test_input_signal_runs_on_gui_thread(self):
        controller = ShakeSearch(self.app)
        calls = []
        with patch.object(controller, 'capture_all_screens', side_effect=lambda: calls.append(threading.get_ident()) or [self.data]), patch('shakesearch.MultiScreenOverlayManager'):
            thread = threading.Thread(target=controller.on_hotkey_triggered)
            thread.start()
            thread.join()
            QTest.qWait(50)
        self.assertEqual(calls, [threading.get_ident()])

    def test_multi_monitor_session_closes_every_window(self):
        other = dict(self.data, geometry=QRect(0, 0, 640, 480))
        finished = Mock()
        manager = MultiScreenOverlayManager([self.data, other], finished)
        self.app.processEvents()
        self.assertEqual(len(manager.overlays), 2)
        self.assertTrue(all(o.isVisible() and o.timer.isActive() for o in manager.overlays))
        manager.cancel()
        self.assertEqual(manager.overlays, [])
        finished.assert_called_once()


if __name__ == '__main__':
    unittest.main()
