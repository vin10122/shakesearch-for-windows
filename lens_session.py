"""Read Lens results through an isolated internal WebView, without exposing app APIs."""
import threading
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from lens_handoff import LensHandoff

READ_RESULTS = r'''(() => {
  const root = document.querySelector('main, [role="main"], #search, #rso');
  const text = (root || document.body).innerText.trim();
  const links = [];
  const seen = new Set();
  for (const anchor of (root || document.body).querySelectorAll('a[href]')) {
    try {
      let url = new URL(anchor.href, location.href);
      if (url.hostname === 'www.google.com' && url.pathname === '/url') {
        url = new URL(url.searchParams.get('q') || url.searchParams.get('url'));
      }
      if (!['https:', 'http:'].includes(url.protocol)) continue;
      if (/(^|\.)(google\.[a-z.]+|gstatic\.com|googleusercontent\.com)$/.test(url.hostname)) continue;
      const title = (anchor.innerText || anchor.querySelector('img')?.alt || '').trim();
      if (!title || seen.has(url.href)) continue;
      seen.add(url.href); links.push({title: title.slice(0, 220), url: url.href});
      if (links.length === 8) break;
    } catch (_) {}
  }
  return {url: location.href, title: document.title, text: text.slice(0, 6000), links,
          complete: document.readyState === 'complete', hasMain: Boolean(root)};
})()'''


def google_url(url):
    parsed = urlsplit(url or '')
    return parsed.scheme == 'https' and parsed.hostname in {
        'lens.google.com', 'www.google.com', 'consent.google.com', 'accounts.google.com'}


def followup_url(url, question):
    if not google_url(url) or urlsplit(url).hostname in {'consent.google.com', 'accounts.google.com'}:
        raise RuntimeError('La sessione Lens non contiene ancora una ricerca valida.')
    parts = urlsplit(url)
    parameters = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key != 'q']
    parameters.append(('q', question))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(parameters), parts.fragment))


def classify(snapshot):
    url = urlsplit(snapshot.get('url', ''))
    text = snapshot.get('text', '')
    title = snapshot.get('title', '')
    lower = text.lower()
    if url.hostname in {'consent.google.com', 'accounts.google.com'} or '/sorry/' in url.path:
        return 'verification'
    if any(phrase in lower for phrase in ('unusual traffic', 'traffico insolito', 'verify you are human', 'verifica di essere umano')):
        return 'verification'
    if '404' in title or 'not found' in title.lower() or '403' in title:
        return 'error'
    if not snapshot.get('complete'):
        return 'loading'
    if snapshot.get('links') or (snapshot.get('hasMain') and len(text) > 80):
        return 'results'
    return 'loading'


class LensSession:
    def __init__(self, image_bytes, window_factory=None, status=None, timeout=45):
        self.image_bytes = image_bytes
        self.window_factory = window_factory
        self.status = status or (lambda text: None)
        self.timeout = timeout
        self.window = None
        self.result_url = None
        self._lock = threading.Lock()
        self._closed = threading.Event()

    def query(self, question=''):
        if not isinstance(question, str) or len(question) > 500:
            raise ValueError('Scrivi una domanda di massimo 500 caratteri.')
        with self._lock:
            if self._closed.is_set():
                raise RuntimeError('La sessione Lens è stata chiusa.')
            handoff = None
            try:
                if self.result_url is not None:
                    target = followup_url(self.result_url, question)
                else:
                    handoff = LensHandoff(self.image_bytes, question)
                    handoff.start()
                    target = handoff.url
                if self.window is None:
                    factory = self.window_factory
                    if factory is None:
                        import webview
                        factory = webview.create_window
                    self.window = factory('Google Lens · Verifica', url=target, hidden=True,
                                          js_api=None, width=900, height=740, on_top=True)
                else:
                    self.window.load_url(target)
                if self._closed.is_set():
                    self.close()  # The chat may have closed while the WebView was being created.
                    raise RuntimeError('La sessione Lens è stata chiusa.')
                self.status('Lens sta cercando sulla selezione…')
                return self._read_results()
            finally:
                if handoff is not None:
                    handoff.close()

    def _read_results(self):
        deadline = time.monotonic() + self.timeout
        verification_shown = False
        previous = None
        while time.monotonic() < deadline and not self._closed.is_set():
            try:
                current = self.window.get_current_url()
                if not current or current.startswith(('http://127.0.0.1:', 'about:')):
                    time.sleep(.25)
                    continue
                if current.startswith(('chrome-error:', 'edge-error:')):
                    raise RuntimeError('La finestra interna non riesce a raggiungere Google Lens. Controlla la connessione e riprova.')
                if not google_url(current):
                    raise RuntimeError('Lens ha aperto una pagina esterna inattesa; non la leggerò come risultato.')
                snapshot = self.window.evaluate_js(READ_RESULTS)
            except RuntimeError:
                raise
            except Exception:
                time.sleep(.25)  # Navigation may temporarily invalidate the WebView document.
                continue
            if not isinstance(snapshot, dict) or not google_url(snapshot.get('url')):
                time.sleep(.25)
                continue
            state = classify(snapshot)
            if state == 'verification':
                previous = None
                if not verification_shown:
                    verification_shown = True
                    self.window.show()
                    self.status('Google richiede un consenso o una verifica. Completa nella finestra Lens per continuare.')
                    deadline = time.monotonic() + 180
            elif state == 'error':
                raise RuntimeError('Google Lens ha restituito una pagina di errore, non risultati.')
            elif state == 'results':
                signature = (snapshot['url'], snapshot.get('text'), repr(snapshot.get('links')))
                if previous == signature:
                    self.result_url = snapshot['url']
                    self.window.hide()
                    return dict(text=snapshot.get('text', ''), links=snapshot.get('links', []))
                previous = signature
            else:
                previous = None
            time.sleep(.35)
        if self._closed.is_set():
            raise RuntimeError('La sessione Lens è stata chiusa.')
        raise RuntimeError('Non sono riuscito a leggere risultati reali da Lens. Google potrebbe richiedere una verifica o aver cambiato la pagina.')

    def close(self):
        self._closed.set()
        if self.window is not None:
            try:
                self.window.destroy()
            except Exception:
                pass
