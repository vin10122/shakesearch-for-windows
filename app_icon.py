"""Shared identity and logo for source and portable Windows windows."""
import ctypes
import os
from pathlib import Path


def icon_path():
    return Path(__file__).resolve().parent / 'assets' / 'shakesearch.ico'


def set_windows_identity():
    if os.name == 'nt':
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('ShakeSearch.Desktop')


def configure_qt_icon(application):
    from PySide6.QtGui import QIcon
    set_windows_identity()
    application.setWindowIcon(QIcon(str(icon_path())))
