# ShakeSearch

![ShakeSearch](logo-shakesearch.png)

ShakeSearch is an experimental open-source screen selection tool for Windows 10/11.
Shake the mouse or click **Select area**, circle what you want, then copy the selected image or search with Google Lens. No API key is required.

The project is independent and is not affiliated with Google. Its selection gesture
is inspired by [Circle to Search](https://blog.google/products/search/google-circle-to-search-android/).

## Install on Windows

**Download the portable app: [ShakeSearch.exe](https://github.com/vin10122/shakesearch-for-windows/releases/latest/download/ShakeSearch.exe).**

You need **Windows 10 or Windows 11 (64-bit)** and
[Microsoft Edge WebView2 Runtime](https://developer.microsoft.com/en-us/microsoft-edge/webview2/).
Python is included: you do not need to install Python, Git, or any Python packages.
No API key is needed.

1. Download **ShakeSearch.exe** using the link above, or open the [latest release](https://github.com/vin10122/shakesearch-for-windows/releases/latest) and select the EXE under **Assets**. The **Source code** archives are for developers; older ZIP assets belong to the previous folder-based build.
2. Move the EXE to a permanent location where you can write files, such as a folder in Documents.
3. Double-click **ShakeSearch.exe**.
4. Complete the first-launch configuration and click **Save / Salva**. The control window shows that the app is active.
5. Shake the mouse or click **Select area / Seleziona area** to begin.

The new portable build is a single EXE containing Python and its dependencies.
It extracts them to a temporary folder at startup, so launching the app or chat
can take longer than the older folder-based build. No `_internal` folder needs
to sit beside the new EXE. WebView2 must still be installed on Windows.
This version does not use an MSI or an installation wizard.
To add a Start shortcut, right-click the EXE and choose **Pin to
Start / Aggiungi a Start** (under **Show more options** if needed).

The build is unsigned. If SmartScreen shows **Windows protected your PC / PC protetto
da Windows**, check that you downloaded the EXE from this repository's release.
If you trust that build, choose **More info / Ulteriori informazioni**, then
**Run anyway / Esegui comunque**, when available.

### Update an existing copy

You can reuse the same EXE location for each release.

1. Choose **Quit / Esci** in ShakeSearch and close any remaining chat or Lens windows.
2. Download the new **ShakeSearch.exe** using the same download link above.
3. Move it to the location of your existing EXE, such as `C:\Apps\ShakeSearch\ShakeSearch.exe`.
4. Accept **Replace the file in the destination / Sostituisci il file nella destinazione**.
5. Start `ShakeSearch.exe` from the same folder as before.

When upgrading from the old ZIP build, replace the old EXE with the new single-file
EXE; the old `_internal` directory is no longer used by the new build.
If Windows says files are in use,
close the running app before retrying. If a pinned shortcut points to an older
app location, recreate it using the updated EXE.

There is no automatic updater. Preferences remain in
`%LOCALAPPDATA%\ShakeSearch\settings.json` and survive replacing the app files.

## First launch and settings

On first launch, choose Italian or English, mouse-shake activation, sensitivity,
and animation mode. Saving opens the control window; canceling exits without saving.
Existing users see this setup once if they have not completed it before.

The terminal stays open and the control window shows that ShakeSearch is active:

- **Select area / Seleziona area:** start a capture manually.
- **Settings / Configurazione:** change your saved preferences.
- **Quit / Esci:** stop the application. Closing the control window also stops it.

Alt+F7 enables or disables mouse-shake detection globally and saves the preference;
it does not start a capture. The control window minimizes before a capture so it
does not cover the selected area. Select area works even when mouse activation is off.

### Gaming mode and notifications

In the main window, turn off **Shake attivi / Shakes enabled** to disable shake
detection and enter **Gaming mode**, without using a keyboard shortcut. This avoids
unwanted captures and interference while playing with a high-DPI mouse. Manual
**Select area / Seleziona area** remains available. Turn the toggle on again to
re-enable shakes; the preference is saved for the next launch.

ShakeSearch sends a notification at startup and whenever shake detection changes,
including changes made in Settings. With shakes disabled, the notification says
**Gaming mode** and explains the high-DPI gaming purpose. With shakes enabled,
it confirms that shake activation is active. The control window and tray tooltip
also show the current state. Windows notification settings and Do Not Disturb
can hide notifications while gaming; the state remains visible in the control window.

Build **0.1.6-gaming.3** adds the main-window toggle. Windows also registers Alt+F7
natively with key repeat disabled, and a Qt timer samples mouse position only
while shakes are enabled. Gaming mode stops that timer entirely. No keyboard
shortcut starts screen capture. If Alt+F7 is unavailable, the app still starts:
use the visible toggle. The version appears in the control window title.
Close all older ShakeSearch instances before opening this EXE; a running older
version can keep its old keyboard behavior. The new version prevents duplicate
main instances of itself.

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

## Coming soon: copy text from images

**La copia del testo dalle immagini arriverà presto.**

Direct text selection and copying from screen captures is planned for a future
version. It is not available in this release: the OCR reader and its buttons have
been removed. Image capture, image copying, and Google Lens search remain available.

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

## Run from source (developers only)

Use Python 3.10+ x64 on Windows (the portable build uses Python 3.12):

```powershell
git clone https://github.com/vin10122/shakesearch-for-windows.git
cd shakesearch-for-windows
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe shakesearch.py
```

No `.env` file or Groq configuration is needed. The complete desktop workflow
requires Windows and WebView2.

## Build the portable EXE

On Windows with Python 3.12 x64:

```powershell
powershell -ExecutionPolicy Bypass -File packaging/build-windows.ps1
```

The script creates `.venv-build`, installs dependencies, runs tests, builds with
PyInstaller in onefile mode, and creates `dist/ShakeSearch.exe`. It then smoke-tests
bundled native dependencies and an independent child process before publishing.
Chat and Lens run as isolated roles of the same executable.

The **Windows portable build** GitHub Actions workflow can run manually. Pushing a
`v*` tag builds and publishes a release with the EXE after tests pass. Manual runs
provide a downloadable workflow artifact. To update an existing release without
moving its tag, run the workflow from the desired source ref and set `release_tag`
(for example `v0.1.6`). It uploads the EXE and updates the notes with the build's
source commit; the obsolete folder-based ZIP asset is removed after successful upload.
Pushing a `release/vX.Y.Z` branch also builds and updates that existing release.
Test screen capture, windows, clipboard,
and live Lens on a Windows desktop before distributing.

## Development checks

The Qt suite can run without a desktop:

```bash
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
```

It covers selection rendering, adjustment, multi-monitor lifecycle, gesture settings,
image clipboard behavior, worker IPC, and simulated Lens requests.

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
- **Lens cannot read results:** check the visible Google window, complete any consent/verification and try again.
- **Missing clipboard dependency when running from source:** reinstall `requirements.txt` to include `pywin32`.
- **Old icon after updating:** recreate the pinned shortcut so Windows can refresh it.

Application and worker logs are in `%TEMP%\shakesearch.log`:

```powershell
notepad "$env:TEMP\shakesearch.log"
```

## License and privacy

MIT License. Experimental software, provided as-is without warranty.
Rectangle detection runs on your PC. Lens searches send your selected
image and questions to Google; avoid sending sensitive information through that flow.
