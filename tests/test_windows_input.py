"""Native Windows integration, including actual Alt+F7 key injection."""
import ctypes
from ctypes import wintypes
import os
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app_settings import save_preferences
from desktop_input import WindowsShakeHotkey, verify_native_hotkey, VK_F7
from shakesearch import ShakeSearch


@unittest.skipUnless(os.name == 'nt', 'Requires Windows native message dispatch')
class WindowsInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_real_registration_and_message_delivery(self):
        verify_native_hotkey()

    def test_conflicting_shortcut_reports_error_then_can_be_registered_again(self):
        first = WindowsShakeHotkey(self.app, lambda: None)
        second = WindowsShakeHotkey(self.app, lambda: None)
        first.start()
        try:
            # A second registration on another native thread must conflict.
            import threading
            errors = []
            def register_on_other_thread():
                import ctypes
                api = ctypes.WinDLL('user32', use_last_error=True)
                if not api.RegisterHotKey(None, 0x5349, 0x4001, VK_F7):
                    errors.append(ctypes.get_last_error())
                else:
                    api.UnregisterHotKey(None, 0x5349)
            thread = threading.Thread(target=register_on_other_thread)
            thread.start()
            thread.join(timeout=5)
            self.assertEqual(errors, [1409])
        finally:
            first.stop()
        second.start()
        second.stop()

    def test_actual_alt_f7_toggles_without_capture_and_does_not_repeat(self):
        api = ctypes.WinDLL('user32', use_last_error=True)
        api.GetForegroundWindow.restype = wintypes.HWND
        if not api.GetForegroundWindow():
            self.skipTest('Runner has no foreground desktop for keyboard injection')
        api.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_size_t]
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'LOCALAPPDATA': directory}):
            save_preferences('en', True, 'normal', 'balanced')
            controller = ShakeSearch(self.app)
            # Exercise OS registration/dispatch without sampling a CI user's mouse.
            controller.inputs.hotkey.start()
            try:
                with patch.object(controller, '_request_capture') as capture:
                    api.keybd_event(0x12, 0, 0, 0)
                    api.keybd_event(VK_F7, 0, 0, 0)
                    QTest.qWait(150)
                    self.assertFalse(controller.options['shake_enabled'])
                    api.keybd_event(VK_F7, 0, 0, 0)
                    QTest.qWait(100)
                    self.assertFalse(controller.options['shake_enabled'])
                    api.keybd_event(VK_F7, 0, 2, 0)
                    api.keybd_event(0x12, 0, 2, 0)
                    QTest.qWait(50)
                    api.keybd_event(0x12, 0, 0, 0)
                    api.keybd_event(VK_F7, 0, 0, 0)
                    QTest.qWait(150)
                    self.assertTrue(controller.options['shake_enabled'])
                    capture.assert_not_called()
            finally:
                api.keybd_event(VK_F7, 0, 2, 0)
                api.keybd_event(0x12, 0, 2, 0)
                controller.inputs.stop()
