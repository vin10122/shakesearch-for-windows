import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import drawer


class WebViewProfileTests(unittest.TestCase):
    def test_consent_profile_is_dedicated_and_persistent(self):
        webview = MagicMock()
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / 'capture.png'
            image.write_bytes(b'capture')
            with patch.dict(os.environ, {'LOCALAPPDATA': directory}), \
                 patch.dict(sys.modules, {'webview': webview}), \
                 patch.object(drawer, 'GROQ_API_KEY', None), \
                 patch.object(drawer, 'GLOBAL_WINDOW', None):
                drawer.run_drawer_app(str(image), 0, 0, 560, 680)
            profile = Path(directory) / 'ShakeSearch' / 'WebViewProfile'
            self.assertTrue(profile.is_dir())
            webview.start.assert_called_once_with(private_mode=False, storage_path=str(profile))
