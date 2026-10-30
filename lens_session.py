"""Read Lens results through an isolated internal WebView, without exposing app APIs."""
import base64
import io
import json
import logging
import threading
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from PIL import Image

from lens_upload import ConsentRequired, upload_image, result_url as is_image_result_url
from lens_handoff import LENS_UPLOAD_URL
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
  // Google also embeds consent in a dialog on www.google.com, without
  // navigating to consent.google.com. Inspect controls separately from results.
  const controls = Array.from(document.querySelectorAll('button, [role="button"], input[type="submit"]'))
    .filter(node => node.getClientRects().length > 0 && getComputedStyle(node).visibility !== 'hidden')
    .map(node => (node.innerText || node.value || node.getAttribute('aria-label') || '').trim());
  const inlineConsent = /before you continue|prima di continuare|prima di passare|we use cookies|utilizziamo cookie/i.test(document.body?.innerText || '') &&
    controls.some(text => /accept all|reject all|accetta tutto|rifiuta tutto|i agree|accetto/i.test(text));
  const url = new URL(location.href);
  const searchPage = /^\/(search|v3\/search)(\/|$)/.test(url.pathname) ||
    (url.hostname === 'lens.google.com' && Boolean(document.querySelector('[data-lpage], [data-docid]')));
  return {url: location.href, title: document.title,
          text: [...answers, ...new Set(cards)].join('\n\n').slice(0, 6000), links,
          resultCount: cards.length, answerCount: answers.length, searchPage,
          landing: ['/', '/webhp', '/imghp'].includes(url.pathname),
          uploadPrompt: Boolean(document.querySelector('input[type="file"]')) && /drag an image|trascina un'immagine|carica un file|upload a file/i.test(context),
          verification: inlineConsent || /unusual traffic|traffico insolito|verify you are human|verifica di essere umano/i.test(context),
          interactiveChallenge: Array.from(document.querySelectorAll('button, [role="button"], input:not([type="hidden"]), iframe[src*="recaptcha"]'))
            .some(node => node.getClientRects().length > 0 && getComputedStyle(node).visibility !== 'hidden'),
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
    if snapshot.get('landing') or snapshot.get('uploadPrompt'):
        return 'landing'
    return 'loading'


class LensSession:
    def __init__(self, image_bytes, window_factory=None, status=None, timeout=45, uploader=None, visible=False):
        self.image_bytes = image_bytes
        self.uploader = uploader or upload_image
        self.window_factory = window_factory
        self.status = status or (lambda text: None)
        self.timeout = timeout
        self.visible = visible
        self.window = None
        self.result_url = None
        self._image_result_url = None
        self._browser_session = False
        self._consent_visible = False
        self._consent_rounds = 0
        self._in_view_upload = False
        self._cancelled = threading.Event()
        self._lock = threading.Lock()
        self._closed = threading.Event()

    def _navigate(self, target):
        if not google_url(target):
            raise RuntimeError('La finestra Lens può aprire soltanto pagine Google autorizzate.')
        if self.window is None:
            factory = self.window_factory
            if factory is None:
                import webview
                factory = webview.create_window
            self.window = factory('ShakeSearch · Consenso Google Lens', url=target, hidden=True,
                                  js_api=None, width=900, height=740, on_top=False)
            window = self.window
            def on_closed():
                if self.window is window:
                    self.window = None
                    self._consent_visible = False
                    self._cancelled.set()
            try:
                self.window.events.closed += on_closed
            except (AttributeError, TypeError):
                pass  # Minimal test adapters may not implement window events.
        else:
            self.window.load_url(target)
        if self._closed.is_set():
            self.close()
            raise RuntimeError('La sessione Lens è stata chiusa.')
        if self.visible:
            self.window.on_top = True
            self.window.show()

    def _show_consent(self, verification=True):
        if not self._consent_visible:
            self._consent_rounds += 1
            self._consent_visible = True
            self.window.on_top = True
            self.window.show()
            self.status('Completa il consenso nella finestra Google. Riprenderò automaticamente da quella stessa sessione.'
                        if verification else 'Lens non ha ancora fornito risultati leggibili. Mostro la stessa finestra Google e continuo ad attendere la risposta.')

    def _upload_in_browser(self):
        # Execute only on Google's own origin, after the user's consent. The
        # same WebView sends its own cookies; none are copied into Python.
        with Image.open(io.BytesIO(self.image_bytes)) as image:
            output = io.BytesIO()
            image.save(output, 'PNG')
            payload = dict(image=base64.b64encode(output.getvalue()).decode('ascii'),
                           width=image.width, height=image.height, target=LENS_UPLOAD_URL)
        data = json.dumps(payload).replace('<', '\\u003c')
        script = r'''(() => {
          if (location.protocol !== 'https:' || !['www.google.com', 'lens.google.com'].includes(location.hostname))
            return {ok:false};
          const payload = PAYLOAD;
          const bytes = Uint8Array.from(atob(payload.image), value => value.charCodeAt(0));
          const transfer = new DataTransfer();
          transfer.items.add(new File([bytes], 'shakesearch.png', {type:'image/png'}));
          const form = document.createElement('form');
          form.method = 'POST'; form.action = payload.target; form.enctype = 'multipart/form-data';
          const file = document.createElement('input'); file.type = 'file'; file.name = 'encoded_image';
          file.files = transfer.files; form.appendChild(file);
          if (file.files.length !== 1) return {ok:false};
          for (const [name,value] of Object.entries({image_url:'',original_width:payload.width,original_height:payload.height})) {
            const field = document.createElement('input'); field.type = 'hidden'; field.name = name;
            field.value = String(value); form.appendChild(field);
          }
          form.hidden = true; document.body.appendChild(form);
          setTimeout(() => form.submit(), 50);
          return {ok:true};
        })()'''.replace('PAYLOAD', data)
        result = self.window.evaluate_js(script)
        if not isinstance(result, dict) or not result.get('ok'):
            raise RuntimeError('Non sono riuscito a inviare automaticamente il file dalla sessione Google autorizzata.')
        self.status('Consenso acquisito. Invio l’immagine dalla stessa sessione Google…')

    def query(self, question=''):
        if not isinstance(question, str) or len(question) > 500:
            raise ValueError('Scrivi una domanda di massimo 500 caratteri.')
        with self._lock:
            if self._closed.is_set():
                raise RuntimeError('La sessione Lens è stata chiusa.')
            self._cancelled.clear()
            self._consent_rounds = 0
            self._in_view_upload = False
            browser_upload = False
            if self.result_url is not None:
                self._navigate(followup_url(self.result_url, question))
            elif self._browser_session or self.visible:
                self.status('Apro Google Lens. Completa eventuali richieste nella finestra Google…')
                browser_upload = True
                self._navigate('https://www.google.com/imghp?hl=it')
            else:
                self.status('Invio diretto dell’immagine a Google Lens…')
                try:
                    target = self.uploader(self.image_bytes)
                except ConsentRequired as consent:
                    self._browser_session = True
                    browser_upload = True
                    self._navigate(consent.url)
                else:
                    if not is_image_result_url(target):
                        raise RuntimeError('Google Lens non ha confermato una ricerca associata all’immagine.')
                    self._image_result_url = target
                    self._navigate(followup_url(target, question) if question else target)
            result = self._read_results(allow_upload=browser_upload)
            # An image posted after consent is first identified without a text
            # query. Apply the optional question after the visual session exists.
            if (browser_upload or self._in_view_upload) and question:
                self._navigate(followup_url(self.result_url, question))
                result = self._read_results()
            return result

    def _read_results(self, allow_upload=False):
        deadline = time.monotonic() + self.timeout
        previous = None
        landing_since = None
        last_state = None
        uploaded_in_view = False
        upload_navigation_done = False
        revealed = False
        read_error_logged = False
        consent_deadline = None
        if self._consent_visible or self.visible:
            deadline = time.monotonic() + 180
        while time.monotonic() < deadline and not self._closed.is_set() and not self._cancelled.is_set():
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
                if not read_error_logged:
                    logger.exception('Lens DOM read failed during navigation')
                    read_error_logged = True
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
                if not snapshot.get('complete') or not snapshot.get('interactiveChallenge', True):
                    time.sleep(.25)
                    continue
                self._browser_session = True
                if not self._consent_visible:
                    self._show_consent()
                    if consent_deadline is None:
                        consent_deadline = time.monotonic() + 180
                    deadline = consent_deadline
                allow_upload = True
                uploaded_in_view = False
            elif self._consent_visible and state != 'loading':
                # Consent has finished in this exact WebView/cookie context.
                if not self.visible:
                    self.window.hide()
                    self.window.on_top = False
                self._consent_visible = False
                deadline = time.monotonic() + self.timeout
                self.status('Consenso completato. Attendo i risultati di Lens…')
                continue
            elif state == 'error':
                if allow_upload and not uploaded_in_view and not upload_navigation_done:
                    # A consent redirect can lose the original POST body and
                    # land on a GET-only upload error. Repost from Google origin.
                    self._navigate('https://www.google.com/imghp?hl=it')
                    upload_navigation_done = True
                    previous = None
                    continue
                self.result_url = None
                raise RuntimeError('Google Lens ha restituito una pagina di errore, non risultati.')
            elif state == 'landing':
                previous = None
                if allow_upload and not uploaded_in_view and snapshot.get('complete'):
                    self._upload_in_browser()
                    self._in_view_upload = True
                    uploaded_in_view = True
                    landing_since = None
                    deadline = time.monotonic() + self.timeout
                elif landing_since is None:
                    landing_since = time.monotonic()
                elif time.monotonic() - landing_since > 8:
                    self.result_url = None
                    raise RuntimeError('Google Lens ha restituito il modulo di caricamento invece dei risultati. L’immagine non è stata associata a una ricerca leggibile.')
            elif state == 'results':
                signature = (snapshot['url'], snapshot.get('text'), repr(snapshot.get('links')))
                if previous == signature:
                    self.result_url = snapshot['url'] if is_image_result_url(snapshot['url']) else self._image_result_url
                    if not self.result_url:
                        raise RuntimeError('Lens non ha mantenuto il riferimento all’immagine dopo il consenso.')
                    if not self.visible:
                        self.window.hide()
                    return dict(text=snapshot.get('text', ''), links=snapshot.get('links', []))
                previous = signature
            else:
                previous = None
            # A hidden WebView may defer rendering, or Google may use a new
            # challenge layout. Reuse the existing window once, rather than
            # silently timing out without ever showing what needs attention.
            if state == 'loading' and not self._consent_visible and not revealed and time.monotonic() >= deadline - 5:
                self._show_consent(verification=False)
                revealed = True
                deadline = time.monotonic() + 180
            time.sleep(.35)
        if self._closed.is_set():
            raise RuntimeError('La sessione Lens è stata chiusa.')
        self.result_url = None
        if self._cancelled.is_set():
            raise RuntimeError('La finestra Google è stata chiusa prima di completare la ricerca. Puoi riprovare.')
        if self._consent_visible:
            raise RuntimeError('Google non ha fornito risultati leggibili. Controlla la pagina nella finestra Lens aperta, completa eventuali verifiche e riprova.')
        raise RuntimeError('Non sono riuscito a leggere risultati reali da Lens. Google potrebbe richiedere una verifica o aver cambiato la pagina.')

    def close(self):
        self._closed.set()
        if self.window is not None:
            try:
                self.window.destroy()
            except Exception:
                pass
