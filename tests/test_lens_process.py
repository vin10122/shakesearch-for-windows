import base64
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock, Mock, patch

import drawer
from lens_process import LensProcessClient
from lens_worker import lock_profile


class LensProcessTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.release = Path(self.directory.name) / 'release'
        fixture = Path(__file__).parent / 'fixtures' / 'lens_ipc_worker.py'
        def factory(command, **options):
            return subprocess.Popen([sys.executable, str(fixture), str(self.release)], **options)
        self.client = LensProcessClient(b'capture', process_factory=factory)
        self.addCleanup(self.client.close)

    def wait(self, token, predicate=lambda value: value['done'], timeout=4):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = self.client.poll(token)
            if predicate(state):
                return state
            time.sleep(.01)
        self.fail('Lens test worker did not reach the expected state')

    def test_slow_lens_never_blocks_submit_poll_or_close(self):
        start = time.monotonic()
        token = self.client.submit('block')
        self.assertLess(time.monotonic() - start, .5)
        self.wait(token, lambda value: value['status'] == 'Attendo consenso…')
        self.assertFalse(self.client.poll(token)['done'])
        start = time.monotonic()
        self.client.close()
        self.assertLess(time.monotonic() - start, .5)
        self.assertFalse(self.client.poll(token)['result']['ok'])

    def test_results_and_followups_share_the_owned_worker(self):
        first = self.client.submit('first')
        second = self.client.submit('second')
        self.assertEqual(self.wait(first)['result']['text'], 'first:7')
        self.assertEqual(self.wait(second)['result']['text'], 'second:7')
        self.assertTrue(self.client.poll(first)['result']['ok'])

    def test_consent_wait_can_resume_without_restarting_chat(self):
        token = self.client.submit('block')
        self.wait(token, lambda value: value['status'] == 'Attendo consenso…')
        self.release.touch()
        self.assertTrue(self.wait(token)['result']['ok'])

    def test_unresponsive_worker_is_bounded_and_can_be_retried(self):
        with patch('lens_process.REQUEST_TIMEOUT', .15):
            token = self.client.submit('block')
            result = self.wait(token)['result']
        self.assertFalse(result['ok'])
        self.assertIn('tempo previsto', result['error'])
        self.assertTrue(self.client.failed)

    def test_native_profile_lock_fails_fast_and_is_released(self):
        profile = Path(self.directory.name)
        first = lock_profile(profile)
        try:
            with self.assertRaisesRegex(RuntimeError, 'altra chat'):
                lock_profile(profile)
        finally:
            first.close()
        lock_profile(profile).close()


class LensWorkerLifecycleTests(unittest.TestCase):
    def test_single_window_is_created_before_gui_loop_and_reused(self):
        import lens_worker
        webview = MagicMock()
        window = webview.create_window.return_value
        commands = '\n'.join(json.dumps(value) for value in (
            dict(type='init', image=base64.b64encode(b'capture').decode()),
            dict(type='query', id='first', question='What is this?'), dict(type='close'))) + '\n'
        output = io.StringIO()
        session = Mock()
        def build(image, window_factory, status):
            self.assertEqual(image, b'capture')
            def query(question):
                self.assertIs(window_factory('Lens', url='https://lens.google.com/search?p=test'), window)
                status('Reading')
                return dict(text='Result', links=[])
            session.query.side_effect = query
            return session
        def start(function, **options):
            webview.create_window.assert_called_once()
            self.assertFalse(options['private_mode'])
            self.assertTrue(options['storage_path'].endswith('LensProfile'))
            function()
        webview.start.side_effect = start
        with tempfile.TemporaryDirectory() as directory, \
             patch.dict(os.environ, {'LOCALAPPDATA': directory}), \
             patch.dict(sys.modules, {'webview': webview}), \
             patch.object(sys, 'stdin', io.StringIO(commands)), \
             patch('lens_session.LensSession', side_effect=build), \
             patch('logging.basicConfig'), contextlib.redirect_stdout(output):
            self.assertEqual(lens_worker.main(), 0)
        messages = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(messages[0]['type'], 'ready')
        self.assertEqual(next(m for m in messages if m['type'] == 'result')['result']['text'], 'Result')
        window.load_url.assert_called_once()
        session.close.assert_called_once()
