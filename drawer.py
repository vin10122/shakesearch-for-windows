from app_icon import icon_path, set_windows_identity
import sys
from app_runtime import child_command
import os
import json
import base64
import threading
import logging
import subprocess
import tempfile
from pathlib import Path
from image_clipboard import copy_image_to_clipboard
from lens_process import LensProcessClient
from window_shape import install_drawer_shape
from localization import get_language, set_language as save_language, catalog, tr

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="utf-8">
<style>
  :root {
    --bg-glass: rgba(34, 38, 45, 0.96);
    --border-glass: rgba(86, 106, 222, 0.38);
    --accent: #3447b8;
    --accent-light: #a8b6ff;
    --card-surface: rgba(43, 49, 59, 0.88);
    --card-hover: rgba(54, 64, 78, 0.96);
    --text-primary: #eef2f8;
    --text-secondary: #aebbcf;
    --font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
  }

  * {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
    user-select: none;
    accent-color: var(--accent);
  }

  html { background: transparent; }

  body {
    background: transparent;
    font-family: var(--font-family);
    color: var(--text-primary);
    overflow: hidden;
    height: 100vh;
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
    padding: 8px 12px;
    transition: padding 0.3s ease;
  }

  body.is-fullscreen {
    padding: 0;
  }

  .material-container {
    background: var(--bg-glass);
    backdrop-filter: blur(36px);
    -webkit-backdrop-filter: blur(36px);
    border: 1px solid var(--border-glass);
    border-radius: 32px;
    box-shadow: none;
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow: hidden;
    transition: border-radius 0.3s ease;
  }

  body.is-fullscreen .material-container {
    border-radius: 0;
    border: none;
  }

  .header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 20px 4px 20px;
    position: relative;
  }

  .handle-bar {
    position: absolute;
    top: 6px;
    left: 50%;
    transform: translateX(-50%);
    width: 40px;
    height: 4px;
    border-radius: 4px;
    background: rgba(255, 255, 255, 0.28);
  }

  .brand {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 0.3px;
    color: var(--accent-light);
  }

  .header-actions {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .btn-icon {
    background: rgba(255, 255, 255, 0.08);
    border: none;
    color: var(--text-secondary);
    width: 28px;
    height: 28px;
    border-radius: 50%;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    transition: all 0.2s;
  }
  .btn-icon:hover {
    background: rgba(255, 255, 255, 0.2);
    color: #fff;
    transform: scale(1.08);
  }

  .content-area {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow-y: auto;
    padding: 4px 18px 8px 18px;
    gap: 10px;
  }
  .content-area::-webkit-scrollbar {
    width: 5px;
  }
  .content-area::-webkit-scrollbar-thumb {
    background: rgba(255, 255, 255, 0.2);
    border-radius: 10px;
  }

  .preview-wrapper {
    background: var(--card-surface);
    border: 1px solid rgba(86, 106, 222, 0.16);
    border-radius: 20px;
    padding: 8px;
    display: flex;
    justify-content: center;
  }
  .preview-wrapper img {
    max-height: 180px;
    max-width: 100%;
    border-radius: 14px;
    object-fit: contain;
  }

  body.is-fullscreen .preview-wrapper img {
    max-height: 280px;
  }

  .actions-row {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    align-items: center;
  }
  .btn-action {
    background: var(--card-surface);
    border: 1px solid rgba(86, 106, 222, 0.18);
    color: var(--text-primary);
    padding: 7px 13px;
    border-radius: 18px;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    transition: all 0.2s;
  }
  .btn-action:hover {
    background: var(--card-hover);
    border-color: rgba(86, 106, 222, 0.45);
  }

  .status-text {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-secondary);
  }

  .lens-search {
    background: var(--card-surface);
    border: 1px solid var(--border-glass);
    border-radius: 16px;
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    font-size: 12px;
  }
  .lens-search textarea {
    width: 100%; min-height: 56px; max-height: 140px; resize: vertical;
    background: #1c2027; color: var(--text-primary);
    border: 1px solid var(--border-glass); border-radius: 8px;
    padding: 8px; font: inherit; user-select: text;
  }

  .chips-container {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .chip-card {
    background: var(--card-surface);
    border: 1px solid rgba(86, 106, 222, 0.14);
    padding: 10px 14px;
    border-radius: 18px;
    font-size: 12px;
    line-height: 1.4;
    color: var(--text-primary);
    transition: all 0.2s;
  }

  .chat-box {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .chat-msg-user {
    align-self: flex-end;
    background: var(--accent);
    color: #f5f7ff;
    font-weight: 600;
    padding: 8px 14px;
    border-radius: 18px 18px 4px 18px;
    font-size: 12px;
    max-width: 85%;
  }
  .chat-msg-ai {
    align-self: flex-start;
    background: var(--card-surface);
    border: 1px solid rgba(86, 106, 222, 0.14);
    color: var(--text-primary);
    padding: 9px 14px;
    border-radius: 18px 18px 18px 4px;
    font-size: 12px;
    line-height: 1.45;
    max-width: 90%;
  }

  /* Search bar */
  .footer {
    padding: 4px 14px 10px 14px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .search-pill {
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(86, 106, 222, 0.2);
    border-radius: 28px;
    display: flex;
    align-items: center;
    padding: 3px 5px 3px 16px;
  }
  .search-pill:focus-within {
    background: rgba(255, 255, 255, 0.12);
    border-color: rgba(86, 106, 222, 0.6);
    box-shadow: 0 0 14px rgba(86, 106, 222, 0.2);
  }
  .search-input {
    flex: 1;
    background: transparent;
    border: none;
    outline: none;
    color: #fff;
    font-size: 13px;
    font-family: inherit;
  }
  .search-input::placeholder {
    color: var(--text-secondary);
  }
  .btn-send {
    width: 34px;
    height: 34px;
    border-radius: 50%;
    border: none;
    background: var(--accent);
    color: #f5f7ff;
    font-size: 14px;
    font-weight: bold;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s;
  }
  .btn-send:hover {
    transform: scale(1.08);
  }
</style>
</head>
<body>

<div class="material-container">
  <div class="handle-bar"></div>
  <div class="header">
    <div class="brand">
      <span>✨</span> ShakeSearch
    </div>
    <div class="header-actions">
      <select id="languageSelect" aria-label="Language / Lingua" onchange="changeLanguage(this.value)" style="background:#2b313b;color:#eef2f8;border:1px solid #526c85;border-radius:8px;padding:5px">
        <option value="it">Italiano</option><option value="en">English</option>
      </select>
      <button class="btn-icon" id="btnToggleFs" title="Schermo intero (F11)" data-i18n-title="Schermo intero (F11)" onclick="toggleFs()">⛶</button>
      <button class="btn-icon" title="Chiudi (Esc)" data-i18n-title="Chiudi (Esc)" onclick="pywebview.api.close_window()">✕</button>
    </div>
  </div>

  <div class="content-area" id="contentArea">
    <div class="preview-wrapper">
      <img id="cropPreview" src="" alt="Selezione" data-i18n-alt="Selezione">
    </div>

    <div class="actions-row">
      <button class="btn-action" id="copyImageButton" onclick="copyImage()">
        📋 <span data-i18n="Copia immagine">Copia immagine</span>
      </button>
      <button class="btn-action" id="openTextImage" onclick="openImageForText()">
        <span data-i18n="Apri immagine per copiare testo">Apri immagine per copiare testo</span>
      </button>
      <button class="btn-action" onclick="toggleFs()">
        <span id="fsActionLabel">⛶ Schermo intero</span>
      </button>
      <span class="status-text" id="copyImageStatus" role="status" aria-live="polite"></span>
    </div>

    <div class="lens-search">
      <label for="lensQuestion" data-i18n="Cerca con Google Lens">Cerca con Google Lens</label>
      <textarea id="lensQuestion" maxlength="500" placeholder="Domanda facoltativa, per esempio: dove posso comprarlo?" data-i18n-placeholder="Domanda facoltativa, per esempio: dove posso comprarlo?"></textarea>
      <span data-i18n="Si apre la finestra Lens: completa lì eventuali richieste di consenso. Il ritaglio viene inviato a Google.">Si apre la finestra Lens: completa lì eventuali richieste di consenso. Il ritaglio viene inviato a Google.</span>
      <button class="btn-action" id="sendToLensButton" onclick="sendToLens()" data-i18n="Invia a Lens">Invia a Lens</button>
      <span id="lensStatus" role="status" aria-live="polite"></span>
    </div>

    <div class="status-text" id="statusText" data-i18n="Cerca questa immagine con Lens">Cerca questa immagine con Lens</div>
    <div class="chips-container" id="chipsContainer"></div>
    <div class="chat-box" id="chatBox"></div>
  </div>

  <div class="footer">
    <div class="search-pill">
      <input type="text" id="queryInput" class="search-input" placeholder="Chiedi qualcosa o cerchia…" data-i18n-placeholder="Chiedi qualcosa o cerchia…" onkeydown="if(event.key==='Enter') sendPrompt()">
      <button class="btn-send" onclick="sendPrompt()">➔</button>
    </div>
  </div>
</div>

<script>
  let translations = {};
  let uiLanguage = 'it';
  function t(text) { return translations[text] || text; }
  function applyLanguage(settings) {
    uiLanguage = settings.language;
    translations = settings.translations;
    document.documentElement.lang = uiLanguage;
    document.getElementById('languageSelect').value = uiLanguage;
    document.querySelectorAll('[data-i18n]').forEach(node => { node.textContent = t(node.dataset.i18n); });
    for (const attribute of ['placeholder', 'title', 'alt']) {
      document.querySelectorAll('[data-i18n-' + attribute + ']').forEach(node => {
        node.setAttribute(attribute, t(node.getAttribute('data-i18n-' + attribute)));
      });
    }
    document.getElementById('fsActionLabel').textContent = t(isFullscreen ? '🗗 Finestra' : '⛶ Schermo intero');
  }
  async function changeLanguage(language) {
    const selector = document.getElementById('languageSelect');
    selector.disabled = true;
    try {
      const settings = await pywebview.api.set_language(language);
      if (!settings.ok) throw new Error(settings.error);
      applyLanguage(settings);
    } catch (_) {
      selector.value = uiLanguage;
      setStatus(t('Impossibile salvare la lingua. Controlla i permessi della cartella delle preferenze.'));
    } finally { selector.disabled = false; }
  }
  let isFullscreen = false;

  let replyCounter = 0;

  function createChatTurn(text, source) {
    const chatBox = document.getElementById('chatBox');
    const user = document.createElement('div');
    user.className = 'chat-msg-user';
    user.textContent = text;
    chatBox.appendChild(user);
    const answer = document.createElement('div');
    answer.className = 'chat-msg-ai';
    answer.id = 'reply-' + (++replyCounter);
    answer.style.whiteSpace = 'pre-wrap';
    answer.style.userSelect = 'text';
    answer.textContent = source === 'lens' ? t('Ricerca su Google Lens…') : '…';
    chatBox.appendChild(answer);
    chatBox.scrollTop = chatBox.scrollHeight;
    return answer.id;
  }

  async function askLens(text) {
    const id = createChatTurn(text || t('Cerca questa immagine con Lens'), 'lens');
    const answer = document.getElementById(id);
    const started = Date.now();
    const bridgeCall = promise => new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('bridge timeout')), 12000);
      Promise.resolve(promise).then(value => { clearTimeout(timer); resolve(value); },
        error => { clearTimeout(timer); reject(error); });
    });
    try {
      const ticket = await bridgeCall(pywebview.api.send_to_lens(text));
      let result = ticket;
      if (ticket.ok) {
        while (true) {
          if (Date.now() - started > 350000) throw new Error('Lens timeout');
          const state = await bridgeCall(pywebview.api.poll_lens(ticket.job_id));
          document.getElementById('lensStatus').textContent = t(state.status || '');
          if (state.done) { result = state.result; break; }
          answer.textContent = (t(state.status || 'Attendo Google Lens…')) + '\n' + Math.floor((Date.now() - started) / 1000) + ' s';
          await new Promise(resolve => setTimeout(resolve, 250));
        }
      }
      if (!result.ok) {
        answer.textContent = t(result.error);
      } else {
        answer.textContent = 'Google Lens\n\n' + result.text;
        if (result.warning) answer.textContent += '\n\n' + t(result.warning);
        for (const link of result.links || []) {
          try {
            const url = new URL(link.url);
            if (!['http:', 'https:'].includes(url.protocol)) continue;
            const anchor = document.createElement('a');
            anchor.href = url.href;
            anchor.target = '_blank';
            anchor.rel = 'noopener noreferrer';
            anchor.style.color = '#a8b6ff';
            anchor.textContent = link.title;
            answer.appendChild(document.createElement('br'));
            answer.appendChild(anchor);
          } catch (_) {}
        }
      }
    } catch (error) {
      document.getElementById('lensStatus').textContent = t('Richiesta Lens interrotta.');
      updateAiResponse(t('Lens non ha completato la richiesta. Puoi riprovare; dettagli in %TEMP%\\shakesearch.log.'), id);
      // Do not wait for another bridge call if the bridge itself is stalled.
      try { Promise.resolve(pywebview.api.cancel_lens()).catch(() => {}); } catch (_) {}
    }
  }

  async function sendToLens() {
    const button = document.getElementById('sendToLensButton');
    button.disabled = true;
    try {
      await askLens(document.getElementById('lensQuestion').value);
    } finally {
      button.disabled = false;
    }
  }

  async function copyImage() {
    const button = document.getElementById('copyImageButton');
    const status = document.getElementById('copyImageStatus');
    button.disabled = true;
    status.textContent = t('Copia in corso…');
    try {
      const result = await pywebview.api.copy_image();
      status.textContent = result.ok ? t('Immagine copiata negli appunti.') : t(result.error);
    } catch (error) {
      status.textContent = t('Impossibile copiare l’immagine. Riprova.');
    } finally {
      button.disabled = false;
    }
  }

  async function openImageForText() {
    const button = document.getElementById('openTextImage');
    button.disabled = true;
    try {
      const result = await pywebview.api.open_image_for_text();
      if (!result.ok) setStatus(t(result.error));
    } catch (error) {
      setStatus(t('Impossibile aprire l’immagine. Riprova.'));
    } finally {
      button.disabled = false;
    }
  }

  function toggleFs() {
    isFullscreen = !isFullscreen;
    document.body.classList.toggle('is-fullscreen', isFullscreen);
    document.getElementById('btnToggleFs').innerText = isFullscreen ? '🗗' : '⛶';
    document.getElementById('fsActionLabel').innerText = t(isFullscreen ? '🗗 Finestra' : '⛶ Schermo intero');
    pywebview.api.toggle_fullscreen();
  }

  window.addEventListener('keydown', (e) => {
    if (e.key === 'F11') {
      e.preventDefault();
      toggleFs();
    } else if (e.key === 'Escape') {
      pywebview.api.close_window();
    }
  });

  async function sendPrompt() {
    const input = document.getElementById('queryInput');
    const text = input.value.trim();
    if (!text) return;
    input.value = '';
    await askLens(text);
  }

  function updateAiResponse(text, id) {
    const el = document.getElementById(id || 'ai-resp-current');
    if (el) {
      el.textContent = text;
      document.getElementById('chatBox').scrollTop = document.getElementById('chatBox').scrollHeight;
    }
  }

  function setPreview(uri) {
    document.getElementById('cropPreview').src = uri;
  }

  function setSuggestions(list) {
    document.getElementById('statusText').dataset.i18n = '✨ Suggerimenti correlati';
    document.getElementById('statusText').innerText = t('✨ Suggerimenti correlati');
    const c = document.getElementById('chipsContainer');
    c.innerHTML = '';
    list.forEach(txt => {
      const d = document.createElement('div');
      d.className = 'chip-card';
      d.innerText = txt;
      c.appendChild(d);
    });
  }

  function setStatus(text) {
    document.getElementById('statusText').removeAttribute('data-i18n');
    document.getElementById('statusText').innerText = t(text);
  }
