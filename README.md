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

ShakeSearch currently provides AI-generated explanations and answers about the selected content. An experimental **Invia a Lens** option is available to try sending a selection to Google Lens in your browser. **Built-in image search is coming soon.**

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
- To try external image search, add an optional question under **Cerca con Google Lens** and click **Invia a Lens**.

## Files

| File | Description |
|------|-------------|
| shakesearch.py | Main application: input listeners, Qt screen capture, session management |
| overlay.py | Qt selection overlay and orange plasma animation |
| rectangle_snap.py | Local rectangle detection and selection alignment |
| drawer.py | Drawer window: image preview, AI chat |
| ocr_viewer.py | Image viewer with editable text recognition and clipboard support |
| image_clipboard.py | Windows clipboard image transfer (DIB and PNG) |
| lens_handoff.py | Experimental image handoff to Google Lens in the default browser |
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

## Google Lens handoff (experimental)

Enter an optional question in **Cerca con Google Lens**, then click **Invia a Lens**.
ShakeSearch opens the default browser and prepares an automatic image upload to
Google Lens. The question is included in the request. The capture stays on your
computer until the browser sends it directly to Google; no public image-hosting
service is used. A temporary, one-use local page handles the transfer and expires
after two minutes. No Groq key is needed for this option.

The upload target is `https://lens.google.com/v3/upload`, using the service host
from [Chromium's Lens configuration](https://github.com/chromium/chromium/blob/main/components/lens/lens_features.cc)
and the upload route in [Chromium's Google image-search template](https://github.com/chromium/chromium/blob/132.0.6834.83/components/search_engines/prepopulated_engines.json).
The separate `lens.google` site does not provide this upload route.

This integration uses Google's web upload form, not an official Lens API. The
browser's multipart image-and-question submission has been tested with an
intercepted destination. **Actual Google results and acceptance of the optional
question have not yet been verified**, because Google access is blocked in the
cloud development environment. Google may change the form, ignore the question,
or ask for consent or a verification step. If automatic file preparation is not
supported by the browser, the temporary page offers image download and a link to
Lens for manual upload. An opened browser tab does not confirm a successful search.

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

For the optional browser handoff check (all requests to the Lens upload endpoint
are intercepted, so this does not validate Google search results):

```bash
python -m pip install playwright
python -m playwright install chromium
python tests/check_lens_browser.py
```

## License

MIT License

## Disclaimer

This project is experimental. It uses third-party AI models through the Groq API. Screen captures are processed by an external service. Do not use this tool to capture sensitive or private information unless you understand and accept the privacy implications of sending images to an AI API.
