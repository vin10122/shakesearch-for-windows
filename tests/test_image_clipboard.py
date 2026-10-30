import io
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PIL import Image
import drawer
from image_clipboard import copy_image_to_clipboard


def png_bytes():
    output = io.BytesIO()
    Image.new('RGBA', (5, 3), (30, 60, 90, 180)).save(output, 'PNG')
    return output.getvalue()


class WindowsImageClipboardTests(unittest.TestCase):
    def setUp(self):
        self.clipboard = SimpleNamespace(CF_DIB=8, RegisterClipboardFormat=Mock(return_value=1000),
                                         OpenClipboard=Mock(), EmptyClipboard=Mock(),
                                         SetClipboardData=Mock(), CloseClipboard=Mock())
        self.windows = SimpleNamespace(CreateWindowEx=Mock(return_value=1234), DestroyWindow=Mock())
        self.modules = patch.dict(sys.modules, {'win32clipboard': self.clipboard, 'win32gui': self.windows})
        self.modules.start()
        self.addCleanup(self.modules.stop)

    def test_copies_valid_dib_and_png_with_real_owner_handle(self):
        copy_image_to_clipboard(png_bytes())
        self.clipboard.OpenClipboard.assert_called_once_with(1234)
        payloads = dict(call.args for call in self.clipboard.SetClipboardData.call_args_list)
        dib = payloads[8]
        header_size = struct.unpack('<I', dib[:4])[0]
        bmp = b'BM' + struct.pack('<IHHI', len(dib) + 14, 0, 0, header_size + 14) + dib
        with Image.open(io.BytesIO(bmp)) as image:
            self.assertEqual(image.size, (5, 3))
            self.assertEqual(image.getpixel((2, 1)), (30, 60, 90))
        with Image.open(io.BytesIO(payloads[1000])) as image:
            self.assertEqual(image.getpixel((2, 1)), (30, 60, 90, 180))
        self.clipboard.CloseClipboard.assert_called_once()
        self.windows.DestroyWindow.assert_called_once_with(1234)

    def test_busy_clipboard_is_retried(self):
        self.clipboard.OpenClipboard.side_effect = [OSError('busy'), None]
        with patch('image_clipboard.time.sleep') as sleep:
            copy_image_to_clipboard(png_bytes())
        self.assertEqual(self.clipboard.OpenClipboard.call_count, 2)
        sleep.assert_called_once_with(.025)
        self.clipboard.EmptyClipboard.assert_called_once()

    def test_always_busy_reports_failure_without_clearing_clipboard(self):
        self.clipboard.OpenClipboard.side_effect = OSError('busy')
        with patch('image_clipboard.time.sleep'):
            with self.assertRaises(OSError):
                copy_image_to_clipboard(png_bytes())
        self.assertEqual(self.clipboard.OpenClipboard.call_count, 10)
        self.clipboard.EmptyClipboard.assert_not_called()
        self.clipboard.CloseClipboard.assert_not_called()
        self.windows.DestroyWindow.assert_called_once_with(1234)

    def test_write_failure_still_releases_clipboard_and_owner(self):
        self.clipboard.SetClipboardData.side_effect = OSError('write failed')
        with self.assertRaises(OSError):
            copy_image_to_clipboard(png_bytes())
        self.clipboard.CloseClipboard.assert_called_once()
        self.windows.DestroyWindow.assert_called_once_with(1234)

    def test_invalid_image_does_not_change_clipboard(self):
        with self.assertRaises(Exception):
            copy_image_to_clipboard(b'not an image')
        self.clipboard.OpenClipboard.assert_not_called()
        self.windows.CreateWindowEx.assert_not_called()


class DrawerCopyTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'capture.png'
        self.path.write_bytes(png_bytes())
        with patch.object(drawer, 'GROQ_API_KEY', None):
            self.api = drawer.DrawerApi(str(self.path), (0, 0, 560, 680))

    def test_copies_original_capture_after_source_file_is_removed(self):
        self.path.unlink()
        with patch.object(drawer, 'copy_image_to_clipboard') as copy:
            self.assertEqual(self.api.copy_image(), dict(ok=True))
        copy.assert_called_once_with(png_bytes())

    def test_dependency_error_explains_how_to_install(self):
        with patch.object(drawer, 'copy_image_to_clipboard', side_effect=ImportError('win32clipboard')), self.assertLogs('shakesearch', level='ERROR'):
            result = self.api.copy_image()
        self.assertFalse(result['ok'])
        self.assertIn('pip install -r requirements.txt', result['error'])

    def test_clipboard_failure_is_returned_to_the_ui(self):
        with patch.object(drawer, 'copy_image_to_clipboard', side_effect=OSError('busy')), self.assertLogs('shakesearch', level='ERROR'):
            result = self.api.copy_image()
        self.assertFalse(result['ok'])
        self.assertIn('Riprova', result['error'])

    def test_missing_capture_does_not_call_clipboard(self):
        self.api.image_bytes = None
        with patch.object(drawer, 'copy_image_to_clipboard') as copy:
            self.assertFalse(self.api.copy_image()['ok'])
        copy.assert_not_called()
