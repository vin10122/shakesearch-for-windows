import base64
import io
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PIL import Image
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication

import drawer
from ocr_viewer import ImageTextWindow, extract_text

TEXT = 'Ciao, mondo!\nSeconda riga: è già qui.'


def sample_png():
    output = io.BytesIO()
    Image.new('RGB', (320, 180), 'white').save(output, 'PNG')
    return output.getvalue()


class ExtractionTests(unittest.TestCase):
    def test_vision_request_preserves_unicode_and_uses_selected_image(self):
        response = SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=TEXT), finish_reason='stop')])
        client = Mock()
        client.chat.completions.create.return_value = response
        with patch.dict(os.environ, {'GROQ_API_KEY': 'test-key', 'GROQ_MODEL': 'test-vision'}), patch('groq.Groq') as factory:
            factory.return_value.__enter__.return_value = client
            result = extract_text(sample_png())
        self.assertEqual(result, dict(text=TEXT, truncated=False))
        request = client.chat.completions.create.call_args.kwargs
        self.assertEqual(request['model'], 'test-vision')
        uri = request['messages'][1]['content'][1]['image_url']['url']
        self.assertEqual(base64.b64decode(uri.split(',', 1)[1]), sample_png())

    def test_missing_key_does_not_send_a_request(self):
        with patch.dict(os.environ, {'GROQ_API_KEY': ''}), patch('groq.Groq') as factory:
            with self.assertRaisesRegex(RuntimeError, 'GROQ_API_KEY'):
                extract_text(sample_png())
        factory.assert_not_called()

    def test_truncation_is_reported(self):
        client = Mock()
        client.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content='Partial text'), finish_reason='length')])
        with patch.dict(os.environ, {'GROQ_API_KEY': 'test-key'}), patch('groq.Groq') as factory:
            factory.return_value.__enter__.return_value = client
            self.assertTrue(extract_text(sample_png())['truncated'])


class ImageTextWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.extractor = patch('ocr_viewer.extract_text', return_value=dict(text=TEXT, truncated=False)).start()
        self.addCleanup(patch.stopall)
        self.window = ImageTextWindow(image_bytes=sample_png())

    def tearDown(self):
        self.window.close()
        self.app.processEvents()

    def recognize(self):
        self.window.show()
        for _ in range(300):
            self.app.processEvents()
            time.sleep(.01)
            if self.window._task is not None and not self.window._recognizing:
                return
        self.fail('Recognition did not finish')

    def test_opens_image_and_makes_recognized_text_editable(self):
        self.recognize()
        self.assertEqual(self.window.text.toPlainText(), TEXT)
        self.assertFalse(self.window.text.isReadOnly())
        self.assertTrue(self.window.copy.isEnabled())
        self.assertFalse(self.window.preview.label.pixmap().isNull())
        self.window.text.insertPlainText('Correzione: ')
        self.assertIn('Correzione:', self.window.text.toPlainText())

    def test_copy_all_and_selected_text(self):
        self.recognize()
        self.window.copy.click()
        self.assertEqual(self.app.clipboard().text(), TEXT)
        cursor = self.window.text.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(4, QTextCursor.MoveMode.KeepAnchor)
        self.window.text.setTextCursor(cursor)
        self.window.copy.click()
        self.assertEqual(self.app.clipboard().text(), 'Ciao')

    def test_no_text_found_and_retry(self):
        self.extractor.return_value = dict(text='', truncated=False)
        self.recognize()
        self.assertIn('Nessun testo', self.window.status.text())
        self.assertFalse(self.window.copy.isEnabled())
        self.extractor.return_value = dict(text=TEXT, truncated=False)
        self.window.retry.click()
        self.recognize()
        self.assertEqual(self.window.text.toPlainText(), TEXT)

    def test_error_is_visible_and_image_stays_open(self):
        self.extractor.side_effect = RuntimeError('Configura GROQ_API_KEY')
        with self.assertLogs('shakesearch', level='ERROR'):
            self.recognize()
        self.assertIn('GROQ_API_KEY', self.window.status.text())
        self.assertTrue(self.window.isVisible())
        self.assertTrue(self.window.retry.isEnabled())
        self.assertFalse(self.window.text.isReadOnly())

    def test_partial_text_is_marked(self):
        self.extractor.return_value = dict(text='Partial', truncated=True)
        self.recognize()
        self.assertIn('Testo parziale', self.window.status.text())
        self.assertEqual(self.window.text.toPlainText(), 'Partial')


class DrawerImageTextTests(unittest.TestCase):
    def test_launch_passes_original_capture_even_after_file_changes(self):
        class Pipe(io.BytesIO):
            def close(self):
                self.written = self.getvalue()
                super().close()

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'capture.png'
            original = sample_png()
            path.write_bytes(original)
            with patch.object(drawer, 'GROQ_API_KEY', None):
                api = drawer.DrawerApi(str(path), (0, 0, 560, 680))
            path.write_bytes(b'later capture')
            process = Mock(stdin=Pipe())
            with patch.object(drawer.subprocess, 'Popen', return_value=process) as launch:
                self.assertEqual(api.open_image_for_text(), dict(ok=True))
            self.assertEqual(process.stdin.written, original)
            self.assertEqual(launch.call_args.args[0][-1], '--stdin')

    def test_missing_image_is_reported_without_launching(self):
        with patch.object(drawer, 'GROQ_API_KEY', None):
            api = drawer.DrawerApi('/nonexistent/image.png', (0, 0, 560, 680))
        with patch.object(drawer.subprocess, 'Popen') as launch:
            self.assertFalse(api.open_image_for_text()['ok'])
        launch.assert_not_called()
