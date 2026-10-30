import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import drawer
from lens_answer import answer_from_lens


RESULT = dict(ok=True, text='Lens identifies a mechanical keyboard.',
              links=[dict(title='Source', url='https://example.org/keyboard')])


class LensAnswerTests(unittest.TestCase):
    def client(self, answer='È una tastiera meccanica.'):
        client = Mock()
        client.with_options.return_value.chat.completions.create.return_value.choices = [
            Mock(message=Mock(content=answer))]
        return client

    def interpret(self, client, result=RESULT):
        return answer_from_lens(client, 'Cos’è?', result, model='configured-model', system_prompt='Be concise.')

    def test_actual_results_question_and_sources_are_sent_to_api(self):
        client = self.client()
        answer = self.interpret(client)
        self.assertTrue(answer['interpreted'])
        self.assertEqual(answer['links'], RESULT['links'])
        client.with_options.assert_called_once_with(timeout=25, max_retries=0)
        arguments = client.with_options.return_value.chat.completions.create.call_args.kwargs
        self.assertEqual(arguments['model'], 'configured-model')
        self.assertEqual(arguments['max_tokens'], 400)
        payload = json.loads(arguments['messages'][-1]['content'])
        self.assertEqual(payload['question'], 'Cos’è?')
        self.assertEqual(payload['lens_results']['text'], RESULT['text'])
        self.assertIn('untrusted source data', arguments['messages'][0]['content'])

    def test_missing_key_preserves_raw_results_and_explains_why(self):
        result = self.interpret(None)
        self.assertFalse(result['interpreted'])
        self.assertEqual(result['text'], RESULT['text'])
        self.assertIn('GROQ_API_KEY', result['warning'])

    def test_api_failure_or_empty_reply_keeps_original_sources(self):
        for text in ('', None):
            with self.subTest(text=text):
                answer = self.interpret(self.client(text))
                self.assertEqual(answer['text'], RESULT['text'])
                self.assertFalse(answer['interpreted'])
                self.assertIn('warning', answer)
        client = self.client()
        client.with_options.return_value.chat.completions.create.side_effect = TimeoutError()
        self.assertEqual(self.interpret(client)['links'], RESULT['links'])


class LensPipelineTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / 'capture.png'
        path.write_bytes(b'capture')
        with patch.object(drawer, 'GROQ_API_KEY', None):
            self.api = drawer.DrawerApi(str(path), (0, 0, 560, 680))
        self.addCleanup(self.api._close_lens_session)
        self.worker = Mock(failed=False)
        self.worker.submit.return_value = 'job'
        self.worker.poll.return_value = dict(done=True, result=RESULT)
        with patch.object(drawer, 'LensProcessClient', return_value=self.worker):
            self.api.send_to_lens('Cos’è?')

    def wait_result(self):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            state = self.api.poll_lens('job')
            if state['done']:
                return state['result']
            time.sleep(.005)
        self.fail('Interpretation did not complete')

    def test_slow_api_runs_once_without_blocking_poll_or_chat(self):
        release = threading.Event()
        entered = threading.Event()
        self.addCleanup(release.set)
        def interpret(*args, **kwargs):
            entered.set()
            release.wait(3)
            return dict(RESULT, text='API interpretation', interpreted=True)
        with patch.object(drawer, 'answer_from_lens', side_effect=interpret) as api:
            start = time.monotonic()
            self.assertFalse(self.api.poll_lens('job')['done'])
            self.assertLess(time.monotonic() - start, .5)
            self.assertTrue(entered.wait(1))
            for _ in range(3):
                self.assertIn('AI', self.api.poll_lens('job')['status'])
            release.set()
            self.assertEqual(self.wait_result()['text'], 'API interpretation')
            self.api.poll_lens('job')
            api.assert_called_once()
        self.assertEqual(self.api._lens_history[-1]['content'], 'API interpretation')

    def test_api_deadline_returns_raw_results_without_overwriting_them_later(self):
        release = threading.Event()
        self.addCleanup(release.set)
        def interpret(*args, **kwargs):
            release.wait(3)
            return dict(RESULT, text='Late response', interpreted=True)
        with patch.object(drawer, 'answer_from_lens', side_effect=interpret):
            self.api.poll_lens('job')
            with self.api._lens_lock:
                self.api._lens_answers['job']['started'] -= 36
            result = self.wait_result()
            self.assertFalse(result['interpreted'])
            self.assertEqual(result['text'], RESULT['text'])
            release.set()

    def test_cancel_stops_worker_and_does_not_interpret_a_failed_search(self):
        self.worker.poll.return_value = dict(done=True, result=dict(ok=False, error='Cancelled'))
        with patch.object(drawer, 'answer_from_lens') as interpret:
            self.api.cancel_lens()
            self.assertFalse(self.api.poll_lens('job')['result']['ok'])
        self.worker.close.assert_called_once()
        interpret.assert_not_called()
