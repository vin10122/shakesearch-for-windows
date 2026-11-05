"""Read an immutable screen capture without blocking Qt or opening a browser."""
import logging
import threading
from PySide6.QtCore import QObject, Signal
from local_ocr import extract_text


class ScreenOcrSignals(QObject):
    finished = Signal(object)


class ScreenOcrTask:
    def __init__(self, image_bytes):
        self.image_bytes = image_bytes
        self.signals = ScreenOcrSignals()

    def start(self):
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        try:
            result = extract_text(self.image_bytes)
        except Exception as error:
            logging.getLogger('shakesearch').exception('Screen text recognition failed')
            result = dict(error=str(error))
        self.signals.finished.emit(result)
