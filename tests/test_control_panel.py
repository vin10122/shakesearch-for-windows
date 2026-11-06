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

    def test_control_window_has_manual_capture(self):
        controller = ShakeSearch(self.app)
        panel = ControlPanel(controller)
        with patch.object(controller, 'trigger_capture') as capture:
            panel.capture.click()
            capture.assert_called_once()
        panel.deleteLater()

    def test_hotkey_toggles_only_shakes_and_preserves_manual_capture(self):
        save_preferences('en', True, 'high', 'light')
        controller = ShakeSearch(self.app)
        controller.panel = ControlPanel(controller)
        controller.inputs.detector.points.append((1, 2, 3))
        with patch.object(controller, 'trigger_capture') as capture:
            controller.inputs.toggle_requested.emit()
            self.app.processEvents()
            self.assertFalse(controller.options['shake_enabled'])
            self.assertFalse(preferences()['shake_enabled'])
            self.assertFalse(controller.inputs.detector.points)
            self.assertEqual(controller.options['sensitivity'], 'high')
            self.assertEqual(controller.options['animation'], 'light')
            self.assertIn('Alt+F7', controller.panel.status.text())
            capture.assert_not_called()
            controller.panel.capture.click()
            capture.assert_called_once()
            controller.inputs.toggle_requested.emit()
            self.app.processEvents()
            self.assertTrue(preferences()['shake_enabled'])
            self.assertEqual(capture.call_count, 1)
        controller.panel.deleteLater()

    def test_toggle_save_failure_keeps_shake_state(self):
        controller = ShakeSearch(self.app)
        with patch('shakesearch.save_preferences', side_effect=OSError('read only')), \
                self.assertLogs('shakesearch', level='ERROR'):
            controller.toggle_shake()
        self.assertTrue(controller.options['shake_enabled'])

    def test_disabling_shakes_cancels_delayed_capture_even_after_reenabling(self):
        controller = ShakeSearch(self.app)
        controller.panel = Mock()
        controller.panel.isMinimized.return_value = False
        with patch('shakesearch.QTimer.singleShot') as timer, \
                patch.object(controller, 'capture_all_screens') as screenshot:
            controller.trigger_shake_capture(controller.inputs.generation)
            delayed_capture = timer.call_args.args[1]
            controller.toggle_shake()
            controller.toggle_shake()
            delayed_capture()
            screenshot.assert_not_called()
            self.assertFalse(controller._capture_pending)

    def test_gaming_mode_preserves_delayed_manual_capture(self):
        controller = ShakeSearch(self.app)
        controller.panel = Mock()
        controller.panel.isMinimized.return_value = False
        with patch('shakesearch.QTimer.singleShot') as timer, \
                patch.object(controller, 'capture_all_screens', return_value=[{}]) as screenshot, \
                patch('shakesearch.MultiScreenOverlayManager'):
            controller.trigger_capture()
            delayed_capture = timer.call_args.args[1]
            controller.toggle_shake()
            delayed_capture()
            screenshot.assert_called_once()

    def test_notifications_describe_gaming_mode_and_reactivation(self):
        for language in ('it', 'en'):
            with self.subTest(language=language):
                save_preferences(language, True, 'normal', 'balanced')
                controller = ShakeSearch(self.app)
                panel = ControlPanel(controller)
                controller.panel = panel
                panel.tray = Mock()
                with patch('control_panel.QSystemTrayIcon.isSystemTrayAvailable', return_value=True):
                    panel.notify_shake_state()
                    self.assertNotIn('Gaming mode', panel.tray.showMessage.call_args.args[0])
                    controller.toggle_shake()
                    title, message = panel.tray.showMessage.call_args.args[:2]
                    self.assertIn('Gaming mode', title)
                    self.assertIn('DPI', message)
                    self.assertIn('Gaming mode', panel.status.text())
                    controller.toggle_shake()
                    self.assertNotIn('Gaming mode', panel.tray.showMessage.call_args.args[0])
                    self.assertEqual(panel.tray.showMessage.call_count, 3)
                panel.deleteLater()

    def test_settings_change_notifies_shake_state(self):
        controller = ShakeSearch(self.app)
        panel = ControlPanel(controller)
        def accept():
            save_preferences('it', False, 'normal', 'balanced')
            return QDialog.DialogCode.Accepted
        with patch('control_panel.SettingsDialog') as dialog, \
                patch.object(panel, 'notify_shake_state') as notify:
            dialog.return_value.exec.side_effect = accept
            panel.settings()
            notify.assert_called_once()
            self.assertIn('Gaming mode', panel.status.text())
        panel.deleteLater()

    def test_queued_shake_does_not_capture_after_gaming_mode_is_enabled(self):
        controller = ShakeSearch(self.app)
        with patch.object(controller, 'trigger_capture') as capture:
            controller.inputs.shake_detected.emit(controller.inputs.generation)
            controller.toggle_shake()
            self.app.processEvents()
            capture.assert_not_called()

    def test_shutdown_stops_input_timer_and_unregisters_shortcut(self):
        controller = ShakeSearch(self.app)
        with patch.object(controller.inputs, 'stop') as stop:
            controller.stop_listeners()
            stop.assert_called_once()

    def test_stale_shake_signal_is_rejected_after_off_on_cycle(self):
        controller = ShakeSearch(self.app)
        old_generation = controller.inputs.generation
        controller.toggle_shake()
        controller.toggle_shake()
        with patch.object(controller, '_request_capture') as capture:
            controller.inputs.shake_detected.emit(old_generation)
            capture.assert_not_called()
            controller.inputs.shake_detected.emit(controller.inputs.generation)
            capture.assert_called_once_with(controller.inputs.generation)

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
