import ctypes
from ctypes import wintypes
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

from desktop_input import (DesktopInput, ShakeDetector, WindowsShakeHotkey,
                           HOTKEY_ID, WM_HOTKEY)


class ShakeDetectorTests(unittest.TestCase):
    def test_zigzag_triggers_once_and_debounces(self):
        detector = ShakeDetector()
        samples = [detector.sample(x, 0, 10 + i * .02, 'normal')
                   for i, x in enumerate((0, 100, 0, 100, 0, 100))]
        self.assertEqual(samples, [False] * 5 + [True])
        for i, x in enumerate((0, 100, 0, 100, 0, 100)):
            self.assertFalse(detector.sample(x, 0, 10.2 + i * .02, 'normal'))

    def test_stationary_linear_and_slow_movement_do_not_trigger(self):
        for positions, interval in [([0] * 20, .02), (list(range(0, 2000, 100)), .02),
                                    ([0, 100] * 10, .2)]:
            detector = ShakeDetector()
            self.assertFalse(any(detector.sample(x, 0, 10 + i * interval, 'normal')
                                 for i, x in enumerate(positions)))

    def test_sensitivity_changes_minimum_distance(self):
        results = {}
        for sensitivity in ('low', 'normal', 'high'):
            detector = ShakeDetector()
            results[sensitivity] = any(detector.sample(x, 0, 10 + i * .02, sensitivity)
                                       for i, x in enumerate((0, 50, 0, 50, 0, 50)))
        self.assertEqual(results, {'low': False, 'normal': False, 'high': True})


class DesktopInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_gaming_mode_stops_polling_and_clears_gesture(self):
        inputs = DesktopInput(self.app)
        with patch.object(inputs.hotkey, 'start'), patch.object(inputs.hotkey, 'stop'):
            inputs.configure(True, 'high')
            inputs.start()
            self.assertTrue(inputs.timer.isActive())
            inputs.detector.points.append((1, 2, 3))
            inputs.configure(False, 'high')
            self.assertFalse(inputs.timer.isActive())
            self.assertFalse(inputs.detector.points)
            with patch('desktop_input.QCursor.pos') as cursor:
                inputs.poll()
                cursor.assert_not_called()
            inputs.configure(True, 'high')
            self.assertTrue(inputs.timer.isActive())
            inputs.stop()
            self.assertFalse(inputs.timer.isActive())

    def test_mouse_samples_emit_only_current_generation(self):
        inputs = DesktopInput(self.app)
        received = []
        inputs.shake_detected.connect(received.append)
        with patch.object(inputs.hotkey, 'start'), patch.object(inputs.hotkey, 'stop'):
            inputs.configure(True, 'normal')
            inputs.start()
            with patch('desktop_input.QCursor.pos', side_effect=[QPoint(x, 0) for x in (0, 100, 0, 100, 0, 100)]), \
                    patch('desktop_input.time.monotonic', side_effect=[10 + i * .02 for i in range(6)]):
                for _ in range(6):
                    inputs.poll()
            self.assertEqual(received, [inputs.generation])
            inputs.stop()

    def test_native_hotkey_dispatches_only_toggle_for_its_own_id(self):
        toggle = Mock()
        hotkey = WindowsShakeHotkey(self.app, toggle)
        hotkey.registered = True
        event = wintypes.MSG()
        event.message = WM_HOTKEY
        event.wParam = HOTKEY_ID
        result = hotkey.nativeEventFilter(b'windows_dispatcher_MSG', ctypes.addressof(event))
        self.assertEqual(result, (True, 0))
        toggle.assert_called_once_with()
        event.wParam = HOTKEY_ID + 1
        self.assertEqual(hotkey.nativeEventFilter(b'windows_dispatcher_MSG', ctypes.addressof(event)), (False, 0))
        self.assertEqual(toggle.call_count, 1)

    def test_registration_failure_is_reported_and_never_starts_polling(self):
        inputs = DesktopInput(self.app)
        with patch.object(inputs.hotkey, 'start', side_effect=RuntimeError('Shortcut busy')):
            with self.assertRaisesRegex(RuntimeError, 'Shortcut busy'):
                inputs.start()
        self.assertFalse(inputs.timer.isActive())
        self.assertFalse(inputs.running)
