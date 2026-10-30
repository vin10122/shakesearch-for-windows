from email import policy
from email.parser import BytesParser
import io
import unittest

import httpx
from PIL import Image
from lens_upload import ConsentRequired, upload_image, result_url

URL = 'https://lens.google.com/search?p=IMAGE_SESSION'


def png():
    stream = io.BytesIO()
    Image.new('RGB', (13, 7), (30, 70, 120)).save(stream, 'PNG')
    return stream.getvalue()


class DirectLensUploadTests(unittest.TestCase):
    def client(self, handler):
        client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
        self.addCleanup(client.close)
        return client

    def test_posts_real_image_bytes_and_waits_for_visual_search_redirect(self):
        seen = []
        def handle(request):
            seen.append(request)
            self.assertEqual(request.method, 'POST')
            self.assertEqual(request.url.host, 'lens.google.com')
            self.assertEqual(request.url.path, '/v3/upload')
            self.assertNotIn('q', request.url.params)
            content_type = request.headers['content-type']
            self.assertIn('multipart/form-data; boundary=', content_type)
            message = BytesParser(policy=policy.default).parsebytes(
                ('Content-Type: ' + content_type + '\r\n\r\n').encode() + request.content)
            parts = {part.get_param('name', header='content-disposition'): part for part in message.iter_parts()}
            self.assertEqual(parts['encoded_image'].get_filename(), 'shakesearch.png')
            self.assertEqual(parts['encoded_image'].get_content_type(), 'image/png')
            with Image.open(io.BytesIO(parts['encoded_image'].get_payload(decode=True))) as image:
                self.assertEqual(image.size, (13, 7))
                self.assertEqual(image.getpixel((0, 0)), (30, 70, 120))
            self.assertEqual(parts['original_width'].get_payload(decode=True), b'13')
            return httpx.Response(303, headers={'Location': URL})
        self.assertEqual(upload_image(png(), client=self.client(handle)), URL)
        self.assertEqual(len(seen), 1)

    def test_homepage_redirect_means_image_not_accepted(self):
        client = self.client(lambda request: httpx.Response(302, headers={'Location': 'https://www.google.com/imghp'}))
        with self.assertRaisesRegex(RuntimeError, 'non è stato accettato'):
            upload_image(png(), client=client)

    def test_empty_upload_form_is_not_a_response(self):
        client = self.client(lambda request: httpx.Response(200, text='<title>Google</title><input type="file">'))
        with self.assertRaisesRegex(RuntimeError, 'non ha restituito una ricerca'):
            upload_image(png(), client=client)

    def test_consent_and_captcha_are_reported_without_opening_windows(self):
        for target in ('https://consent.google.com/m', 'https://accounts.google.com/login', 'https://www.google.com/sorry/index'):
            with self.subTest(target=target):
                client = self.client(lambda request: httpx.Response(302, headers={'Location': target}))
                with self.assertRaises(ConsentRequired) as error:
                    upload_image(png(), client=client)
                self.assertEqual(error.exception.url, target)

    def test_blocked_upload_is_reported(self):
        for status in (403, 429, 500):
            client = self.client(lambda request: httpx.Response(status))
            with self.assertRaisesRegex(RuntimeError, str(status)):
                upload_image(png(), client=client)

    def test_foreign_redirect_is_not_followed(self):
        calls = []
        def handle(request):
            calls.append(request)
            return httpx.Response(302, headers={'Location': 'https://example.org/steal'})
        with self.assertRaisesRegex(RuntimeError, 'inatteso'):
            upload_image(png(), client=self.client(handle))
        self.assertEqual(len(calls), 1)

    def test_html_redirect_to_image_result_is_supported(self):
        for text in (f'<meta http-equiv="refresh" content="0;URL={URL}">',
                     f'<script>window.location.replace("{URL}")</script>'):
            with self.subTest(html=text):
                client = self.client(lambda request: httpx.Response(200, text=text))
                self.assertEqual(upload_image(png(), client=client), URL)

    def test_plain_text_search_does_not_confirm_an_image_upload(self):
        self.assertFalse(result_url('https://www.google.com/search?q=what+is+this'))
        self.assertFalse(result_url('https://evil.example/search?p=token'))
        self.assertTrue(result_url('https://www.google.com/search?vsrid=token&q=question'))
