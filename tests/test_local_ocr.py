import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch
from PIL import Image, ImageDraw, ImageFont
import local_ocr


def png(size=(300, 120)):
    stream = io.BytesIO()
    Image.new('RGB', size, 'white').save(stream, format='PNG')
    return stream.getvalue()


class LocalOcrTests(unittest.TestCase):
    def test_offline_result_preserves_unicode_and_removes_temporary_image(self):
        captured = []
        def recognize(command, **options):
            path = Path(command[command.index('-ImagePath') + 1])
            captured.append(path)
            self.assertTrue(path.is_file())
            self.assertIn('windows-ocr.ps1', ' '.join(command))
            self.assertEqual(options['timeout'], 45)
            return Mock(returncode=0, stdout=json.dumps(dict(text='Caffè\nSeconda riga')), stderr='')
        with patch.object(sys, 'platform', 'win32'), patch('local_ocr.subprocess.run', side_effect=recognize), patch('lens_process.LensProcessClient') as lens:
            self.assertEqual(local_ocr.extract_text(png())['text'], 'Caffè\nSeconda riga')
            lens.assert_not_called()
        self.assertFalse(captured[0].exists())

    def test_large_image_is_scaled_to_windows_limit(self):
        def recognize(command, **options):
            with Image.open(command[command.index('-ImagePath') + 1]) as image:
                self.assertEqual(image.size, (2600, 650))
            return Mock(returncode=0, stdout='{"text":""}', stderr='')
        with patch.object(sys, 'platform', 'win32'), patch('local_ocr.subprocess.run', side_effect=recognize):
            self.assertEqual(local_ocr.extract_text(png((5200, 1300)))['text'], '')

    def test_missing_language_and_timeout_are_actionable(self):
        with patch.object(sys, 'platform', 'win32'), patch('local_ocr.subprocess.run') as run:
            run.return_value = Mock(returncode=1, stderr='OCR_LANGUAGE_MISSING')
            with self.assertRaisesRegex(RuntimeError, 'lingua|language'):
                local_ocr.extract_text(png())
            run.side_effect = subprocess.TimeoutExpired('powershell', 45)
            with self.assertRaisesRegex(RuntimeError, 'tempo|timed out'):
                local_ocr.extract_text(png())

    def test_invalid_output_is_not_treated_as_recognized_text(self):
        with patch.object(sys, 'platform', 'win32'), patch('local_ocr.subprocess.run', return_value=Mock(returncode=0, stdout='not JSON')):
            with self.assertRaisesRegex(RuntimeError, 'OCR'):
                local_ocr.extract_text(png())

    @unittest.skipUnless(sys.platform == 'win32', 'Windows OCR integration requires Windows')
    def test_real_windows_ocr_reads_generated_image_offline(self):
        image = Image.new('RGB', (1000, 180), 'white')
        font = ImageFont.truetype(str(Path(os.environ['SystemRoot']) / 'Fonts' / 'arial.ttf'), 64)
        ImageDraw.Draw(image).text((30, 40), 'SHAKE SEARCH 123', font=font, fill='black')
        stream = io.BytesIO()
        image.save(stream, format='PNG')
        with patch('local_ocr.get_language', return_value='en-US'):
            text = local_ocr.extract_text(stream.getvalue())['text']
        self.assertIn('SEARCH', text.upper())
        self.assertIn('123', text)
