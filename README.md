# ShakeSearch

![ShakeSearch Preview](Logo%20ShakeSearch%20su%20sfondo%20pesca%20morbido.png)

ShakeSearch is an experimental open-source project for Windows that brings an AI-powered screen selection tool to your desktop. It is inspired by features like Google's Magic Pointer and Circle to Search, but it is an independent project with no affiliation with Google.

## Purpose

ShakeSearch lets you select any area of your screen by shaking your mouse or pressing a hotkey. Once you circle an area, a drawer window opens with:

- A preview of the captured image
- AI-generated suggestions about what is in the image
- A text input to ask custom questions about the selection
- An option to copy the captured image

Circle to Search is Google's visual search feature for supported Android phones. It lets you circle, highlight, scribble over or tap something on the screen to search for it with Google without leaving the app you are using.

Google explains the original Android feature in its [introduction to Circle to Search](https://blog.google/products/search/google-circle-to-search-android/). ShakeSearch takes inspiration from its screen selection gesture and is developed independently of Google.

ShakeSearch currently provides AI-generated explanations and answers about the selected content. An experimental **Invia a Lens** option reads Google Lens results into the ShakeSearch chat through an internal web session. **Built-in image search is coming soon.**

It runs locally on Windows and uses Groq's API (Qwen 3.8 27B vision model) to understand what is on your screen.

**This is experimental software.** It is provided as-is without warranty. Use it at your own risk. The project is not affiliated with, endorsed by, or connected to Google LLC or any of its products.

## What you can use it for

Use ShakeSearch when you want help with something you see on your screen. Circle a picture to ask what it shows, select an error message to ask for help, or extract text from a screenshot instead of typing it again. You can also copy a selected part of the screen to paste into another app. If your selection is not quite right, adjust its edges before confirming. You do not need to draw a perfect shape.

## Requirements

- Windows 10 or Windows 11
- Python 3.10 or newer (64-bit)
- Microsoft Edge WebView2 Runtime (required by the chat window on Windows)
- A free Groq API key from https://console.groq.com/

## Installation

1. Download or clone this repository:

   git clone https://github.com/vin10122/shakesearch-windows.git
   cd shakesearch-windows

2. Install the Python dependencies:

   pip install -r requirements.txt

3. Create a file named `.env` in the project folder with your Groq API key:

   GROQ_API_KEY=your_api_key_here
   GROQ_MODEL=qwen/qwen3.8-27b

4. Run the application:

   python shakesearch.py

## How to use

- Shake your mouse quickly or press Alt + F7 to activate the screen capture.
- A darkened overlay appears over your screen.
- Click and drag to draw a circle around the area you want to select.
- Nearby visible rectangles are detected locally and the selection snaps to their edges.
- Hold Shift when releasing the mouse to keep a free selection.
- Before confirming, drag the orange handles at the corners or along any edge to refine the rectangle.
- Press Enter to confirm the selection, or Esc to cancel and try again.
- A drawer window opens showing the captured image and AI suggestions.
- Type a question in the input box at the bottom to ask about the image.
- Click **Copia immagine** to copy the original capture to the Windows clipboard. A message confirms the copy or explains an error.
- Click **Apri immagine per copiare testo** to open the image alongside its recognized text.
- To query Lens in the chat, add an optional question under **Cerca con Google Lens** and click **Invia a Lens**. Leave **Usa Lens per le prossime domande** checked to send follow-up questions about the same image.

## Files

| File | Description |
|------|-------------|
| shakesearch.py | Main application: input listeners, Qt screen capture, session management |
| overlay.py | Qt selection overlay and orange plasma animation |
| rectangle_snap.py | Local rectangle detection and selection alignment |
| drawer.py | Drawer window: image preview, AI chat |
| ocr_viewer.py | Image viewer with editable text recognition and clipboard support |
| image_clipboard.py | Windows clipboard image transfer (DIB and PNG) |
| lens_upload.py | Direct Python multipart upload and Lens response validation |
| lens_handoff.py | Standalone browser-handoff helper |
| lens_session.py | Isolated internal Lens session and reading of visible results |
| lens_process.py | Nonblocking Lens request queue and child-process management |
| lens_worker.py | Dedicated Lens WebView process and persistent consent profile |
| lens_answer.py | API interpretation of real Lens results with source links |
| browser_window.py | Standalone browser-launch helper |
| requirements.txt | Python dependencies |
| .env | Your API keys (not tracked by git) |
| .gitignore | Files excluded from version control |

## Capture animation

The capture overlay uses Qt (PySide6). On each monitor, an orange plasma wave
moves from the edges to the center, returns to the edges, then fades to a thin
orange perimeter line with a continuously moving highlight. The sequence takes
2.8 seconds and requests a frame every 7 ms (about 144 updates per second, subject
to display refresh rate and rendering performance). Selection stays available
throughout. After the opening sequence, only the border area is repainted. Screenshots remain at their native resolution, including on mixed-DPI
monitor setups.

After updating an existing installation, install the new Qt dependency:

```powershell
python -m pip install -r requirements.txt
python shakesearch.py
```

## Rectangle snapping

Draw roughly around a card, window, image or other rectangle. ShakeSearch checks
nearby screen edges and aligns the selection when it finds a close match, including
rectangles with rounded corners. If no reliable match is found, your original
selection is kept. Hold **Shift when releasing the mouse** to skip alignment.

Before pressing **Enter**, drag any orange corner handle or edge to adjust the
selection. Manual adjustments are kept without snapping again. The selection
stays within the screen and cannot shrink below 25 logical pixels per side.
Nothing is sent to the chat until you confirm with Enter; Esc clears the selection.

Detection uses OpenCV locally in a background thread; screenshots are not sent to
an AI service for alignment. Rotated shapes and rectangles without clear visible
edges may require a free selection. Install updated requirements after upgrading.

## Copy text from an image

In the chat drawer, choose **Apri immagine per copiare testo**. A separate window
shows the captured image with zoom controls and extracts its text using the
configured Groq vision model. This requires your existing `GROQ_API_KEY` and an
Internet connection; recognition is performed by Groq, not locally.

The extracted text is selectable and editable. Use **Copia testo** to copy the
selected portion, or all text when nothing is selected. **Ctrl+C** copies a text
selection as usual. Use **Rileggi testo** to retry recognition. Empty results,
request failures and truncated text are shown in the window.

## Google Lens in the chat (experimental)

Enter an optional question in **Cerca con Google Lens** and click **Invia a Lens**.
ShakeSearch keeps its chat open and sends the captured PNG directly from Python
to Google Lens using an HTTP multipart request. It waits for a response containing
an image-search session, then reads that result in a hidden, isolated renderer
and sends its text and source links to the configured Groq API for a concise
answer to your question. Original source links remain visible in the chat.
The upload does
not use a browser file input or a local upload page.
It does not open the default browser, minimize the chat or close the panel.

Lens runs in a separate process with one internal window created at startup.
The chat submits requests and checks their progress without waiting inside its
interface callbacks, so a stalled Google page cannot freeze the chat's interface.
Requests stop after five minutes without a response. Closing the chat cancels
pending requests and stops its Lens process, including an unresponsive reader.

With **Usa Lens per le prossime domande** checked, messages in the main input use
the same image-search session. Uncheck it to return to Groq's AI explanations.
The chat labels replies interpreted by AI using Lens results. The API receives
the question, up to 6,000 characters of Lens text, up to eight source links and
recent Lens conversation context. It is instructed to treat page content as
untrusted data and explain uncertainty. If the API is unavailable or no
`GROQ_API_KEY` is configured, the original Lens results appear with an explanation.
The API call has a 25-second timeout and the chat stops waiting for interpretation
after 35 seconds. If Lens returns no results, the chat reports the failure
instead of substituting a generated answer.
Menus, headers, footers and generic page links are excluded. The reader accepts
structured result cards, visual matches and recognized answer blocks, rather than
the full page text. If Google opens its homepage instead of search results, the
chat reports that problem without opening another window. If no
readable results are found, the chat reports an error. No additional API
key or public image-hosting service is used; the image is sent directly to Google.

The hidden Google reader has no access to ShakeSearch's application API. It stays
hidden during normal searches. If Google requires consent, access or a human
verification, ShakeSearch shows that same internal window once and waits for your
choice. It never chooses a consent option or solves a verification for you.
Consent dialogs embedded in the Google results page are detected as well. The
window stays visible through loading redirects until a readable page arrives.
If the hidden reader cannot identify results before its initial timeout, it shows
the same window once and keeps reading for up to three more minutes, allowing
you to see and complete an unrecognized Google prompt.

After you finish, ShakeSearch keeps the authorized WebView session, hides the
window and automatically submits the selected image from Google's own page if
needed. The response is read back into the chat from that same session. It does
not switch back to a separate HTTP cookie jar after consent. Closing the consent
window cancels the pending request; closing the chat also closes the internal reader.

Google's consent choice is retained in ShakeSearch's dedicated WebView profile
under `%LOCALAPPDATA%\ShakeSearch\LensProfile` on Windows, separately from the
chat's `WebViewProfile`. Only one chat can use the Lens profile at a time; another
chat reports that Lens is already active instead of opening a competing reader.
Cookies are managed
by the WebView and are not extracted into Python or copied from your default browser.

This uses Google's web upload endpoint and result pages, not an official Lens API. Page structure,
image-session lifetime and support for follow-up questions can change. Automated
checks inspect the real multipart encoding sent by the HTTP client and cover
rejected uploads, DOM extraction, session reuse and chat rendering with simulated
Google responses, plus cancellation and timeouts with a deliberately stalled
worker process. **The live Google flow still needs verification on
Windows**, because Google access is blocked in the cloud development environment.

The upload host is `lens.google.com`, as configured in
[Chromium's Lens configuration](https://github.com/chromium/chromium/blob/main/components/lens/lens_features.cc).

## Troubleshooting

If image copying reports a missing dependency, run `python -m pip install -r requirements.txt` to install `pywin32` on Windows.

On Windows, application and chat-process logs are written to
`%TEMP%\shakesearch.log`. Open them with:

```powershell
notepad "$env:TEMP\shakesearch.log"
```

## Development checks

Run the Qt rendering, input, multi-monitor lifecycle and crop tests without a desktop:

```bash
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
```

For the optional internal Lens chat check (Google pages are simulated, so this
does not validate live Google results):

```bash
python -m pip install playwright
python -m playwright install chromium
python tests/check_lens_chat_browser.py
python tests/check_lens_reader_browser.py
python tests/check_lens_consent_browser.py
```

## License

MIT License

## Disclaimer

This project is experimental. It uses third-party AI models through the Groq API. Screen captures are processed by an external service. Do not use this tool to capture sensitive or private information unless you understand and accept the privacy implications of sending images to an AI API.
