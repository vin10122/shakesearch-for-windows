"""ShakeSearch desktop entry point. Qt owns all capture and animation windows."""
import logging
from logging.handlers import RotatingFileHandler
import math
import os
import subprocess
import sys
import tempfile
import time

from dotenv import load_dotenv
from PySide6.QtCore import QObject, Signal, Slot, Qt, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QMessageBox

from overlay import AnimatedScreenOverlay

load_dotenv()
SHAKE_DISTANCE_THRESHOLD = 300
SHAKE_TIME_WINDOW = 0.55
SHAKE_MIN_REVERSALS = 4
SHAKE_DEBOUNCE = 0.8
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
    capture_requested = Signal()

    def __init__(self, application):
        super().__init__()
        self.application = application
        self.positions = []
        self.last_shake = 0
        self.mouse_listener = None
        self.hotkey_listener = None
        self.multi_overlay = None
        self.capture_requested.connect(self.trigger_capture, Qt.ConnectionType.QueuedConnection)
        self.application.aboutToQuit.connect(self.stop_listeners)

    def detect_shake(self, x, y):
        now = time.time()
        self.positions.append((x, y, now))
        cutoff = now - SHAKE_TIME_WINDOW
        self.positions = [(px, py, pt) for px, py, pt in self.positions if pt > cutoff]

        if len(self.positions) < 6:
            return False

        total_distance = sum(
            math.hypot(self.positions[i][0] - self.positions[i - 1][0],
                       self.positions[i][1] - self.positions[i - 1][1])
            for i in range(1, len(self.positions))
        )
        if total_distance < SHAKE_DISTANCE_THRESHOLD:
            return False

        dx_signs = []
        dy_signs = []
        for i in range(1, len(self.positions)):
            dx = self.positions[i][0] - self.positions[i - 1][0]
            dy = self.positions[i][1] - self.positions[i - 1][1]
            if abs(dx) > 12:
                dx_signs.append(1 if dx > 0 else -1)
            if abs(dy) > 12:
                dy_signs.append(1 if dy > 0 else -1)

        x_reversals = sum(1 for i in range(1, len(dx_signs)) if dx_signs[i] != dx_signs[i - 1])
        y_reversals = sum(1 for i in range(1, len(dy_signs)) if dy_signs[i] != dy_signs[i - 1])

        if (x_reversals >= SHAKE_MIN_REVERSALS or y_reversals >= SHAKE_MIN_REVERSALS):
            if now - self.last_shake > SHAKE_DEBOUNCE:
                self.last_shake = now
                self.positions = []
                print("[ShakeSearch] Shake detected!")
                return True

        return False

    def on_move(self, x, y):
        if self.detect_shake(x, y):
            self.capture_requested.emit()

    def on_hotkey_triggered(self):
        logger.info("Alt+F7 received")
        self.capture_requested.emit()

    @Slot()
    def trigger_capture(self):
        if self.multi_overlay is not None:
            return
        try:
            screen_data = self.capture_all_screens()
            self.multi_overlay = MultiScreenOverlayManager(screen_data, self.on_session_finished)
            logger.info("Qt overlays opened on %d monitor(s)", len(screen_data))
        except Exception:
            logger.exception("Unable to open capture overlay")
            QMessageBox.critical(None, "ShakeSearch",
                                 "Unable to open screen capture. Details: " + LOG_PATH)

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
        for listener in (self.mouse_listener, self.hotkey_listener):
            if listener is not None:
                listener.stop()

    def run(self):
        # Import platform input backends only when starting global input listeners.
        from pynput import mouse, keyboard
        try:
            self.mouse_listener = mouse.Listener(on_move=self.on_move)
            self.mouse_listener.start()
            self.hotkey_listener = keyboard.GlobalHotKeys({'<alt>+<f7>': self.on_hotkey_triggered})
            self.hotkey_listener.start()
            logger.info("Ready: Alt+F7 or shake the mouse")
            print("[ShakeSearch] Active! Press Alt+F7 or shake the mouse.")
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
            script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "drawer.py")
            with open(LOG_PATH, 'a', encoding='utf-8') as log:
                subprocess.Popen([sys.executable, script, path, str(x), str(y),
                                  str(width), str(height)], stdout=log, stderr=log)
        except Exception:
            logger.exception("Unable to launch chat drawer")
            QMessageBox.critical(None, "ShakeSearch", "Unable to open chat. Details: " + LOG_PATH)
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
    application = QApplication(sys.argv)
    application.setQuitOnLastWindowClosed(False)
    application.setApplicationName("ShakeSearch")
    controller = ShakeSearch(application)
    try:
        return controller.run()
    except Exception:
        logger.exception("ShakeSearch stopped")
        raise


if __name__ == "__main__":
    sys.exit(main())
