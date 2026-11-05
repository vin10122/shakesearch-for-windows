# ShakeSearch

![ShakeSearch](logo-shakesearch.png)

ShakeSearch is an experimental open-source screen selection tool for Windows 10/11.
Shake the mouse or click **Select area**, circle what you want, then copy the image,
extract its text locally, or search with Google Lens. No API key is required.

The project is independent and is not affiliated with Google. Its selection gesture
is inspired by [Circle to Search](https://blog.google/products/search/google-circle-to-search-android/).

## Download and run

1. Download `ShakeSearch-windows-x64.zip` from the [latest release](https://github.com/vin10122/shakesearch-for-windows/releases/latest).
2. Extract the entire ZIP.
3. Open `ShakeSearch/ShakeSearch.exe`. Keep `_internal` beside the EXE.

The portable build includes Python. It requires Windows 10/11 x64 and Microsoft
Edge WebView2 Runtime for chat and Lens. Local text recognition uses Windows OCR
and an installed OCR language pack. It works offline and does not open Lens.

The build is unsigned, so Windows SmartScreen may show a warning. Only run a build
you trust. You can pin `ShakeSearch.exe` to Start; the EXE and application windows
use the project logo.

### Update an existing copy

Close ShakeSearch, its chat and Lens windows. Extract the new ZIP to the same
parent folder and replace the existing files. Keep the EXE and `_internal` together;
avoid nesting one `ShakeSearch` directory inside another. There is no automatic
updater. Preferences survive replacement because they are stored separately in
`%LOCALAPPDATA%\ShakeSearch\settings.json`.

## First launch and settings

On first launch, choose Italian or English, mouse-shake activation, sensitivity,
and animation mode. Saving opens the control window; canceling exits without saving.
Existing users see this setup once if they have not completed it before.

The terminal stays open and the control window shows that ShakeSearch is active:

- **Select area / Seleziona area:** start a capture manually.
- **Settings / Configurazione:** change your saved preferences.
- **Quit / Esci:** stop the application. Closing the control window also stops it.

There is no Alt+F7 shortcut. The control window minimizes before a capture so it
does not cover the selected area. Select area works even when mouse activation is off.

**Balanced** animation requests roughly 60 updates per second during the opening
effect, then 30 for the thin border. **Light** skips the opening effect and draws
only the border. These are timer targets, not measured frame rates. Mouse gesture
processing is capped to reduce work from high-polling-rate mice.

## Capture and adjust a selection

1. Shake the mouse or click **Select area**.
2. Draw around an area on any connected monitor.
3. Nearby rectangles can snap to their edges. Hold **Shift when releasing the mouse** to skip snapping.
4. Drag the selection corners or edges to adjust it.
5. Press **Enter** to confirm or **Esc** to cancel.

Screen captures retain their native resolution, including on mixed-DPI monitors.
Rectangle detection uses OpenCV locally in a background task. It does not upload
the screen to an AI service. Rotated shapes or faint edges may need manual adjustment.

The chat drawer shows your capture and search controls. **Copy image / Copia immagine**
copies the original image to the Windows clipboard. **F11** toggles the chat's
fullscreen view; **Esc** closes the chat.

## Copy text immediately after shaking the mouse

Shake the mouse (or use Select area). The frozen screen starts **local Windows OCR**
automatically, without opening chat, Lens, or an image viewer. The overlay shows
recognition progress and the running app version.

1. Wait for **Drag over text · Ctrl+C to copy**.
2. Drag directly over the letters on the frozen screen, or double-click a word.
3. Press **Ctrl+C** or click **Copy text** in the overlay toolbar.

**Select all** selects all recognized text on the current monitor. Selection and
clipboard copying work independently on each monitor, including mixed-DPI screens.
To draw an image area starting over text, turn off **Select text**, then draw and
press Enter as usual. Text selection alone never opens the chat or Lens. Press
Esc to clear a text selection, then Esc again to exit.

If Windows OCR is unavailable or no text is detected, the overlay shows that result;
it does not silently open Lens. An installed Windows OCR language is required.

## Copy text from a separate image window

Click **Open image to copy text / Apri immagine per copiare testo** in the drawer.
The image window automatically recognizes text using **Windows OCR**, locally.
No browser, Lens window, API key, or Internet connection is needed for recognition.

Drag directly over the letters **on the image** to highlight a selection, then
press **Ctrl+C** or **Copy text / Copia testo**. You can select part of a word,
multiple words, or several lines; double-click selects a word. **Ctrl+A** selects
all recognized text. Selection follows the image when you zoom or scroll.

The image is the main view. **Show separate text / Mostra testo separato** optionally
opens an editable text pane. Clicking Copy text without a selection copies all
recognized text. Use **Read text again / Rileggi testo** to retry recognition.
The selectable layer comes from local Windows OCR; unclear or unrecognized letters
cannot be selected accurately.

OCR first tries the chosen interface language, then the Windows profile's available
OCR languages. Install the appropriate language's **Optical character recognition**
feature in Windows Language settings if recognition is unavailable. Accuracy depends
on the image and installed languages. Large images are scaled to the Windows OCR
size limit; selecting a smaller region can improve small-text recognition.

The capture is stored temporarily on this PC for recognition and removed after
the request finishes. Text is not sent to Google by this feature.

## Google Lens search (experimental)

To search online, enter an optional question under **Search with Google Lens** and
click **Send to Lens / Invia a Lens**. Questions from the main chat input also use
Lens. The selected image and questions are sent to Google only through this flow.

The Lens window opens at the current chat size and stays visible. Complete any
Google consent, sign-in, or verification there. ShakeSearch does not choose consent
options or solve verification prompts. Available Lens text and source links appear
directly in chat, without an additional AI interpretation API. Follow-ups reuse
the same image session.

The Lens browser has no access to the application's JavaScript API. Its persistent
profile is stored at `%LOCALAPPDATA%\ShakeSearch\LensProfile`, separately from the
chat's `WebViewProfile`. Only one chat can use the Lens profile at a time. Closing
the chat stops its Lens worker. Cookies remain in WebView storage and are not
extracted into Python or copied from your default browser.

This integration uses Google web pages, not an official Lens API. Google may change
page structure, require verification, or return no readable results. The app reports
those failures rather than replacing them with invented answers. Automated tests
simulate Google responses; they do not establish that every live Google flow works.

## Run from source

Use Python 3.10+ x64 on Windows (the portable build uses Python 3.12):

```powershell
git clone https://github.com/vin10122/shakesearch-for-windows.git
cd shakesearch-for-windows
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe shakesearch.py
```

No `.env` file or Groq configuration is needed. Windows OCR and WebView2 are Windows
components; the complete desktop workflow requires Windows.

## Build the portable EXE

On Windows with Python 3.12 x64:

```powershell
powershell -ExecutionPolicy Bypass -File packaging/build-windows.ps1
```

The script creates `.venv-build`, installs dependencies, runs tests, builds with
PyInstaller, and creates `dist/ShakeSearch-windows-x64.zip`. Chat, Lens, and the text
viewer run as isolated roles of the same executable. The local OCR PowerShell helper
is included in `_internal/scripts` and uses the built-in Windows runtime.

Before producing the ZIP, the build also runs the **compiled EXE** against a known
text image, checks real Windows OCR word positions, selects a word on the capture
overlay, and verifies Ctrl+C clipboard output.

The **Windows portable build** GitHub Actions workflow can run manually. Pushing a
`v*` tag builds and publishes a release with the ZIP after tests pass. Manual runs
provide a downloadable workflow artifact. Test screen capture, windows, clipboard,
local text recognition, and live Lens on a Windows desktop before distributing.

## Development checks

The Qt suite can run without a desktop:

```bash
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
```

It covers selection rendering, adjustment, multi-monitor lifecycle, gesture settings,
clipboard behavior, worker IPC, simulated Lens requests, and local OCR handling.
The real Windows OCR test runs only on Windows; other platforms skip it.

Optional browser checks use simulated Google pages:

```bash
python -m pip install playwright
python -m playwright install chromium
python tests/check_lens_chat_browser.py
python tests/check_lens_reader_browser.py
python tests/check_lens_consent_browser.py
python tests/check_language_browser.py
```

## Troubleshooting

- **No capture after shaking:** enable mouse activation in Settings, raise sensitivity, or use Select area.
- **Text recognition unavailable:** install a Windows OCR language pack. The image window remains open so you can retry.
- **Lens cannot read results:** check the visible Google window, complete any consent/verification and try again.
- **Missing clipboard dependency when running from source:** reinstall `requirements.txt` to include `pywin32`.
- **Old icon after updating:** recreate the pinned shortcut so Windows can refresh it.

Application and worker logs are in `%TEMP%\shakesearch.log`:

```powershell
notepad "$env:TEMP\shakesearch.log"
```

## License and privacy

MIT License. Experimental software, provided as-is without warranty.
Local OCR and rectangle detection run on your PC. Lens searches send your selected
image and questions to Google; avoid sending sensitive information through that flow.
