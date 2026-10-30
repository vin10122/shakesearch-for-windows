import io
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, ProxyHandler, build_opener
from urllib.parse import urlsplit

from PIL import Image
import drawer
from lens_handoff import LENS_UPLOAD_URL, LensHandoff, make_page


def image_bytes():
    output = io.BytesIO()
    Image.new('RGB', (80, 60), 'orange').save(output, 'PNG')
    return output.getvalue()


class LensHandoffTests(unittest.TestCase):
    def test_upload_uses_lens_service_host_not_marketing_site(self):
        target = urlsplit(LENS_UPLOAD_URL)
        self.assertEqual(target.scheme, 'https')
        self.assertEqual(target.hostname, 'lens.google.com')
        self.assertEqual(target.path, '/v3/upload')

    def setUp(self):
        self.opener = build_opener(ProxyHandler({}))  # Local loopback only.

    def handoff(self, question=''):
        handoff = LensHandoff(image_bytes(), question)
        self.addCleanup(handoff.close)
        with patch('lens_handoff.webbrowser.open', return_value=True) as browser:
            handoff.open()
        browser.assert_called_once_with(handoff.url, new=2)
        return handoff

    def test_page_delivered_once_and_contains_direct_browser_upload(self):
        handoff = self.handoff('Dove posso comprarlo?')
        with self.opener.open(handoff.url, timeout=2) as response:
            html = response.read().decode()
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
            self.assertEqual(response.headers['Referrer-Policy'], 'no-referrer')
            self.assertIn("frame-ancestors 'none'", response.headers['Content-Security-Policy'])
        self.assertIn('https://lens.google.com/v3/upload', html)
        self.assertNotIn('https://lens.google/v3/upload', html)
        self.assertIn('name="encoded_image"', html)
        self.assertIn('Dove posso comprarlo?', html)
        self.assertIsNone(handoff._page)
        with self.assertRaises(HTTPError) as error:
            self.opener.open(handoff.url, timeout=2)
        self.assertEqual(error.exception.code, 410)

    def test_wrong_token_and_host_cannot_read_capture(self):
        handoff = self.handoff()
        for request in (handoff.url + 'wrong', Request(handoff.url, headers={'Host': 'example.com'})):
            with self.assertRaises(HTTPError) as error:
                self.opener.open(request, timeout=2)
            self.assertEqual(error.exception.code, 404)
        with self.opener.open(handoff.url, timeout=2) as response:
            self.assertEqual(response.status, 200)

    def test_browser_failure_closes_server(self):
        handoff = LensHandoff(image_bytes())
        with patch('lens_handoff.webbrowser.open', return_value=False):
            with self.assertRaisesRegex(RuntimeError, 'browser'):
                handoff.open()
        self.assertTrue(handoff.closed)
        self.assertIsNone(handoff._page)
        self.assertEqual(handoff._server.socket.fileno(), -1)

    def test_unused_handoff_expires(self):
        with patch('lens_handoff.HANDOFF_SECONDS', .05):
            handoff = self.handoff()
        for _ in range(50):
            if handoff.closed:
                break
            time.sleep(.01)
        self.assertTrue(handoff.closed)
        self.assertIsNone(handoff._page)

    def test_question_is_data_not_executable_html(self):
        html = make_page(image_bytes(), '</script><script>alert(1)</script>', 'test-nonce').decode()
        self.assertEqual(html.count('</script>'), 1)
        self.assertIn('\\u003c/script>', html)

    def test_question_length_is_bounded(self):
        with self.assertRaises(ValueError):
            LensHandoff(image_bytes(), 'x' * 501)


class DrawerLensTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'capture.png'
        self.path.write_bytes(image_bytes())
        with patch.object(drawer, 'GROQ_API_KEY', None):
            self.api = drawer.DrawerApi(str(self.path), (0, 0, 560, 680))

    def test_sends_immutable_capture_and_question(self):
        self.path.write_bytes(b'new capture')
        with patch.object(drawer, 'LensHandoff') as factory:
            factory.return_value.closed = False
            self.assertEqual(self.api.send_to_lens('Che oggetto è?'), dict(ok=True))
        factory.assert_called_once_with(image_bytes(), 'Che oggetto è?')
        factory.return_value.open.assert_called_once()

    def test_missing_capture_does_not_open_browser(self):
        self.api.image_bytes = None
        with patch.object(drawer, 'LensHandoff') as factory:
            self.assertFalse(self.api.send_to_lens()['ok'])
        factory.assert_not_called()

    def test_browser_failure_is_reported_to_ui(self):
        with patch.object(drawer, 'LensHandoff') as factory, self.assertLogs('shakesearch', level='ERROR'):
            factory.return_value.open.side_effect = RuntimeError('no browser')
            result = self.api.send_to_lens()
        self.assertFalse(result['ok'])
        self.assertIn('browser', result['error'])
