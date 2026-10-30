"""Exercise language switching in the actual drawer DOM, without external APIs."""
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from playwright.sync_api import sync_playwright
import drawer
from localization import catalog


with sync_playwright() as runner:
    browser = runner.chromium.launch(executable_path=os.getenv('CHROMIUM_EXECUTABLE') or None,
                                    headless=True, args=['--no-sandbox'])
    page = browser.new_page()
    page.set_content(drawer.HTML_TEMPLATE)
    page.evaluate('''settings => {
      window.catalogs = settings;
      pywebview = {api: {
        set_language: async language => ({ok: true, language, translations: catalogs[language]}),
        send_to_lens: async () => ({ok: false, error: 'Immagine non disponibile. Esegui una nuova cattura.'}),
        toggle_fullscreen: () => {}
      }};
      applyLanguage({language: 'it', translations: catalogs.it});
      document.getElementById('lensQuestion').value = 'Keep this question';
      document.getElementById('lensChatMode').checked = true;
      updateAiResponse('Unused', 'missing');
      createChatTurn('User text: Copia immagine', 'ai');
    }''', dict(it=catalog('it'), en=catalog('en')))
    page.select_option('#languageSelect', 'en')
    page.wait_for_function("document.documentElement.lang === 'en'")
    assert page.locator('#copyImageButton').inner_text().endswith('Copy image')
    assert page.locator('#sendToLensButton').inner_text() == 'Send to Lens'
    assert page.locator('#queryInput').get_attribute('placeholder') == 'Ask anything or circle...'
    assert page.locator('#lensQuestion').input_value() == 'Keep this question'
    assert page.locator('#lensChatMode').is_checked()
    assert page.locator('.chat-msg-user').inner_text() == 'User text: Copia immagine'
    page.evaluate("async () => { toggleFs(); await askLens('Question'); }")
    assert page.locator('#fsActionLabel').inner_text() == '🗗 Window'
    assert 'Image unavailable' in page.locator('.chat-msg-ai').last.inner_text()
    page.select_option('#languageSelect', 'it')
    page.wait_for_function("document.documentElement.lang === 'it'")
    assert page.locator('#copyImageButton').inner_text().endswith('Copia immagine')
    assert page.locator('#fsActionLabel').inner_text() == '🗗 Finestra'
    page.evaluate("pywebview.api.set_language = async () => ({ok: false});")
    page.select_option('#languageSelect', 'en')
    page.wait_for_function("!document.getElementById('languageSelect').disabled")
    assert page.locator('#languageSelect').input_value() == 'it'
    assert 'Impossibile salvare' in page.locator('#statusText').inner_text()
    browser.close()
    print('PASS: Italian/English labels, errors, full screen and persistence failure; user content and selection preserved')
