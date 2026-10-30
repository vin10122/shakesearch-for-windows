# ShakeSearch

![ShakeSearch Preview](Logo%20ShakeSearch%20su%20sfondo%20pesca%20morbido.png)

ShakeSearch is an experimental open-source project for Windows that brings an AI-powered screen selection tool to your desktop. It is inspired by features like Google's Magic Pointer and Circle to Search, but it is an independent project with no affiliation with Google.

## Purpose

ShakeSearch lets you select any area of your screen by shaking your mouse or pressing a hotkey. Once you circle an area, a drawer window opens with:

- A preview of the captured image
- AI-generated suggestions about what is in the image
- A text input to ask custom questions about the selection
- An option to copy the captured image

It is inspired by Circle to Search on Android and Magic Pointer on Googlebook OS, but it is an independent project with no affiliation with Google.

It runs locally on Windows and uses Groq's API (Qwen 3.8 27B vision model) to understand what is on your screen.

**This is experimental software.** It is provided as-is without warranty. Use it at your own risk. The project is not affiliated with, endorsed by, or connected to Google LLC or any of its products.

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
- Press Enter to confirm the selection, or Esc to cancel and try again.
- A drawer window opens showing the captured image and AI suggestions.
- Type a question in the input box at the bottom to ask about the image.
- Click Copy to copy the image to the clipboard.

## Files

| File | Description |
|------|-------------|
| shakesearch.py | Main application: input listeners, Qt screen capture, session management |
| overlay.py | Qt selection overlay and orange plasma animation |
| drawer.py | Drawer window: image preview, AI chat |
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

## Troubleshooting

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

## License

MIT License

## Disclaimer

This project is experimental. It uses third-party AI models through the Groq API. Screen captures are processed by an external service. Do not use this tool to capture sensitive or private information unless you understand and accept the privacy implications of sending images to an AI API.
