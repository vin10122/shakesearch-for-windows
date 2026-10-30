"""Experimental browser-native image handoff to Google Lens.

The browser posts directly to Google. The temporary loopback page never uploads
images to a public image host and never reads the user's browser profile.
"""
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import secrets
import threading
import webbrowser

from PIL import Image

LENS_UPLOAD_URL = 'https://lens.google/v3/upload?ep=gsbubb&hl=it'
HANDOFF_SECONDS = 120


def make_page(image_bytes, question, nonce):
    with Image.open(io.BytesIO(image_bytes)) as image:
        output = io.BytesIO()
        image.save(output, 'PNG')
    payload = json.dumps(dict(image=base64.b64encode(output.getvalue()).decode('ascii'),
                              question=question), ensure_ascii=True).replace('<', '\\u003c')
    page = '''<!doctype html>
<html lang="it"><head><meta charset="utf-8"><meta name="referrer" content="no-referrer">
<title>ShakeSearch · Google Lens</title>
<style nonce="NONCE">body{font:16px system-ui;background:#201812;color:#fdf8f5;margin:60px auto;max-width:650px;padding:20px}h1{color:#ff944d}a{color:#ffb077;margin-right:20px}p{line-height:1.5}</style>
</head><body><h1>Invio a Google Lens…</h1>
<p id="status">Apertura della ricerca nel browser.</p>
<div id="fallback" hidden><a id="save">Salva immagine</a><a href="https://lens.google/">Apri Google Lens</a>
<p>Carica l’immagine salvata in Lens. Puoi aggiungere la domanda dopo il caricamento.</p></div>
<form id="lens" action="UPLOAD_URL" method="post" enctype="multipart/form-data" accept-charset="UTF-8" hidden>
<input id="image" type="file" name="encoded_image" accept="image/png">
<input id="question" type="hidden" name="q">
</form>
<script nonce="NONCE">
const payload = PAYLOAD;
try {
  const bytes = Uint8Array.from(atob(payload.image), character => character.charCodeAt(0));
  const file = new File([bytes], 'shakesearch.png', {type: 'image/png'});
  const transfer = new DataTransfer();
  transfer.items.add(file);
  const input = document.getElementById('image');
  input.files = transfer.files;
  if (input.files.length !== 1) throw new Error('File input unsupported');
  document.getElementById('question').value = payload.question;
  const form = document.getElementById('lens');
  if (payload.question) {
    const target = new URL(form.action);
    target.searchParams.set('q', payload.question);
    form.action = target.toString();
  }
  form.submit();
} catch (error) {
  document.getElementById('status').textContent = 'Questo browser non ha avviato l’invio automatico. Puoi caricare la selezione manualmente.';
  const save = document.getElementById('save');
  save.href = 'data:image/png;base64,' + payload.image;
  save.download = 'shakesearch.png';
  document.getElementById('fallback').hidden = false;
}
</script></body></html>'''
    return page.replace('NONCE', nonce).replace('UPLOAD_URL', LENS_UPLOAD_URL).replace('PAYLOAD', payload).encode('utf-8')


class LensHandoff:
    def __init__(self, image_bytes, question=''):
        if not isinstance(question, str) or len(question) > 500:
            raise ValueError('La domanda deve contenere al massimo 500 caratteri.')
        self.closed = False
        self._lock = threading.Lock()
        self._nonce = secrets.token_urlsafe(24)
        self._path = '/' + secrets.token_urlsafe(24)
        self._page = make_page(image_bytes, question.strip(), self._nonce)
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                expected_host = f'127.0.0.1:{owner._server.server_port}'
                if self.headers.get('Host') != expected_host or self.path != owner._path:
                    self.send_error(404)
                    return
                with owner._lock:
                    page = owner._page
                    owner._page = None  # One delivery; keep no extra copy afterwards.
                if page is None:
                    self.send_error(410, 'Start a new search from ShakeSearch')
                    return
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(page)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Referrer-Policy', 'no-referrer')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Content-Security-Policy',
                    "default-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
                    f"script-src 'nonce-{owner._nonce}'; style-src 'nonce-{owner._nonce}'; "
                    'form-action https://lens.google https://lens.google.com '
                    'https://www.google.com https://consent.google.com')
                self.end_headers()
                self.wfile.write(page)

            def log_message(self, *args):
                pass  # Do not write image-bearing URLs or questions into access logs.

        self._server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self._thread = None
        self._timer = None

    @property
    def url(self):
        return f'http://127.0.0.1:{self._server.server_port}{self._path}'

    def open(self):
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        kwargs={'poll_interval': .1}, daemon=True)
        self._thread.start()
        self._timer = threading.Timer(HANDOFF_SECONDS, self.close)
        self._timer.daemon = True
        self._timer.start()
        try:
            if not webbrowser.open(self.url, new=2):
                raise RuntimeError('Impossibile aprire il browser predefinito.')
        except Exception:
            self.close()
            raise

    def close(self):
        with self._lock:
            if self.closed:
                return
            self.closed = True
            self._page = None
        if self._timer is not None:
            self._timer.cancel()
        if self._thread is not None:
            self._server.shutdown()
        self._server.server_close()
