"""Nonblocking JSON-lines client for an isolated Lens/WebView worker process."""
import base64
import json
import logging
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import uuid

logger = logging.getLogger('shakesearch')
REQUEST_TIMEOUT = 300


class LensProcessClient:
    def __init__(self, image_bytes, process_factory=None):
        self.image_bytes = image_bytes
        self.process_factory = process_factory or subprocess.Popen
        self._lock = threading.Lock()
        self._closed = threading.Event()
        self._ready = threading.Event()
        self._requests = queue.Queue()
        self._jobs = {}
        self._thread = None
        self._process = None
        self._reader_thread = None
        self._stopping = False
        self.failed = False

    def submit(self, question=''):
        if not isinstance(question, str) or len(question) > 500:
            raise ValueError('Scrivi una domanda di massimo 500 caratteri.')
        with self._lock:
            if self._closed.is_set() or self.failed:
                raise RuntimeError('La sessione Lens non è più disponibile. Riprova.')
            if sum(not job['done'] for job in self._jobs.values()) >= 4:
                raise RuntimeError('Attendi le risposte Lens già in corso prima di inviare altre domande.')
            for old in list(self._jobs):
                if len(self._jobs) < 64:
                    break
                if self._jobs[old]['done']:
                    del self._jobs[old]
            token = uuid.uuid4().hex
            self._jobs[token] = dict(done=False, status='Richiesta Lens in coda…', result=None,
                                     event=threading.Event())
            self._requests.put((token, question))
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, daemon=True)
                self._thread.start()
        return token

    def poll(self, token):
        with self._lock:
            job = self._jobs.get(token)
            if job is None:
                return dict(done=True, result=dict(ok=False, error='Richiesta Lens sconosciuta.'))
            return dict(done=job['done'], status=job['status'], result=job['result'])

    def _finish(self, token, result):
        with self._lock:
            job = self._jobs.get(token)
            if job is not None and not job['done']:
                job.update(done=True, result=result, status=(
                    'Risultati Lens letti. Puoi fare un’altra domanda.' if result.get('ok') else 'Ricerca Lens non completata.'))
                job['event'].set()

    def _reader(self, process):
        try:
            for line in process.stdout:
                try:
                    message = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(message, dict):
                    continue
                token = message.get('id')
                if message.get('type') == 'ready':
                    self._ready.set()
                elif message.get('type') == 'result':
                    self._finish(token, message['result'])
                elif message.get('type') == 'status':
                    with self._lock:
                        if token in self._jobs:
                            self._jobs[token]['status'] = str(message.get('text', ''))
                elif message.get('type') == 'fatal':
                    self.failed = True
                    self._fail_all(str(message.get('error', 'Il processo Lens si è arrestato.')))
                    self._ready.set()
        finally:
            process.stdout.close()
            if not self._closed.is_set():
                self.failed = True
                self._fail_all('Il processo Lens si è chiuso. La chat è ancora disponibile: puoi riprovare.')
                self._ready.set()

    def _fail_all(self, error):
        with self._lock:
            tokens = list(self._jobs)
        for token in tokens:
            self._finish(token, dict(ok=False, error=error))

    def _run(self):
        try:
            executable = Path(sys.executable)
            if executable.name.lower() == 'pythonw.exe' and executable.with_name('python.exe').is_file():
                executable = executable.with_name('python.exe')
            script = Path(__file__).with_name('lens_worker.py')
            with open(Path(tempfile.gettempdir()) / 'shakesearch.log', 'a', encoding='utf-8') as log:
                process = self.process_factory([str(executable), str(script)], stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE, stderr=log, text=True, encoding='utf-8', bufsize=1,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            self._process = process
            if self._closed.is_set():
                self._stop_process()
                return
            self._reader_thread = threading.Thread(target=self._reader, args=(process,), daemon=True)
            self._reader_thread.start()
            if not self._ready.wait(20) or self.failed:
                raise RuntimeError('Lens GUI did not initialize')
            if self._closed.is_set():
                return
            process.stdin.write(json.dumps(dict(type='init', image=base64.b64encode(self.image_bytes).decode('ascii'))) + '\n')
            process.stdin.flush()
            while not self._closed.is_set() and not self.failed:
                try:
                    token, question = self._requests.get(timeout=.1)
                except queue.Empty:
                    continue
                process.stdin.write(json.dumps(dict(type='query', id=token, question=question)) + '\n')
                process.stdin.flush()
                with self._lock:
                    done = self._jobs[token]['event']
                # This wait is in the owned worker thread, never in the GUI or JS bridge.
                if not done.wait(REQUEST_TIMEOUT):
                    self.failed = True
                    self._fail_all('Lens non ha risposto entro il tempo previsto. Il processo è stato fermato; puoi riprovare.')
                    self._stop_process()
            if self.failed and process.poll() is None:
                self._stop_process()
        except Exception:
            self.failed = True
            logger.exception('Lens worker failed')
            self._fail_all('Impossibile avviare Lens. Controlla shakesearch.log e riprova.')
            self._stop_process()

    def _stop_process(self):
        with self._lock:
            if self._stopping or self._process is None:
                return
            self._stopping = True
            process = self._process
        def terminate():
            try:
                if process.poll() is None:
                    process.kill()
            except OSError:
                pass
        def cleanup():
            deadline = threading.Timer(2, terminate)
            deadline.daemon = True
            deadline.start()
            try:
                process.stdin.write(json.dumps(dict(type='close')) + '\n')
                process.stdin.flush()
                process.wait(timeout=2)
            except (OSError, ValueError, subprocess.TimeoutExpired):
                terminate()
            finally:
                deadline.cancel()
                try:
                    process.stdin.close()
                    process.wait(timeout=.5)
                except (OSError, ValueError, subprocess.TimeoutExpired):
                    terminate()
                if self._reader_thread is None:
                    process.stdout.close()
        # Keep cleanup alive briefly after the chat closes, so an unresponsive
        # owned child cannot be orphaned when the interpreter exits.
        threading.Thread(target=cleanup, daemon=False).start()

    def close(self):
        self._closed.set()
        self._ready.set()
        self._fail_all('Richiesta Lens annullata.')
        self._stop_process()
