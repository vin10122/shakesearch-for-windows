"""Exercise Lens DOM extraction against realistic page shapes, without Google traffic."""
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright
from lens_session import READ_RESULTS, classify

MENU = '''<header><a href="https://about.google/">Chi siamo</a>
<a href="https://store.google/">Google Store</a><a href="https://mail.google.com/">Gmail</a>
<a href="https://accounts.google.com/">Accedi</a><a href="https://www.google.com/search?udm=50">AI Mode</a></header>'''
FOOTER = '<footer>Italia <a href="https://ads.google.com/">Pubblicità</a> Soluzioni aziendali</footer>'
fixtures = [
    ('https://www.google.com/', MENU + '<main>Google Immagini</main>' + FOOTER, 'landing', None),
    ('https://www.google.com/search?q=test', MENU + '<main><p>' + 'Caricamento risultati ' * 12 + '</p><a href="https://about.google/">Chi siamo</a></main>' + FOOTER, 'loading', None),
    ('https://www.google.com/search?q=test', MENU + '''<main id="search"><div class="g">
       <a href="https://example.org/product"><h3>Tastiera meccanica</h3></a>
       <p>Tastiera compatta con tasti retroilluminati. Prezzo: 79 euro.</p>
       <div style="display:none">MENU NASCOSTO</div>
       <nav>MENU DEL RISULTATO</nav></div><a href="https://about.google/">Chi siamo</a></main>''' + FOOTER, 'results', 'Tastiera compatta'),
    ('https://lens.google.com/search?p=test', MENU + '''<div data-lpage="https://example.org/match">
       <a href="https://www.google.com/imgres?imgrefurl=https%3A%2F%2Fexample.org%2Fmatch">
       <img alt="Monitor da 27 pollici" width="100" height="100"></a></div>''' + FOOTER, 'results', 'Monitor da 27 pollici'),
    ('https://www.google.com/search?q=test', MENU + '''<main><section aria-label="Panoramica AI"><h2>Panoramica AI</h2>
       <p>La foto mostra un terminale Windows PowerShell con il risultato di un aggiornamento Git.</p>
       </section></main>''' + FOOTER, 'results', 'Windows PowerShell'),
    ('https://www.google.com/search?q=test', MENU + '''<main><article hidden>
       <a href="https://example.org/product"><h3>Risultato nascosto</h3></a></article></main>''' + FOOTER, 'loading', None),
]
with sync_playwright() as runner:
    browser = runner.chromium.launch(executable_path=os.getenv('CHROMIUM_EXECUTABLE') or None,
                                    headless=True, args=['--no-sandbox'])
    page = browser.new_page()
    for url, html, expected, phrase in fixtures:
        page.unroute('**/*')
        def serve(route):
            route.fulfill(status=200, content_type='text/html; charset=utf-8', body='<!doctype html><title>Google Lens</title>' + html)
        page.route('**/*', serve)
        page.goto(url)
        result = page.evaluate(READ_RESULTS)
        assert classify(result) == expected, (url, result)
        assert 'Chi siamo' not in result['text'] and 'Pubblicità' not in result['text'], result
        assert 'MENU NASCOSTO' not in result['text'] and 'MENU DEL RISULTATO' not in result['text'], result
        if phrase:
            assert phrase in result['text'], result
        else:
            assert not result['text'] and not result['links'], result
    browser.close()
print('PASS: homepage/menu rejection, delayed results, real cards, image matches, AI answer and hidden content exclusion')
