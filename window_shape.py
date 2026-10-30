"""Clip the native Windows form to the rounded drawer, removing its outer backing."""
import ctypes
from ctypes import wintypes
import logging
import sys


def install_drawer_shape(window, fullscreen):
    # Called by before_show on the native UI thread; no bridge or Invoke waits.
    if sys.platform != 'win32':
        return
    try:
        form = window.native
        gdi = ctypes.windll.gdi32
        user = ctypes.windll.user32
        gdi.CreateRoundRectRgn.argtypes = [ctypes.c_int] * 6
        gdi.CreateRoundRectRgn.restype = wintypes.HRGN
        gdi.DeleteObject.argtypes = [wintypes.HANDLE]
        gdi.DeleteObject.restype = wintypes.BOOL
        user.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HRGN, wintypes.BOOL]
        user.SetWindowRgn.restype = ctypes.c_int

        def update(*_):
            try:
                hwnd = int(form.Handle.ToInt64())
                if fullscreen():
                    user.SetWindowRgn(hwnd, None, True)
                    return
                scale = float(form.DeviceDpi) / 96
                x, y, radius = round(12 * scale), round(8 * scale), round(64 * scale)
                width, height = int(form.ClientSize.Width), int(form.ClientSize.Height)
                if width <= 2 * x or height <= 2 * y:
                    return
                region = gdi.CreateRoundRectRgn(x, y, width - x + 1, height - y + 1, radius, radius)
                if not region:
                    raise OSError('CreateRoundRectRgn failed')
                # Windows takes ownership only after a successful SetWindowRgn.
                if not user.SetWindowRgn(hwnd, region, True):
                    gdi.DeleteObject(region)
                    raise OSError('SetWindowRgn failed')
            except Exception:
                logging.getLogger('shakesearch').exception('Unable to update rounded drawer shape')

        form.Resize += update
        update()
    except Exception:
        logging.getLogger('shakesearch').exception('Unable to remove native drawer backing')