</script>
</body>
</html>
"""

GLOBAL_WINDOW = None


class DrawerApi:
    def __init__(self, image_path, initial_geom):
        self.image_path = image_path
        self.language = get_language()
        try:
            self.image_bytes = Path(image_path).read_bytes()
        except OSError:
            self.image_bytes = None
        self.initial_geom = initial_geom
        self._fullscreen = False
        self._lens_lock = threading.Lock()
        self._lens_client = None
        self._lens_jobs = {}
        self._lens_closed = False

    def language_settings(self):
        return dict(ok=True, language=self.language, translations=catalog(self.language))

    def set_language(self, language):
        try:
            save_language(language)
            self.language = language
            return self.language_settings()
        except (OSError, ValueError):
            logging.getLogger('shakesearch').exception('Unable to save language')
            return dict(ok=False, error='Unable to save language')

    def close_window(self):
        global GLOBAL_WINDOW
        self._close_lens_session()
        if GLOBAL_WINDOW:
            GLOBAL_WINDOW.destroy()

    def toggle_fullscreen(self):
        global GLOBAL_WINDOW
        if GLOBAL_WINDOW:
            try:
                self._fullscreen = not self._fullscreen
                GLOBAL_WINDOW.toggle_fullscreen()
            except Exception as e:
                print(f"Errore toggle fullscreen: {e}")

    def copy_image(self):
        if not self.image_bytes:
            return dict(ok=False, error='Immagine non disponibile. Esegui una nuova cattura.')
        try:
            copy_image_to_clipboard(self.image_bytes)
            return dict(ok=True)
        except ImportError:
            logging.getLogger('shakesearch').exception('Windows clipboard dependency is missing')
            return dict(ok=False, error='Aggiorna le dipendenze: python -m pip install -r requirements.txt')
        except Exception:
            logging.getLogger('shakesearch').exception('Unable to copy image')
            return dict(ok=False, error='Impossibile copiare l’immagine. Riprova; dettagli in shakesearch.log.')

    def send_to_lens(self, question=''):
        if not self.image_bytes:
            return dict(ok=False, error='Immagine non disponibile. Esegui una nuova cattura.')
        try:
            with self._lens_lock:
                if self._lens_closed:
                    return dict(ok=False, error='La chat è stata chiusa.')
                if self._lens_client is None or self._lens_client.failed:
                    if self._lens_client is not None:
                        self._lens_client.close()
                    size = (int(GLOBAL_WINDOW.width), int(GLOBAL_WINDOW.height)) if GLOBAL_WINDOW else self.initial_geom[2:]
                    self._lens_client = LensProcessClient(self.image_bytes, window_size=size)
                token = self._lens_client.submit(question)
                self._lens_jobs[token] = self._lens_client
                for old in list(self._lens_jobs):
                    if len(self._lens_jobs) <= 64:
                        break
                    if self._lens_jobs[old].poll(old)['done']:
                        del self._lens_jobs[old]
            return dict(ok=True, job_id=token)
        except Exception as error:
            logging.getLogger('shakesearch').exception('Unable to queue Lens request')
            return dict(ok=False, error=str(error))

    def poll_lens(self, token):
        with self._lens_lock:
            client = self._lens_jobs.get(token)
        if client is None:
            return dict(done=True, result=dict(ok=False, error='Richiesta Lens annullata o sconosciuta.'))
        state = client.poll(token)
        return state

    def cancel_lens(self):
        with self._lens_lock:
            client = self._lens_client
            self._lens_client = None
        if client is not None:
            client.close()
        return dict(ok=True)

    def _close_lens_session(self):
        with self._lens_lock:
            self._lens_closed = True
            clients = set(self._lens_jobs.values())
            if self._lens_client is not None:
                clients.add(self._lens_client)
            self._lens_client = None
            self._lens_jobs.clear()
        for client in clients:
            client.close()

    def open_image_for_text(self):
        if not self.image_bytes:
            return dict(ok=False, error='Immagine non disponibile. Esegui una nuova cattura.')
        try:
            log_path = os.path.join(tempfile.gettempdir(), 'shakesearch.log')
            with open(log_path, 'a', encoding='utf-8') as log:
                process = subprocess.Popen(child_command('ocr_viewer', '--stdin'),
                                           stdin=subprocess.PIPE, stdout=log, stderr=log,
                                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            # Pass the immutable capture, never a path overwritten by later captures.
            with process.stdin:
                process.stdin.write(self.image_bytes)
            return dict(ok=True)
        except Exception:
            logging.getLogger('shakesearch').exception('Unable to open image text viewer')
            return dict(ok=False, error='Impossibile aprire l’immagine. Controlla shakesearch.log.')

def run_drawer_app(image_path, x, y, width, height):
    global GLOBAL_WINDOW
    import webview
    set_windows_identity()

    def on_loaded():
        if os.path.exists(image_path):
            with open(image_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            uri = f"data:image/png;base64,{b64}"
            GLOBAL_WINDOW.evaluate_js(f"setPreview('{uri}')")

    api = DrawerApi(image_path, (x, y, width, height))
    GLOBAL_WINDOW = webview.create_window(
        title="ShakeSearch",
        html=HTML_TEMPLATE.replace('</body>', '<script>applyLanguage(' + json.dumps(api.language_settings()).replace('<', '\\u003c') + ');</script></body>'),
        js_api=api,
        width=width,
        height=height,
        x=x,
        y=y,
        frameless=True,
        easy_drag=False,
        on_top=True,
        transparent=True,
        background_color='#22262d',
        shadow=False
    )
    GLOBAL_WINDOW.events.before_show += lambda: install_drawer_shape(GLOBAL_WINDOW, lambda: api._fullscreen)
    GLOBAL_WINDOW.events.loaded += on_loaded
    GLOBAL_WINDOW.events.closed += api._close_lens_session
    # A dedicated app profile retains Google's consent choice between captures.
    # Cookies remain in WebView storage and are never extracted into Python.
    profile = Path(os.getenv('LOCALAPPDATA') or tempfile.gettempdir()) / 'ShakeSearch' / 'WebViewProfile'
    profile.mkdir(parents=True, exist_ok=True)
    webview.start(private_mode=False, storage_path=str(profile), icon=str(icon_path()))


if __name__ == "__main__":
    if len(sys.argv) >= 6:
        img_p = sys.argv[1]
        x = int(sys.argv[2])
        y = int(sys.argv[3])
        w = int(sys.argv[4])
        h = int(sys.argv[5])
        run_drawer_app(img_p, x, y, w, h)
