"""Offline Windows OCR, isolated from the Qt UI and Google Lens."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from PIL import Image, ImageOps
from localization import get_language, tr


def extract_text(image_bytes):
    if sys.platform != 'win32':
        raise RuntimeError(tr('Il riconoscimento locale del testo richiede Windows 10 o 11.'))
    script = Path(__file__).resolve().parent / 'scripts' / 'windows-ocr.ps1'
    # Windows OCR accepts images up to 2600 pixels on either edge.
    with tempfile.TemporaryDirectory(prefix='shakesearch-ocr-') as directory:
        path = Path(directory) / 'capture.png'
        with Image.open(io.BytesIO(image_bytes)) as original:
            image = ImageOps.exif_transpose(original).convert('RGB')
            source_width, source_height = image.size
            image.thumbnail((2600, 2600), Image.Resampling.LANCZOS)
            scale_x, scale_y = source_width / image.width, source_height / image.height
            image.save(path)
        windows = Path(os.environ.get('SystemRoot', r'C:\Windows'))
        command = [str(windows / 'System32' / 'WindowsPowerShell' / 'v1.0' / 'powershell.exe'),
                   '-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                   '-File', str(script), '-ImagePath', str(path), '-Language', get_language()]
        try:
            result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8',
                                    errors='replace', timeout=45,
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(tr('La lettura locale ha impiegato troppo tempo. Prova con un ritaglio più piccolo.')) from error
        if result.returncode:
            if 'OCR_LANGUAGE_MISSING' in result.stderr:
                raise RuntimeError(tr('Installa una lingua per il riconoscimento testo nelle impostazioni Lingua di Windows.'))
            raise RuntimeError(tr('Riconoscimento Windows non disponibile. Controlla shakesearch.log.') + '\n' + result.stderr.strip())
        try:
            payload = json.loads(result.stdout.lstrip('\ufeff'))
            if not isinstance(payload.get('text'), str):
                raise ValueError('Invalid OCR output')
            text = payload['text']
            words = []
            cursor = 0
            for word in payload.get('words', []):
                content = word['text']
                start = text.find(content, cursor)
                if not content or start < 0:
                    continue
                cursor = start + len(content)
                words.append(dict(text=content, start=start, end=cursor,
                                  x=float(word['x']) * scale_x, y=float(word['y']) * scale_y,
                                  width=float(word['width']) * scale_x, height=float(word['height']) * scale_y))
            return dict(text=text, words=words, truncated=False)
        except (ValueError, AttributeError, KeyError, TypeError) as error:
            raise RuntimeError(tr('Windows non ha restituito un risultato OCR valido.')) from error
