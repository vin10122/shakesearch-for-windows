"""Read Lens results through an isolated internal WebView, without exposing app APIs."""
import logging
import threading
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from lens_handoff import LensHandoff
logger = logging.getLogger('shakesearch')

READ_RESULTS = r'''(() => {
  const excluded = 'header, footer, nav, aside, form, button, [role="navigation"], [role="contentinfo"], [role="menu"], #foot, #footer, #fbar, #gb, script, style, [hidden], [aria-hidden="true"]';
  const visible = element => !element.closest(excluded) && element.getClientRects().length > 0 && getComputedStyle(element).visibility !== 'hidden';
  const cleanText = element => {
    const clone = element.cloneNode(true);
    const originals = element.querySelectorAll('*');
    const copies = clone.querySelectorAll('*');
    originals.forEach((node, index) => {
      const style = getComputedStyle(node);
      if (style.display === 'none' || style.visibility === 'hidden') copies[index].remove();
    });
    clone.querySelectorAll(excluded).forEach(node => node.remove());
    clone.querySelectorAll('br').forEach(node => node.replaceWith('\n'));
    clone.querySelectorAll('p, div, li, h1, h2, h3').forEach(node => node.append('\n'));
    return clone.textContent.replace(/[ \t]+/g, ' ').replace(/ *\n */g, '\n').replace(/\n{3,}/g, '\n\n').trim();
  };
  const destination = anchor => {
    try {
      const visual = anchor.closest('[data-lpage]');
      let url = new URL(visual?.getAttribute('data-lpage') || anchor.href, location.href);
      if (url.hostname === 'www.google.com' && url.pathname === '/url') {
        url = new URL(url.searchParams.get('q') || url.searchParams.get('url'));
      }
      if (url.hostname === 'www.google.com' && url.pathname === '/imgres') {
        url = new URL(url.searchParams.get('imgrefurl') || url.searchParams.get('imgurl'));
      }
      if (!['https:', 'http:'].includes(url.protocol)) return null;
      if (url.hostname.endsWith('.google') || /(^|\.)(google\.[a-z.]+|gstatic\.com|googleusercontent\.com|googleadservices\.com|googlesyndication\.com)$/.test(url.hostname)) return null;
      return url.href;
    } catch (_) { return null; }
  };
  const roots = Array.from(document.querySelectorAll('#rso, #search, main, [role="main"], [data-lpage], [data-docid]'));
  const links = [], cards = [], answers = [], seen = new Set();
  for (const root of roots) {
    const anchors = root.matches('a[href]') ? [root] : root.querySelectorAll('a[href]');
    for (const anchor of anchors) {
      if (!visible(anchor)) continue;
      const url = destination(anchor);
      if (!url || seen.has(url)) continue;
      const card = anchor.closest('article, [role="listitem"], .g, [data-lpage], [data-docid]');
      const heading = anchor.querySelector('h3') || card?.querySelector('h3');
      const thumbnail = anchor.querySelector('img');
      // A generic outbound link is not a search result: it needs a heading,
      // a visual-match thumbnail or a semantic result-card container.
      if (!heading && !thumbnail && !card) continue;
      const title = (heading?.innerText || thumbnail?.alt || anchor.innerText || anchor.getAttribute('aria-label') || '').trim();
      if (!title) continue;
      seen.add(url);
      links.push({title: title.slice(0, 220), url});
      cards.push(card ? cleanText(card) || title : title);
      if (links.length >= 8) break;
    }
    if (links.length >= 8) break;
  }
  const answerNodes = new Set(document.querySelectorAll(
    '[data-attrid="wa:/description"], [data-attrid="kc:/description"], [data-attrid="description"], [data-attrid="SGEAnswer"], [data-attrid*="ai_overview"], [aria-label="AI Overview"], [aria-label="Panoramica AI"]'));
  for (const heading of document.querySelectorAll('h2, h3, [role="heading"]')) {
    if (!/^(AI Overview|Panoramica AI)$/i.test(heading.textContent.trim())) continue;
    const block = heading.closest('section, article, [data-attrid]');
    if (block) answerNodes.add(block);
  }
  for (const node of answerNodes) {
    if (!visible(node)) continue;
    const text = cleanText(node);
    if (text.length >= 40 && !answers.includes(text)) answers.push(text);
  }
  const context = document.body?.innerText.slice(0, 4000) || '';
  const url = new URL(location.href);
  const searchPage = /^\/(search|v3\/search)(\/|$)/.test(url.pathname) ||
    (url.hostname === 'lens.google.com' && Boolean(document.querySelector('[data-lpage], [data-docid]')));
  return {url: location.href, title: document.title,
          text: [...answers, ...new Set(cards)].join('\n\n').slice(0, 6000), links,
          resultCount: cards.length, answerCount: answers.length, searchPage,
          landing: ['/', '/webhp', '/imghp'].includes(url.pathname),
          verification: /unusual traffic|traffico insolito|verify you are human|verifica di essere umano/i.test(context),
          complete: document.readyState === 'complete'};
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
    if snapshot.get('verification') or any(phrase in lower for phrase in ('unusual traffic', 'traffico insolito', 'verify you are human', 'verifica di essere umano')):
        return 'verification'
    if '404' in title or 'not found' in title.lower() or '403' in title:
        return 'error'
    if not snapshot.get('complete'):
        return 'loading'
    if snapshot.get('searchPage') and text and (snapshot.get('resultCount', 0) > 0 or snapshot.get('answerCount', 0) > 0):
        return 'results'
    if snapshot.get('landing'):
        return 'landing'
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
        landing_since = None
        last_state = None
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
            if state != last_state:
                parsed = urlsplit(snapshot['url'])
                logger.info('Lens reader: state=%s host=%s path=%s cards=%s answers=%s',
                            state, parsed.hostname, parsed.path,
                            snapshot.get('resultCount', 0), snapshot.get('answerCount', 0))
                last_state = state
            if state != 'landing':
                landing_since = None
            if state == 'verification':
                previous = None
                if not verification_shown:
                    verification_shown = True
                    self.window.show()
                    self.status('Google richiede un consenso o una verifica. Completa nella finestra Lens per continuare.')
                    deadline = time.monotonic() + 180
            elif state == 'error':
                self.result_url = None
                raise RuntimeError('Google Lens ha restituito una pagina di errore, non risultati.')
            elif state == 'landing':
                previous = None
                if landing_since is None:
                    landing_since = time.monotonic()
                elif time.monotonic() - landing_since > 8:
                    self.result_url = None
                    self.window.show()
                    raise RuntimeError('Lens ha aperto la pagina iniziale di Google, non i risultati. Ho mostrato la finestra Lens per controllare il caricamento.')
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
        self.result_url = None
        self.window.show()
        raise RuntimeError('Non sono riuscito a leggere risultati reali da Lens. Google potrebbe richiedere una verifica o aver cambiato la pagina.')

    def close(self):
        self._closed.set()
        if self.window is not None:
            try:
                self.window.destroy()
            except Exception:
                pass
