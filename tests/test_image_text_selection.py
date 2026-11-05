import io
import os
import unittest
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PIL import Image
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from ocr_viewer import ImageTextWindow

TEXT = 'Ciao mondo\nSeconda riga'
WORDS = [dict(start=0, end=4, x=20, y=20, width=80, height=30),
         dict(start=5, end=10, x=120, y=20, width=100, height=30),
         dict(start=11, end=18, x=20, y=80, width=140, height=30),
         dict(start=19, end=23, x=180, y=80, width=80, height=30)]


class ImageTextSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        output = io.BytesIO()
        Image.new('RGB', (640, 240), 'white').save(output, 'PNG')
        self.ocr = patch('ocr_viewer.extract_text', return_value=dict(text=TEXT, words=WORDS)).start()
        self.lens = patch('lens_process.LensProcessClient').start()
        self.addCleanup(patch.stopall)
        self.window = ImageTextWindow(image_bytes=output.getvalue())
        self.window.show()
        for _ in range(100):
            QTest.qWait(10)
            if self.window.preview.label.words:
                break
        self.label = self.window.preview.label
        self.assertEqual(len(self.label.words), 4)
        self.assertFalse(self.window.text.isVisible())
        self.addCleanup(self.window.close)

    def point(self, word_index, char_index):
        word = self.label.words[word_index]
        rect = self.label.word_rect(word)
        fraction = self.label.boundaries(word)[char_index]
        return QPoint(round(rect.left() + fraction * rect.width()), round(rect.center().y()))

    def drag(self, start, end):
        QTest.mousePress(self.label, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(self.label, end)
        QTest.mouseRelease(self.label, Qt.MouseButton.LeftButton, pos=end)

    def test_select_individual_letters_and_ctrl_c_directly_on_image(self):
        self.drag(self.point(0, 1), self.point(0, 3))
        self.assertEqual(self.label.selected_text(), 'ia')
        QTest.keyClick(self.label, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.app.clipboard().text(), 'ia')
        self.lens.assert_not_called()

    def test_multiline_reverse_selection_and_copy_button(self):
        self.drag(self.point(2, 7), self.point(0, 0))
        self.assertEqual(self.label.selected_text(), 'Ciao mondo\nSeconda')
        self.window.copy.click()
        self.assertEqual(self.app.clipboard().text(), 'Ciao mondo\nSeconda')
        self.lens.assert_not_called()

    def test_selection_survives_zoom_and_tracks_scaled_coordinates(self):
        self.window.preview.set_zoom(2)
        self.drag(self.point(1, 0), self.point(1, 5))
        self.assertEqual(self.label.selected_text(), 'mondo')
        self.window.preview.set_zoom(.5)
        self.assertEqual(self.label.selected_text(), 'mondo')
        self.drag(self.point(3, 0), self.point(3, 4))
        self.assertEqual(self.label.selected_text(), 'riga')

    def test_ctrl_a_and_blank_click_clear_selection(self):
        self.label.setFocus()
        QTest.keyClick(self.label, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.label.selected_text(), TEXT)
        QTest.mouseClick(self.label, Qt.MouseButton.LeftButton, pos=QPoint(self.label.width() - 2, self.label.height() - 2))
        self.assertEqual(self.label.selected_text(), '')
