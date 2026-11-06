"""GUI-thread input: a native Windows hotkey and bounded mouse polling."""
from collections import deque
import ctypes
from ctypes import wintypes
import math
import os
import time

from PySide6.QtCore import QAbstractNativeEventFilter, QEventLoop, QObject, QTimer, Qt, Signal
from PySide6.QtGui import QCursor

from app_settings import DISTANCES

WM_HOTKEY = 0x0312
HOTKEY_ID = 0x5348
VK_F7 = 0x76
MOD_ALT = 0x0001
MOD_NOREPEAT = 0x4000


class ShakeDetector:
    def __init__(self):
        self.points = deque()
        self.last_trigger = float('-inf')

    def reset(self):
        self.points.clear()

    def sample(self, x, y, now, sensitivity):
        while self.points and self.points[0][2] <= now - .55:
            self.points.popleft()
        if self.points and (x, y) == self.points[-1][:2]:
            return False
        self.points.append((x, y, now))
        if len(self.points) < 6 or now - self.last_trigger < .8:
            return False
        distance = 0
        signs = [[], []]
        for previous, current in zip(self.points, list(self.points)[1:]):
            dx, dy = current[0] - previous[0], current[1] - previous[1]
            distance += math.hypot(dx, dy)
            for axis, delta in enumerate((dx, dy)):
                if abs(delta) > 12:
                    signs[axis].append(delta > 0)
        reversals = max(sum(a != b for a, b in zip(axis, axis[1:])) for axis in signs)
        if distance < DISTANCES[sensitivity] or reversals < 4:
            return False
        self.last_trigger = now
        self.reset()
        return True


class WindowsShakeHotkey(QAbstractNativeEventFilter):
    """Register Alt+F7 with the OS; its only callback toggles shake reception."""
    def __init__(self, application, toggle):
        super().__init__()
        self.application = application
        self.toggle = toggle
        self.registered = False
        self.user32 = None

    def start(self):
        if self.registered:
            return
        if os.name != 'nt':
            raise RuntimeError('The global Alt+F7 shortcut requires Windows.')
        self.user32 = ctypes.WinDLL('user32', use_last_error=True)
        self.user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        self.user32.RegisterHotKey.restype = wintypes.BOOL
        self.user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        self.user32.UnregisterHotKey.restype = wintypes.BOOL
        if not self.user32.RegisterHotKey(None, HOTKEY_ID, MOD_ALT | MOD_NOREPEAT, VK_F7):
            error = ctypes.get_last_error()
            raise RuntimeError(f'Cannot register Alt+F7 (Windows error {error}). '
                               'Close other ShakeSearch instances or apps using this shortcut.')
        self.registered = True
        self.application.installNativeEventFilter(self)

    def nativeEventFilter(self, event_type, message):
        if self.registered and bytes(event_type) in (b'windows_generic_MSG', b'windows_dispatcher_MSG'):
            event = wintypes.MSG.from_address(int(message))
            if event.message == WM_HOTKEY and event.wParam == HOTKEY_ID:
                self.toggle()
                return True, 0
        return False, 0

    def stop(self):
        if self.registered:
            self.application.removeNativeEventFilter(self)
            self.user32.UnregisterHotKey(None, HOTKEY_ID)
            self.registered = False


class DesktopInput(QObject):
    shake_detected = Signal(int)
    toggle_requested = Signal()

    def __init__(self, application):
        super().__init__()
        self.detector = ShakeDetector()
        self.enabled = False
        self.sensitivity = 'normal'
        self.generation = 0
        self.running = False
        self.hotkey_error = None
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(8)
        self.timer.timeout.connect(self.poll)
        self.hotkey = WindowsShakeHotkey(application, self.toggle_requested.emit)

    def configure(self, enabled, sensitivity):
        self.generation += 1
        self.enabled = enabled
        self.sensitivity = sensitivity
        self.detector.reset()
        self.timer.stop()
        if self.running and enabled:
            self.timer.start()

    def start(self):
        self.hotkey_error = None
        try:
            self.hotkey.start()
        except RuntimeError as error:
            # The panel toggle and manual capture must work without a shortcut.
            self.hotkey_error = str(error)
        self.running = True
        if self.enabled:
            self.timer.start()

    def stop(self):
        self.running = False
        self.timer.stop()
        self.detector.reset()
        self.hotkey.stop()

    def poll(self):
        if not self.running or not self.enabled:
            return
        position = QCursor.pos()
        if self.detector.sample(position.x(), position.y(), time.monotonic(), self.sensitivity):
            self.shake_detected.emit(self.generation)


def verify_native_hotkey():
    """Exercise real Windows registration and Qt delivery in the frozen EXE."""
    from PySide6.QtWidgets import QApplication
    application = QApplication.instance() or QApplication([])
    received = []
    hotkey = WindowsShakeHotkey(application, lambda: received.append(True))
    hotkey.start()
    try:
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD
        post = hotkey.user32.PostThreadMessageW
        post.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        post.restype = wintypes.BOOL
        if not post(kernel32.GetCurrentThreadId(), WM_HOTKEY, HOTKEY_ID, MOD_ALT | (VK_F7 << 16)):
            raise ctypes.WinError(ctypes.get_last_error())
        loop = QEventLoop()
        QTimer.singleShot(100, loop.quit)
        loop.exec()
        if received != [True]:
            raise RuntimeError('Native Alt+F7 message did not reach the Qt event loop')
    finally:
        hotkey.stop()
