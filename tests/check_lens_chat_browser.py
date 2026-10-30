"""Optional Chromium check of internal Lens chat. All Google pages are fixtures."""
import html
import io
import httpx
import os
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from playwright.sync_api import sync_playwright
from lens_session import LensSession, READ_RESULTS, classify
from lens_upload import upload_image
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
        if url.hostname == 'lens.google.com' and url.path == '/search':
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
    def direct_request(request):
        assert request.url.host == 'lens.google.com' and request.url.path == '/v3/upload'
        assert request.method == 'POST' and b'\x89PNG' in request.content
        assert not views  # No WebView is created until the upload is accepted.
        uploaded.append(request.content)
        return httpx.Response(303, headers={'Location': 'https://lens.google.com/search?p=IMAGE_SESSION'})
    def direct_upload(data):
        with httpx.Client(transport=httpx.MockTransport(direct_request), follow_redirects=False) as client:
            return upload_image(data, client=client)
    session = LensSession(image.getvalue(), window_factory=View, timeout=10, uploader=direct_upload)
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
          window.pywebview = {api: {
            send_to_lens: async () => ({ok: true, job_id: String(index++)}),
            poll_lens: async token => {
              await new Promise(resolve => setTimeout(resolve, token === '0' ? 30 : 0));
              return {done: true, status: 'Read', result: {ok: true, ...results[Number(token)]}};
            }
          }};
          await Promise.all([askLens('prima domanda'), askLens('seconda domanda')]);
        }''', [first, second])
        replies = chat.locator('.chat-msg-ai')
        assert 'Che oggetto è?' in replies.nth(0).inner_text()
        assert 'Dove posso comprarlo?' in replies.nth(1).inner_text()
        assert chat.locator('.chat-msg-ai img').count() == 0
        assert chat.locator('.chat-msg-ai a').count() == 2
        chat.evaluate('''() => {
          window.lensAnswerReady = false;
          pywebview.api.poll_lens = async () => window.lensAnswerReady
            ? {done: true, result: {ok: true, interpreted: true, text: 'Spiegazione API', links: [{title: 'Fonte Lens', url: 'https://example.org/source'}]}}
            : {done: false, status: 'Risultati Lens ricevuti. L’AI sta preparando la risposta…'};
          window.pendingLensAnswer = askLens('Spiegami i risultati');
        }''')
        chat.wait_for_function("document.querySelectorAll('.chat-msg-ai')[2].textContent.includes('AI sta preparando')")
        chat.evaluate('async () => { window.lensAnswerReady = true; await window.pendingLensAnswer; }')
        assert 'Risposta AI basata sui risultati Lens' in replies.nth(2).inner_text()
        assert 'Spiegazione API' in replies.nth(2).inner_text()
        assert replies.nth(2).locator('a').get_attribute('href') == 'https://example.org/source'
        chat.evaluate('''async () => {
          window.lensWasCancelled = false;
          pywebview.api.send_to_lens = async () => {throw new Error('Disconnected bridge');};
          pywebview.api.cancel_lens = async () => {window.lensWasCancelled = true;};
          await askLens('Bridge failure');
        }''')
        assert 'non ha completato' in replies.nth(3).inner_text()
        assert chat.evaluate('lensWasCancelled')
        print('PASS: progress replaces the waiting bubble, API interpretation retains source links, bridge failures terminate the request')
        google = views[0].page
        google.set_content('''<title>Google</title><div role="dialog"><h1>Prima di passare alla Ricerca Google</h1>
            <p>Utilizziamo cookie e dati per fornire i servizi.</p><form>
            <button>Rifiuta tutto</button><button>Accetta tutto</button></form></div>''')
        assert classify(google.evaluate(READ_RESULTS)) == 'verification'
        google.set_content('''<title>Google</title><main><h3>Cookie documentation</h3></main>
            <div hidden>Prima di continuare <button>Accetta tutto</button></div>''')
        assert classify(google.evaluate(READ_RESULTS)) != 'verification'
        print('PASS: inline Google consent is detected without mistaking hidden consent controls for a challenge')
        print('PASS: direct Python upload before any WebView, hidden results reading, image-session follow-ups and safe chat replies')
    finally:
        session.close()
        browser.close()
