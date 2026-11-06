"""ShakeSearch desktop entry point. Qt owns all capture and animation windows."""
import logging
from app_runtime import child_command, child_environment
from localization import tr, get_language
from logging.handlers import RotatingFileHandler
import os
import subprocess
import sys
import tempfile

from PySide6.QtCore import QObject, QLockFile, Slot, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QMessageBox

from overlay import AnimatedScreenOverlay
from app_settings import preferences, save_preferences
from desktop_input import DesktopInput

logger = logging.getLogger("shakesearch")
LOG_PATH = os.path.join(tempfile.gettempdir(), "shakesearch.log")


def configure_logging():
    handler = RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=1,
                                  encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler],
                        format="%(asctime)s %(levelname)s %(message)s")
    logger.info("Starting ShakeSearch with Qt; log: %s", LOG_PATH)


def report_exception(error_type, error, traceback):
    logger.error("Unhandled interface error", exc_info=(error_type, error, traceback))
    sys.__excepthook__(error_type, error, traceback)


class ShakeSearch(QObject):
    def __init__(self, application):
        super().__init__()
        self.application = application
        self.inputs = DesktopInput(application)
        self.options = preferences()
        self.panel = None
        self._capture_pending = False
        self.multi_overlay = None
        self.inputs.configure(self.options['shake_enabled'], self.options['sensitivity'])
        self.inputs.shake_detected.connect(self.trigger_shake_capture)
        self.inputs.toggle_requested.connect(self.toggle_shake)
        self.application.aboutToQuit.connect(self.stop_listeners)

    def reload_preferences(self):
        self.options = preferences()
        self.inputs.configure(self.options['shake_enabled'], self.options['sensitivity'])

    @Slot()
    def toggle_shake(self):
        enabled = not self.options['shake_enabled']
        try:
            save_preferences(get_language(), enabled, self.options['sensitivity'],
                             self.options['animation'])
        except (OSError, ValueError):
            logger.exception("Unable to save shake activation preference")
            return
        self.reload_preferences()
        if self.panel is not None:
            self.panel.refresh()
            self.panel.notify_shake_state()

    @Slot(int)
    def trigger_shake_capture(self, generation):
        if self.options['shake_enabled'] and generation == self.inputs.generation:
            self._request_capture(generation)

    @Slot()
    def trigger_capture(self):
        # Manual capture is available independently of shake activation.
        self._request_capture()

    def _request_capture(self, shake_generation=None):
        if self.multi_overlay is not None or self._capture_pending:
            return
        if self.panel is not None and self.panel.isVisible() and not self.panel.isMinimized():
            self.panel.showMinimized()
            self._capture_pending = True
            QTimer.singleShot(180, lambda: self._capture_after_hide(shake_generation))
            return
        self._capture_after_hide(shake_generation)

    def _capture_after_hide(self, shake_generation=None):
        self._capture_pending = False
        if shake_generation is not None and (
                shake_generation != self.inputs.generation or not self.options['shake_enabled']):
            return
        try:
            screen_data = self.capture_all_screens()
            self.multi_overlay = MultiScreenOverlayManager(screen_data, self.on_session_finished)
            logger.info("Qt overlays opened on %d monitor(s)", len(screen_data))
        except Exception:
            logger.exception("Unable to open capture overlay")
            QMessageBox.critical(None, "ShakeSearch",
                                 tr("Unable to open screen capture. Details: ") + LOG_PATH)

    def capture_all_screens(self):
        # Qt supplies logical geometry and native-resolution pixels for mixed-DPI screens.
        results = []
        for screen in self.application.screens():
            pixmap = screen.grabWindow(0)
            if pixmap.isNull():
                raise RuntimeError("Screen capture failed for " + screen.name())
            results.append(dict(geometry=screen.geometry(),
                                work_area=screen.availableGeometry(), pixmap=pixmap))
        if not results:
            raise RuntimeError("No monitors available")
        return results

    def on_session_finished(self):
        self.multi_overlay = None

    def stop_listeners(self):
        self.inputs.stop()

    def run(self):
        from control_panel import ControlPanel, SettingsDialog
        from localization import read_settings
        from PySide6.QtWidgets import QDialog
        try:
            if not read_settings().get('setup_complete'):
                if SettingsDialog().exec() != QDialog.DialogCode.Accepted:
                    return 0
                self.reload_preferences()
            try:
                self.inputs.start()
            except RuntimeError as error:
                logger.exception('Unable to register shake toggle shortcut')
                QMessageBox.warning(None, 'ShakeSearch — Alt+F7', str(error))
                return 1
            self.panel = ControlPanel(self)
            self.panel.show()
            QTimer.singleShot(0, self.panel.notify_shake_state)
            logger.info("Ready: shake the mouse or use Select area")
            print("[ShakeSearch] Attivo. Scuoti il mouse o usa Seleziona area. Chiudi la finestra per uscire.", flush=True)
            return self.application.exec()
        finally:
            self.stop_listeners()



