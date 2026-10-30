"""Consent recovery in one browser context. Google traffic is entirely simulated."""
import html
import io
import json
import os
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlencode, urlsplit
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from playwright.sync_api import sync_playwright
from lens_session import LensSession
from lens_upload import ConsentRequired

image = io.BytesIO()
Image.new('RGB', (120, 80), 'orange').save(image, 'PNG')
CONSENT = 'https://consent.google.com/m'
with sync_playwright() as runner:
    browser = runner.chromium.launch(executable_path=os.getenv('CHROMIUM_EXECUTABLE') or None,
                                    headless=True, args=['--no-sandbox'])
    context = browser.new_context()
    views, uploads = [], []
    def route_google(route):
        request = route.request
        target = urlsplit(request.url)
        accepted = 'fixture_consent=accepted' in request.headers.get('cookie', '')
        def redirect(url):
            route.fulfill(status=200, content_type='text/html; charset=utf-8',
                          body='<script>location.replace(' + json.dumps(url) + ')</script>')
        if target.hostname == 'consent.google.com':
            if accepted:
                redirect('https://www.google.com/imghp')
            else:
                route.fulfill(status=200, content_type='text/html; charset=utf-8', body='''
                    <title>Google consent</title><h1>Choose consent</h1><button id="accept" onclick="
                    document.cookie='fixture_consent=accepted; Domain=.google.com; Path=/; Secure; SameSite=Lax';
                    location.href='https://www.google.com/imghp';">Accept (fixture)</button>''')
        elif target.hostname == 'www.google.com' and target.path == '/imghp':
            if not accepted:
                redirect(CONSENT)
            else:
                route.fulfill(status=200, content_type='text/html; charset=utf-8', body='<title>Google</title><main>Search by image<input type="file"></main>')
        elif target.hostname == 'lens.google.com' and target.path == '/v3/upload':
            assert accepted, 'The upload did not use the consented browser context'
            assert request.method == 'POST'
            assert b'\x89PNG' in request.post_data_buffer
            assert request.headers.get('origin') == 'https://www.google.com'
            uploads.append(request.post_data_buffer)
            redirect('https://lens.google.com/search?p=CONSENTED_IMAGE')
        elif target.hostname == 'lens.google.com' and target.path == '/search':
            assert accepted
            question = parse_qs(target.query).get('q', ['Ricerca immagine'])[0]
            route.fulfill(status=200, content_type='text/html; charset=utf-8', body=f'''
                <title>Google Lens</title><main><article><h3>Immagine trovata</h3><p>{html.escape(question)}</p>
                <a href="https://example.org/match">Pagina corrispondente</a></article></main>''')
        else:
            route.abort()
    class View:
        def __init__(self, title, **options):
            assert options['js_api'] is None
            self.page = context.new_page()
            self.page.route('**/*', route_google)
            self.page.goto(options['url'], wait_until='networkidle')
            self.show_count = 0
            self.events = None
            self.on_top = False
            views.append(self)
        def get_current_url(self): return self.page.url
        def evaluate_js(self, code): return self.page.evaluate(code)
        def load_url(self, url): self.page.goto(url, wait_until='networkidle')
        def show(self):
            self.show_count += 1
            # Test-only simulated human click. The application never clicks consent.
            if self.page.locator('#accept').count():
                self.page.locator('#accept').click()
                self.page.wait_for_url('https://www.google.com/imghp')
        def hide(self): pass
        def destroy(self): self.page.close()
    def blocked_upload(data):
        raise ConsentRequired(CONSENT)
    session = LensSession(image.getvalue(), window_factory=View, uploader=blocked_upload, timeout=10)
    try:
        answer = session.query('Spiega questa immagine')
        assert 'Spiega questa immagine' in answer['text']
        assert len(views) == 1 and views[0].show_count == 1 and len(uploads) == 1
        second = session.query('E questo dettaglio?')
        assert 'E questo dettaglio?' in second['text']
        assert len(views) == 1 and views[0].show_count == 1 and len(uploads) == 1
        print('PASS: one consent window, same-origin image upload with consent cookie, Lens reading and follow-ups in that same context')
    finally:
        session.close()
    # A subsequent capture reuses the dedicated browser profile's consent choice.
    next_session = LensSession(image.getvalue(), window_factory=View, uploader=blocked_upload, timeout=10)
    try:
        next_session.query()
        assert len(views) == 2 and views[1].show_count == 0 and len(uploads) == 2
        print('PASS: stored consent continues without another visible prompt on a new capture')
    finally:
        next_session.close()
    context.clear_cookies()
    def unused_upload(data):
        raise AssertionError('Visible Lens must upload through its own browser session')
    visible_session = LensSession(image.getvalue(), window_factory=View, uploader=unused_upload, timeout=10, visible=True)
    try:
        result = visible_session.query('Spiega il risultato visibile')
        assert 'Spiega il risultato visibile' in result['text']
        assert len(views) == 3 and len(uploads) == 3
        assert views[2].show_count >= 1 and not views[2].page.is_closed()
        print('PASS: clicking Lens opens the visible window, consent and upload use that context, results stay open')
    finally:
        visible_session.close()
        browser.close()
