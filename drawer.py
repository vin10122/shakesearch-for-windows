import sys
import os
import json
import base64
import threading
import logging
import subprocess
import tempfile
from pathlib import Path
from dotenv import load_dotenv
from image_clipboard import copy_image_to_clipboard

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<style>
  :root {
    --bg-glass: rgba(26, 20, 16, 0.88);
    --border-glass: rgba(255, 140, 60, 0.38);
    --primary-orange: #ff944d;
    --primary-orange-light: #ffb077;
    --card-surface: rgba(44, 34, 28, 0.78);
    --card-hover: rgba(60, 46, 38, 0.92);
    --text-primary: #fdf8f5;
    --text-secondary: #bfaea5;
    --font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
  }

  * {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
    user-select: none;
  }

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
    box-shadow: 0 16px 48px rgba(0, 0, 0, 0.75),
                0 0 20px rgba(255, 140, 60, 0.16);
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
    color: var(--primary-orange);
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
    border: 1px solid rgba(255, 140, 60, 0.16);
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
    border: 1px solid rgba(255, 140, 60, 0.18);
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
    border-color: rgba(255, 140, 60, 0.45);
  }

  .status-text {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-secondary);
  }

  .chips-container {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .chip-card {
    background: var(--card-surface);
    border: 1px solid rgba(255, 140, 60, 0.14);
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
    background: var(--primary-orange);
    color: #1a0f05;
    font-weight: 600;
    padding: 8px 14px;
    border-radius: 18px 18px 4px 18px;
    font-size: 12px;
    max-width: 85%;
  }
  .chat-msg-ai {
    align-self: flex-start;
    background: var(--card-surface);
    border: 1px solid rgba(255, 140, 60, 0.14);
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
    border: 1px solid rgba(255, 140, 60, 0.2);
    border-radius: 28px;
    display: flex;
    align-items: center;
    padding: 3px 5px 3px 16px;
  }
  .search-pill:focus-within {
    background: rgba(255, 255, 255, 0.12);
    border-color: rgba(255, 140, 60, 0.6);
    box-shadow: 0 0 14px rgba(255, 140, 60, 0.2);
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
    background: var(--primary-orange);
    color: #1a0f05;
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
      <button class="btn-icon" id="btnToggleFs" title="Fullscreen (F11)" onclick="toggleFs()">⛶</button>
      <button class="btn-icon" title="Close (Esc)" onclick="pywebview.api.close_window()">✕</button>
    </div>
  </div>

  <div class="content-area" id="contentArea">
    <div class="preview-wrapper">
      <img id="cropPreview" src="" alt="Selection">
    </div>

    <div class="actions-row">
      <button class="btn-action" id="copyImageButton" onclick="copyImage()">
        📋 Copia immagine
      </button>
      <button class="btn-action" id="openTextImage" onclick="openImageForText()">
        Apri immagine per copiare testo
      </button>
      <button class="btn-action" onclick="toggleFs()">
        <span id="fsActionLabel">⛶ Fullscreen</span>
      </button>
      <span class="status-text" id="copyImageStatus" role="status" aria-live="polite"></span>
    </div>

    <div class="status-text" id="statusText">⏳ Analyzing selection...</div>
    <div class="chips-container" id="chipsContainer"></div>
    <div class="chat-box" id="chatBox"></div>
  </div>

  <div class="footer">
    <div class="search-pill">
      <input type="text" id="queryInput" class="search-input" placeholder="Ask anything or circle..." onkeydown="if(event.key==='Enter') sendPrompt()">
      <button class="btn-send" onclick="sendPrompt()">➔</button>
    </div>
  </div>
</div>

<script>
  let isFullscreen = false;

  async function copyImage() {
    const button = document.getElementById('copyImageButton');
    const status = document.getElementById('copyImageStatus');
    button.disabled = true;
    status.textContent = 'Copia in corso…';
    try {
      const result = await pywebview.api.copy_image();
      status.textContent = result.ok ? 'Immagine copiata negli appunti.' : result.error;
    } catch (error) {
      status.textContent = 'Impossibile copiare l’immagine. Riprova.';
    } finally {
      button.disabled = false;
    }
  }

  async function openImageForText() {
    const button = document.getElementById('openTextImage');
    button.disabled = true;
    try {
      const result = await pywebview.api.open_image_for_text();
      if (!result.ok) setStatus(result.error);
    } catch (error) {
      setStatus('Impossibile aprire l’immagine. Riprova.');
    } finally {
      button.disabled = false;
    }
  }

  function toggleFs() {
    isFullscreen = !isFullscreen;
    document.body.classList.toggle('is-fullscreen', isFullscreen);
    document.getElementById('btnToggleFs').innerText = isFullscreen ? '🗗' : '⛶';
    document.getElementById('fsActionLabel').innerText = isFullscreen ? '🗗 Window' : '⛶ Fullscreen';
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

  function sendPrompt() {
    const input = document.getElementById('queryInput');
    const text = input.value.trim();
    if (!text) return;
    input.value = '';

    const chatBox = document.getElementById('chatBox');
    const uMsg = document.createElement('div');
    uMsg.className = 'chat-msg-user';
    uMsg.innerText = text;
    chatBox.appendChild(uMsg);

    const aMsg = document.createElement('div');
    aMsg.className = 'chat-msg-ai';
    aMsg.id = 'ai-resp-current';
    aMsg.innerText = '...';
    chatBox.appendChild(aMsg);

    chatBox.scrollTop = chatBox.scrollHeight;
    pywebview.api.send_chat(text);
  }

  function updateAiResponse(text) {
    const el = document.getElementById('ai-resp-current');
    if (el) {
      el.innerText = text;
      el.removeAttribute('id');
      document.getElementById('chatBox').scrollTop = document.getElementById('chatBox').scrollHeight;
    }
  }

  function setPreview(uri) {
    document.getElementById('cropPreview').src = uri;
  }

  function setSuggestions(list) {
    document.getElementById('statusText').innerText = '✨ Related suggestions';
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
    document.getElementById('statusText').innerText = text;
  }
</script>
</body>
</html>
"""

GLOBAL_WINDOW = None


class DrawerApi:
    def __init__(self, image_path, initial_geom):
        self.image_path = image_path
        try:
            self.image_bytes = Path(image_path).read_bytes()
        except OSError:
            self.image_bytes = None
        self.initial_geom = initial_geom
        self.conversation_history = []
        self.is_first_prompt = True
        self.client = None
        if GROQ_API_KEY:
            try:
                from groq import Groq
                self.client = Groq(api_key=GROQ_API_KEY)
            except Exception as e:
                print(f"Errore Groq: {e}")

    def close_window(self):
        global GLOBAL_WINDOW
        if GLOBAL_WINDOW:
            GLOBAL_WINDOW.destroy()

    def toggle_fullscreen(self):
        global GLOBAL_WINDOW
        if GLOBAL_WINDOW:
            try:
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

    def send_chat(self, text):
        threading.Thread(target=self._ask_ai, args=(text,), daemon=True).start()

    def open_image_for_text(self):
        if not self.image_bytes:
            return dict(ok=False, error='Immagine non disponibile. Esegui una nuova cattura.')
        try:
            script = str(Path(__file__).with_name('ocr_viewer.py'))
            log_path = os.path.join(tempfile.gettempdir(), 'shakesearch.log')
            executable = Path(sys.executable)
            if executable.name.lower() == 'pythonw.exe' and executable.with_name('python.exe').is_file():
                executable = executable.with_name('python.exe')
            with open(log_path, 'a', encoding='utf-8') as log:
                process = subprocess.Popen([str(executable), script, '--stdin'],
                                           stdin=subprocess.PIPE, stdout=log, stderr=log,
                                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            # Pass the immutable capture, never a path overwritten by later captures.
            with process.stdin:
                process.stdin.write(self.image_bytes)
            return dict(ok=True)
        except Exception:
            logging.getLogger('shakesearch').exception('Unable to open image text viewer')
            return dict(ok=False, error='Impossibile aprire l’immagine. Controlla shakesearch.log.')

    def _ask_ai(self, text):
        global GLOBAL_WINDOW
        if not self.client or not GLOBAL_WINDOW:
            return

        content_payload = [{"type": "text", "text": text}]

        if self.is_first_prompt and os.path.exists(self.image_path):
            with open(self.image_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            content_payload.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"}
            })
            self.is_first_prompt = False

        # Costruisce la lista messaggi mantenendo il contesto precedente
        messages = [
            {"role": "system", "content": "You are the intelligent visual assistant of ShakeSearch. Provide accurate, concise, and well-formatted answers."}
        ]

        # Inserisce la cronologia precedente
        for turn in self.conversation_history:
            messages.append({"role": turn["role"], "content": turn["text"]})

        messages.append({"role": "user", "content": content_payload})

        try:
            completion = self.client.chat.completions.create(
                model=GROQ_MODEL,
                messages=messages,
                max_tokens=400,
                temperature=0.5,
            )
            answer = completion.choices[0].message.content.strip()

            # Salva cronologia per le domande successive
            self.conversation_history.append({"role": "user", "text": text})
            self.conversation_history.append({"role": "assistant", "text": answer})

            ans_clean = json.dumps(answer)
            GLOBAL_WINDOW.evaluate_js(f"updateAiResponse({ans_clean})")
        except Exception as e:
            GLOBAL_WINDOW.evaluate_js(f"updateAiResponse('Errore: {e}')")


def run_drawer_app(image_path, x, y, width, height):
    global GLOBAL_WINDOW
    import webview

    def on_loaded():
        if os.path.exists(image_path):
            with open(image_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            uri = f"data:image/png;base64,{b64}"
            GLOBAL_WINDOW.evaluate_js(f"setPreview('{uri}')")

        if api and api.client and os.path.exists(image_path):
            def fetch_sugg():
                try:
                    with open(image_path, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode()
                    prompt = (
                        "You are ShakeSearch visual assistant. "
                        "Look at the selected element. "
                        "Provide: 1) Name or identification in one line. "
                        "2) Up to 2 quick suggestions. "
                        "Answer directly without introductory text."
                    )
                    comp = api.client.chat.completions.create(
                        model=GROQ_MODEL,
                        messages=[
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": prompt},
                                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                                ],
                            }
                        ],
                        max_tokens=200,
                        temperature=0.4,
                    )
                    lines = [l.strip("-• * ") for l in comp.choices[0].message.content.strip().split("\n") if l.strip()][:3]
                    GLOBAL_WINDOW.evaluate_js(f"setSuggestions({json.dumps(lines)})")
                except Exception as e:
                    GLOBAL_WINDOW.evaluate_js(f"setStatus('Nota: {e}')")

            threading.Thread(target=fetch_sugg, daemon=True).start()

    api = DrawerApi(image_path, (x, y, width, height))
    GLOBAL_WINDOW = webview.create_window(
        title="ShakeSearch",
        html=HTML_TEMPLATE,
        js_api=api,
        width=width,
        height=height,
        x=x,
        y=y,
        frameless=True,
        easy_drag=False,
        on_top=True,
        transparent=True,
        background_color='#000000'
    )
    GLOBAL_WINDOW.events.loaded += on_loaded
    webview.start()


if __name__ == "__main__":
    if len(sys.argv) >= 6:
        img_p = sys.argv[1]
        x = int(sys.argv[2])
        y = int(sys.argv[3])
        w = int(sys.argv[4])
        h = int(sys.argv[5])
        run_drawer_app(img_p, x, y, w, h)