class MultiScreenOverlayManager:
    def __init__(self, screen_data, on_finish):
        self.on_finish = on_finish
        self.overlays = []
        self.selection_done = False
        cursor = QCursor.pos()
        target = next((s for s in screen_data if s['geometry'].contains(cursor)), screen_data[0])
        try:
            for data in screen_data:
                overlay = AnimatedScreenOverlay(data, self)
                self.overlays.append(overlay)
            for overlay in self.overlays:
                overlay.show()
                overlay.raise_()
            selected = next(o for o in self.overlays if o.screen_data is target)
            selected.activateWindow()
            selected.setFocus()
            QTimer.singleShot(0, self.start_animations)
        except Exception:
            self.close_overlays()
            raise

    def start_animations(self):
        for overlay in self.overlays:
            overlay.start_animation()

    def on_confirm_crop(self, image, screen_data):
        if self.selection_done:
            return
        # Prepare the drawer before ending the capture session, so launch errors are visible.
        try:
            path = os.path.join(tempfile.gettempdir(), "cts_selection.png")
            image.save(path, format="PNG")
            work = screen_data['work_area']
            width = min(560, max(200, work.width() - 32))
            height = min(680, max(200, int(work.height() * .82)))
            x = work.x() + (work.width() - width) // 2
            y = work.y() + work.height() - height - 14
            with open(LOG_PATH, 'a', encoding='utf-8') as log:
                subprocess.Popen(child_command('drawer', path, x, y, width, height),
                                 stdout=log, stderr=log,
                                 env=child_environment('drawer'),
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except Exception:
            logger.exception("Unable to launch chat drawer")
            QMessageBox.critical(None, "ShakeSearch", tr("Unable to open chat. Details: ") + LOG_PATH)
            return
        self.selection_done = True
        self.close_overlays()
        self.on_finish()

    def close_overlays(self):
        for overlay in self.overlays:
            overlay.close()
        self.overlays.clear()

    def cancel(self):
        self.close_overlays()
        self.on_finish()


def main():
    configure_logging()
    sys.excepthook = report_exception
    from app_icon import configure_qt_icon
    application = QApplication(sys.argv)
    configure_qt_icon(application)
    application.setQuitOnLastWindowClosed(False)
    application.setApplicationName("ShakeSearch")
    from localization import settings_path
    lock_path = settings_path().with_name('app.lock')
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    instance_lock = QLockFile(str(lock_path))
    instance_lock.setStaleLockTime(0)
    if not instance_lock.tryLock(0):
        QMessageBox.information(None, 'ShakeSearch',
                                'ShakeSearch is already running. Close the previous instance first.\n'
                                'ShakeSearch è già aperto. Chiudi prima la precedente istanza.')
        return 0
    controller = ShakeSearch(application)
    try:
        return controller.run()
    except Exception:
        logger.exception("ShakeSearch stopped")
        raise
    finally:
        instance_lock.unlock()


if __name__ == "__main__":
    sys.exit(main())
