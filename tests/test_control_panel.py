import os
import tempfile
import unittest
from unittest.mock import Mock, patch
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication, QDialog
from app_settings import preferences, save_preferences
from localization import read_settings, set_language
from control_panel import SettingsDialog, ControlPanel
from shakesearch import ShakeSearch


class ConfigurationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        environment = patch.dict(os.environ, {'LOCALAPPDATA': directory.name})
        environment.start()
        self.addCleanup(environment.stop)

    def test_first_run_save_preserves_language_and_preferences(self):
        self.assertFalse(read_settings().get('setup_complete'))
        dialog = SettingsDialog()
        dialog.shake.setChecked(False)
        dialog.animation.setCurrentIndex(dialog.animation.findData('light'))
        dialog.save()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertTrue(read_settings()['setup_complete'])
        self.assertFalse(preferences()['shake_enabled'])
        set_language('en')
        self.assertEqual(preferences()['animation'], 'light')
        dialog.deleteLater()

    def test_cancel_does_not_complete_setup(self):
        dialog = SettingsDialog()
        dialog.reject()
        self.assertFalse(read_settings().get('setup_complete'))
        dialog.deleteLater()

    def test_disabled_shake_and_high_polling_mouse_are_filtered(self):
        controller = ShakeSearch(self.app)
        with patch.object(controller, 'detect_shake') as detect:
            controller.options['shake_enabled'] = False
            controller.on_move(1, 1)
            detect.assert_not_called()
            controller.options['shake_enabled'] = True
            with patch('shakesearch.time.monotonic', side_effect=[100, 100.001, 100.009]):
                controller.on_move(1, 1)
                controller.on_move(2, 2)
                controller.on_move(3, 3)
            self.assertEqual(detect.call_count, 2)

    def test_control_window_has_manual_capture_and_no_keyboard_listener(self):
        controller = ShakeSearch(self.app)
        panel = ControlPanel(controller)
        with patch.object(controller, 'trigger_capture') as capture:
            panel.capture.click()
            capture.assert_called_once()
        self.assertFalse(hasattr(controller, 'hotkey_listener'))
        panel.deleteLater()

    def test_light_mode_skips_plasma_and_keeps_border(self):
        from PySide6.QtCore import QRect
        from PySide6.QtGui import QPixmap
        from overlay import AnimatedScreenOverlay
        save_preferences('it', True, 'normal', 'light')
        pixmap = QPixmap(320, 240)
        pixmap.fill()
        overlay = AnimatedScreenOverlay(dict(pixmap=pixmap, geometry=QRect(0, 0, 320, 240)), Mock())
        overlay.start_animation()
        overlay.advance_animation()
        self.assertEqual(overlay.progress, 1)
        self.assertEqual(overlay.timer.interval(), 33)
        overlay.close()
