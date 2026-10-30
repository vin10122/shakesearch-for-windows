"""One WebView GUI process dedicated to Lens; stdout is a JSON-lines protocol."""
import base64
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
import threading


def lock_profile(profile):
    """Fail fast instead of starting two native GUI processes on a locked profile."""
    stream = open(profile / 'shakesearch-worker.lock', 'a+b')
    if stream.tell() == 0:
        stream.write(b'0')
        stream.flush()
    stream.seek(0)
    try:
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        stream.close()
        raise RuntimeError('Lens è già attivo in un’altra chat. Chiudi quella chat e riprova.')
    return stream


def main():
    import webview
    from lens_session import LensSession

    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    profile = Path(os.getenv('LOCALAPPDATA') or tempfile.gettempdir()) / 'ShakeSearch' / 'LensProfile'
    profile.mkdir(parents=True, exist_ok=True)
    try:
        profile_lock = lock_profile(profile)
    except RuntimeError as error:
        print(json.dumps(dict(type='fatal', error=str(error))), flush=True)
        return 1
    stop = threading.Event()
    write_lock = threading.Lock()
    window = webview.create_window('ShakeSearch · Consenso Google Lens', url='about:blank',
                                   hidden=True, js_api=None, width=900, height=740, on_top=False)
    window.events.closed += stop.set
    current = {'id': None}

    def emit(message):
        with write_lock:
            sys.stdout.write(json.dumps(message, ensure_ascii=True) + '\n')
            sys.stdout.flush()

    def status(text):
        emit(dict(type='status', id=current['id'], text=text))

    def navigate_existing(title, **options):
        # The sole WebView already exists and its event loop is running. Never
        # create a second form from a JavaScript callback or navigation event.
        window.load_url(options['url'])
        return window

    def requests():
        session = None
        try:
            emit(dict(type='ready'))
            first = json.loads(sys.stdin.readline())
            if first.get('type') != 'init':
                raise ValueError('Missing Lens image initialization')
            image = base64.b64decode(first['image'], validate=True)
            session = LensSession(image, window_factory=navigate_existing, status=status)
            for line in sys.stdin:
                message = json.loads(line)
                if stop.is_set():
                    break
                if message.get('type') == 'close':
                    break
                if message.get('type') != 'query':
                    continue
                current['id'] = message['id']
                try:
                    result = dict(ok=True, **session.query(message.get('question', '')))
                except Exception as error:
                    logging.getLogger('shakesearch').exception('Lens query failed')
                    result = dict(ok=False, error=str(error))
                emit(dict(type='result', id=current['id'], result=result))
                if stop.is_set():
                    break
        except Exception as error:
            logging.getLogger('shakesearch').exception('Lens worker protocol failed')
            emit(dict(type='fatal', error=str(error)))
        finally:
            if session is not None:
                session.close()
            if not stop.is_set():
                window.destroy()

    # The consent profile is deliberately separate from the chat's profile.
    try:
        webview.start(requests, private_mode=False, storage_path=str(profile))
    finally:
        profile_lock.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
