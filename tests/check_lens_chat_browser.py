"""Optional Chromium check of internal Lens chat. All Google pages are fixtures."""
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
import drawer

image = io.BytesIO()
Image.new('RGB', (120, 80), 'orange').save(image, 'PNG')
with sync_playwright() as runner:
    browser = runner.chromium.launch(executable_path=os.getenv('CHROMIUM_EXECUTABLE') or None,
                                    headless=True, args=['--no-sandbox'])
    uploaded = []
    views = []
    def route_google(route):
        request = route.request
        url = urlsplit(request.url)
        if url.hostname == '127.0.0.1':
            route.continue_()
        elif url.hostname == 'lens.google.com' and url.path == '/v3/upload':
            assert request.method == 'POST'
            assert b'\x89PNG' in request.post_data_buffer
            uploaded.append(request.post_data_buffer)
            query = parse_qs(url.query).get('q', [''])[0]
            target = 'https://lens.google.com/search?' + urlencode({'p': 'IMAGE_SESSION', 'q': query})
            route.fulfill(status=200, content_type='text/html; charset=utf-8', body='<script>location.replace(' + json.dumps(target).replace('<', '\\u003c') + ')</script>')
        elif url.hostname == 'lens.google.com' and url.path == '/search':
            query = parse_qs(url.query).get('q', [''])[0]
            assert parse_qs(url.query)['p'] == ['IMAGE_SESSION']
            route.fulfill(status=200, content_type='text/html; charset=utf-8', body=f'''<!doctype html><title>Google Lens</title>
                <header><a href="https://about.google/">Chi siamo</a></header>
                <main><article><h3>Fixture Lens result</h3><p>{html.escape(query)}</p>
                <p>These are simulated search results used to verify reading from the browser, not invented AI answers.</p>
                <a href="https://example.org/product">Source article</a>
                <a href="https://www.google.com/preferences">Google settings</a>
                <a href="javascript:alert(1)">Invalid source</a></article></main>
                <footer>Italia Pubblicità Soluzioni aziendali</footer>''')
        else:
            route.abort()
    class View:
        def __init__(self, title, **options):
            assert options['js_api'] is None and options['hidden'] is True
            self.page = browser.new_page()
            self.page.route('**/*', route_google)
            self.page.goto(options['url'])
            views.append(self)
        def get_current_url(self): return self.page.url
        def evaluate_js(self, script): return self.page.evaluate(script)
        def load_url(self, url): self.page.goto(url)
        def hide(self): pass
        def show(self): pass
        def destroy(self): self.page.close()
    session = LensSession(image.getvalue(), window_factory=View, timeout=10)
    try:
        first = session.query('Che oggetto è? <img src=x onerror=alert(1)>')
        second = session.query('Dove posso comprarlo?')
        assert len(uploaded) == 1 and len(views) == 1
        assert 'Che oggetto è?' in first['text']
        assert 'Dove posso comprarlo?' in second['text']
        assert first['links'] == [{'title': 'Fixture Lens result', 'url': 'https://example.org/product'}]
        chat = browser.new_page()
        chat.set_content(drawer.HTML_TEMPLATE)
        chat.evaluate('''async results => {
          let index = 0;
          window.pywebview = {api: {send_to_lens: async () => {
            const result = results[index++];
            await new Promise(resolve => setTimeout(resolve, index === 1 ? 30 : 0));
            return {ok: true, ...result};
          }}};
          await Promise.all([askLens('prima domanda'), askLens('seconda domanda')]);
        }''', [first, second])
        replies = chat.locator('.chat-msg-ai')
        assert 'Che oggetto è?' in replies.nth(0).inner_text()
        assert 'Dove posso comprarlo?' in replies.nth(1).inner_text()
        assert chat.locator('.chat-msg-ai img').count() == 0
        assert chat.locator('.chat-msg-ai a').count() == 2
        print('PASS: internal image upload, actual DOM reading, follow-up session, safe chat rendering and separate reply bubbles')
    finally:
        session.close()
        browser.close()
