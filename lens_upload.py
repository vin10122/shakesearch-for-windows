"""Direct multipart upload to the Lens web endpoint; never open an upload window."""
from html import unescape
from html.parser import HTMLParser
import io
import json
import re
from urllib.parse import parse_qs, urljoin, urlsplit

import httpx
from PIL import Image

from lens_handoff import LENS_UPLOAD_URL

GOOGLE_HOSTS = {'lens.google.com', 'www.google.com', 'consent.google.com', 'accounts.google.com'}


def result_url(url):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname not in {'lens.google.com', 'www.google.com'}:
        return False
    if parsed.username or parsed.password or parsed.port not in (None, 443):
        return False
    if parsed.path.rstrip('/') not in ('/search', '/v3/search'):
        return False
    params = parse_qs(parsed.query)
    return any(params.get(name) for name in ('p', 'vsrid', 'vsint', 'gsessionid'))


class RedirectLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == 'a' and attrs.get('href'):
            self.urls.append(attrs['href'])
        if tag == 'meta' and attrs.get('http-equiv', '').lower() == 'refresh':
            content = attrs.get('content', '')
            if 'url=' in content.lower():
                self.urls.append(re.split('url=', content, maxsplit=1, flags=re.I)[1].strip(' \"\''))


def html_result_url(html, base):
    parser = RedirectLinks()
    parser.feed(html)
    # Some upload responses redirect in HTML/JavaScript rather than a Location
    # header. Read string literals only; do not execute response code in Python.
    for match in re.finditer(r'(?:window\.)?location(?:\.href)?\s*(?:=|\.replace\()\s*("(?:[^"\\]|\\.)*")', html):
        try:
            parser.urls.append(json.loads(match.group(1)))
        except ValueError:
            continue
    for candidate in parser.urls:
        target = urljoin(base, unescape(candidate))
        if result_url(target):
            return target
    return None


def upload_image(image_bytes, *, client=None):
    with Image.open(io.BytesIO(image_bytes)) as image:
        width, height = image.size
        output = io.BytesIO()
        image.save(output, 'PNG')
    owned = client is None
    if owned:
        client = httpx.Client(timeout=httpx.Timeout(30, connect=10), follow_redirects=False,
                              headers={'Accept': 'text/html,application/xhtml+xml'})
    try:
        response = client.post(
            LENS_UPLOAD_URL,
            files={'encoded_image': ('shakesearch.png', output.getvalue(), 'image/png')},
            data={'image_url': '', 'original_width': str(width), 'original_height': str(height)},
        )
        for _ in range(6):
            if response.status_code in (403, 429):
                raise RuntimeError(f'Google Lens ha bloccato la richiesta diretta (HTTP {response.status_code}). Non ho ricevuto risultati da trascrivere.')
            if response.status_code >= 400:
                raise RuntimeError(f'Google Lens ha restituito un errore HTTP {response.status_code}. Nessun risultato ricevuto.')
            if result_url(str(response.url)):
                return str(response.url)
            if response.is_redirect:
                target = urljoin(str(response.url), response.headers.get('location', ''))
                parsed = urlsplit(target)
                if parsed.scheme != 'https' or parsed.hostname not in GOOGLE_HOSTS or parsed.username or parsed.password or parsed.port not in (None, 443):
                    raise RuntimeError('Google Lens ha restituito un reindirizzamento inatteso; invio interrotto.')
                if parsed.hostname in {'consent.google.com', 'accounts.google.com'} or '/sorry/' in parsed.path:
                    raise RuntimeError('Google richiede un consenso, un accesso o una verifica: la richiesta automatica non è stata completata.')
                if result_url(target):
                    return target
                if parsed.path in ('/', '/imghp', '/webhp'):
                    raise RuntimeError('Google ha riaperto il caricamento immagini: il file non è stato accettato da Lens.')
                response = client.get(target)
            else:
                target = html_result_url(response.text, str(response.url))
                if target:
                    return target
                raise RuntimeError('Google Lens non ha restituito una ricerca associata all’immagine. Non ci sono risultati verificati da trascrivere.')
        raise RuntimeError('Troppi reindirizzamenti nella risposta di Google Lens.')
    finally:
        if owned:
            client.close()
