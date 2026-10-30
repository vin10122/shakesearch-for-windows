"""Copy image pixels to the Windows clipboard as DIB and PNG."""
import io
import time

from PIL import Image


def copy_image_to_clipboard(image_bytes):
    # Import on use so non-Windows development and tests can load the application.
    import win32clipboard
    import win32gui

    with Image.open(io.BytesIO(image_bytes)) as source:
        with io.BytesIO() as bitmap:
            source.convert('RGB').save(bitmap, 'BMP')
            dib = bitmap.getvalue()[14:]  # CF_DIB excludes the BMP file header.
        with io.BytesIO() as png:
            source.save(png, 'PNG')
            png_bytes = png.getvalue()
    png_format = win32clipboard.RegisterClipboardFormat('PNG')
    # A real, non-null owner window is needed by EmptyClipboard/SetClipboardData.
    # The pywebview callback runs on a worker thread, so give it a hidden window.
    owner = win32gui.CreateWindowEx(0, 'STATIC', 'ShakeSearch clipboard', 0,
                                   0, 0, 0, 0, 0, 0, 0, None)
    if not owner:
        raise RuntimeError('Unable to create clipboard owner window')
    try:
        for attempt in range(10):
            try:
                win32clipboard.OpenClipboard(owner)
                break
            except Exception:
                if attempt == 9:
                    raise
                time.sleep(.025)
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32clipboard.CF_DIB, dib)
            win32clipboard.SetClipboardData(png_format, png_bytes)
        finally:
            win32clipboard.CloseClipboard()
    finally:
        win32gui.DestroyWindow(owner)
