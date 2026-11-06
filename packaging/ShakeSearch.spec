# Build on Windows x64: python -m PyInstaller --noconfirm packaging/ShakeSearch.spec
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

root = Path(SPECPATH).parent
webview_data, webview_binaries, webview_hidden = collect_all('webview')
a = Analysis(
    [str(root / 'portable_main.py')],
    pathex=[str(root)],
    binaries=webview_binaries,
    datas=webview_data + [(str(root / 'logo-shakesearch.png'), '.'), (str(root / 'assets' / 'shakesearch.ico'), 'assets'),
        (str(root / 'LICENSE'), '.'), (str(root / 'packaging' / 'PORTABLE.txt'), '.')],
    hiddenimports=webview_hidden + ['webview.platforms.edgechromium',
        'win32clipboard',
        'win32con', 'clr'],
    excludes=['tkinter', 'PyQt5', 'PyQt6', 'PySide2'],
    noarchive=False,
)
pyz = PYZ(a.pure)
# Retain redirected standard streams for the Lens JSON-lines protocol.
# Keep the main console visible for status and errors; children use CREATE_NO_WINDOW.
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='ShakeSearch', icon=str(root / 'assets' / 'shakesearch.ico'),
          debug=False, strip=False, upx=False, console=True)
