"""Run with QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v."""
import os
import threading
import time
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QPoint, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QPixmap, QPainter, QPen
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
        self.wait_for_snap()

    def wait_for_snap(self):
        for _ in range(500):
            if not self.overlay._snap_pending:
                break
            time.sleep(.01)  # Let the Python detector run while Qt events are pumped.
            self.app.processEvents()
        self.assertFalse(self.overlay._snap_pending)

    def draw_card(self):
        self.overlay.close()
        pixmap = self.data['pixmap'].copy()
        painter = QPainter(pixmap)
        painter.setPen(QPen(QColor('#eeeeee'), 2))
        painter.setBrush(QColor('#202020'))
        painter.drawRect(QRectF(100, 120, 200, 140))
        painter.end()
        self.data['pixmap'] = pixmap
        self.overlay = AnimatedScreenOverlay(self.data, self.manager)
        self.overlay.show()
        self.app.processEvents()

    def test_rough_selection_snaps_to_visible_rectangle(self):
        self.draw_card()
        QTest.mousePress(self.overlay, Qt.MouseButton.LeftButton, pos=QPoint(88, 108))
        QTest.mouseRelease(self.overlay, Qt.MouseButton.LeftButton, pos=QPoint(312, 272))
        self.wait_for_snap()
        self.assertTrue(self.overlay.snapped)
        box = self.overlay.pending_bbox
        for actual, expected in zip((box.left(), box.top(), box.right(), box.bottom()), (100, 120, 300, 260)):
            self.assertAlmostEqual(actual, expected, delta=3)
        QTest.keyClick(self.overlay, Qt.Key.Key_Return)
        self.manager.on_confirm_crop.assert_called_once()

    def test_shift_keeps_selection_free(self):
        self.draw_card()
        QTest.mousePress(self.overlay, Qt.MouseButton.LeftButton, pos=QPoint(88, 108))
        QTest.mouseRelease(self.overlay, Qt.MouseButton.LeftButton,
                           Qt.KeyboardModifier.ShiftModifier, pos=QPoint(312, 272))
        self.assertFalse(self.overlay._snap_pending)
        self.assertFalse(self.overlay.snapped)
        self.assertEqual(self.overlay.pending_bbox, QRectF(88, 108, 224, 164))

    def test_enter_waits_for_alignment_before_confirming(self):
        release = threading.Event()

        def delayed(*args):
            release.wait(2)
            return QRectF(95, 115, 110, 110)

        with patch('rectangle_snap.find_rectangle', side_effect=delayed):
            QTest.mousePress(self.overlay, Qt.MouseButton.LeftButton, pos=QPoint(100, 120))
            QTest.mouseRelease(self.overlay, Qt.MouseButton.LeftButton, pos=QPoint(200, 220))
            QTest.keyClick(self.overlay, Qt.Key.Key_Return)
            self.manager.on_confirm_crop.assert_not_called()
            release.set()
            self.wait_for_snap()
        self.manager.on_confirm_crop.assert_called_once()
        self.assertEqual(self.manager.on_confirm_crop.call_args.args[0].size, (220, 220))

    def test_old_detection_cannot_replace_new_selection(self):
        release = threading.Event()

        def delayed(*args):
            release.wait(2)
            return QRectF(95, 115, 110, 110)

        with patch('rectangle_snap.find_rectangle', side_effect=delayed):
            QTest.mousePress(self.overlay, Qt.MouseButton.LeftButton, pos=QPoint(100, 120))
            QTest.mouseRelease(self.overlay, Qt.MouseButton.LeftButton, pos=QPoint(200, 220))
            QTest.mousePress(self.overlay, Qt.MouseButton.LeftButton, pos=QPoint(300, 300))
            QTest.mouseRelease(self.overlay, Qt.MouseButton.LeftButton,
                               Qt.KeyboardModifier.ShiftModifier, pos=QPoint(400, 400))
            release.set()
            for _ in range(200):
                time.sleep(.01)
                self.app.processEvents()
                if not self.overlay._snap_tasks:
                    break
        self.assertFalse(self.overlay._snap_tasks)
        self.assertEqual(self.overlay.pending_bbox, QRectF(300, 300, 100, 100))
        self.assertFalse(self.overlay.snapped)

    def test_crop_uses_native_pixels_and_enter_confirms(self):
        self.select()
        image = self.overlay.selected_image()
        self.assertEqual(image.size, (200, 200))
        self.assertEqual(image.getpixel((0, 0)), (69, 103, 137, 255))
        QTest.keyClick(self.overlay, Qt.Key.Key_Return)
        self.manager.on_confirm_crop.assert_called_once()
        self.assertIs(self.manager.on_confirm_crop.call_args.args[1], self.data)

    def test_all_edges_and_corners_can_be_refined_before_confirmation(self):
        self.select()
        cases = (
            ((100, 170), (90, 170), (90, 120, 110, 100)),
            ((200, 170), (215, 170), (100, 120, 115, 100)),
            ((150, 120), (150, 110), (100, 110, 100, 110)),
            ((150, 220), (150, 235), (100, 120, 100, 115)),
            ((100, 120), (90, 110), (90, 110, 110, 110)),
            ((200, 120), (215, 110), (100, 110, 115, 110)),
            ((200, 220), (215, 235), (100, 120, 115, 115)),
            ((100, 220), (90, 235), (90, 120, 110, 115)),
        )
        for start, end, expected in cases:
            with self.subTest(start=start):
                self.overlay.pending_bbox = QRectF(100, 120, 100, 100)
                QTest.mousePress(self.overlay, Qt.MouseButton.LeftButton, pos=QPoint(*start))
                QTest.mouseMove(self.overlay, QPoint(*end))
                QTest.mouseRelease(self.overlay, Qt.MouseButton.LeftButton, pos=QPoint(*end))
                self.assertEqual(self.overlay.pending_bbox, QRectF(*expected))
                self.assertEqual(self.overlay.selected_image().size, (expected[2] * 2, expected[3] * 2))
                self.assertFalse(self.overlay._snap_pending)
                self.manager.on_confirm_crop.assert_not_called()
        QTest.keyClick(self.overlay, Qt.Key.Key_Return)
        self.manager.on_confirm_crop.assert_called_once()
        self.assertEqual(self.manager.on_confirm_crop.call_args.args[0].size, (220, 230))

    def test_refinement_is_clamped_to_screen_and_minimum_size(self):
        self.select()
        QTest.mousePress(self.overlay, Qt.MouseButton.LeftButton, pos=QPoint(100, 120))
        QTest.mouseRelease(self.overlay, Qt.MouseButton.LeftButton, pos=QPoint(-50, -50))
        self.assertEqual(self.overlay.pending_bbox, QRectF(0, 0, 200, 220))
        QTest.mousePress(self.overlay, Qt.MouseButton.LeftButton, pos=QPoint(200, 220))
        QTest.mouseRelease(self.overlay, Qt.MouseButton.LeftButton, pos=QPoint(800, 700))
        self.assertEqual(self.overlay.pending_bbox, QRectF(0, 0, 640, 480))
        QTest.mousePress(self.overlay, Qt.MouseButton.LeftButton, pos=QPoint(640, 480))
        QTest.mouseRelease(self.overlay, Qt.MouseButton.LeftButton, pos=QPoint(-50, -50))
        self.assertEqual(self.overlay.pending_bbox, QRectF(0, 0, 25, 25))

    def test_manual_refinement_wins_over_in_flight_snap(self):
        release = threading.Event()

        def delayed(*args):
            release.wait(2)
            return QRectF(95, 115, 110, 110)

        with patch('rectangle_snap.find_rectangle', side_effect=delayed):
            QTest.mousePress(self.overlay, Qt.MouseButton.LeftButton, pos=QPoint(100, 120))
            QTest.mouseRelease(self.overlay, Qt.MouseButton.LeftButton, pos=QPoint(200, 220))
            QTest.mousePress(self.overlay, Qt.MouseButton.LeftButton, pos=QPoint(200, 170))
            QTest.mouseRelease(self.overlay, Qt.MouseButton.LeftButton, pos=QPoint(230, 170))
            release.set()
            for _ in range(200):
                time.sleep(.01)
                self.app.processEvents()
                if not self.overlay._snap_tasks:
                    break
        self.assertFalse(self.overlay._snap_tasks)
        self.assertEqual(self.overlay.pending_bbox, QRectF(100, 120, 130, 100))

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
