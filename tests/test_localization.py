import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, MagicMock, patch
import sys

import drawer
from localization import get_language, set_language, settings_path, tr, google_language_url
from lens_session import LensSession


class LanguageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        environment = patch.dict(os.environ, {'LOCALAPPDATA': self.directory.name})
        environment.start()
        self.addCleanup(environment.stop)

    def test_default_invalid_and_saved_preference(self):
        self.assertEqual(get_language(), 'it')
        set_language('en')
        self.assertEqual(get_language(), 'en')
        self.assertEqual(tr('Copia testo'), 'Copy text')
        self.assertEqual(tr('Circle anything · Esc to exit'), 'Circle anything · Esc to exit')
        settings_path().write_text('{bad json')
        self.assertEqual(get_language(), 'it')
        self.assertEqual(tr('Circle anything · Esc to exit'), 'Cerchia qualsiasi cosa · Esc per uscire')
        settings_path().write_text('{"language":"xx"}')
        self.assertEqual(get_language(), 'it')

    def test_language_changes_preserve_other_settings_and_reject_unknown_values(self):
        set_language('it')
        settings_path().write_text(json.dumps(dict(language='it', extra='preserved')))
        set_language('en')
        self.assertEqual(json.loads(settings_path().read_text())['extra'], 'preserved')
        with self.assertRaises(ValueError):
            set_language('de')
        self.assertEqual(get_language(), 'en')

    def api(self):
        path = Path(self.directory.name) / 'capture.png'
        path.write_bytes(b'capture')
        with patch.object(drawer, 'GROQ_API_KEY', None):
            return drawer.DrawerApi(str(path), (0, 0, 560, 680))

    def test_choice_survives_new_chat_and_controls_ai_without_losing_history(self):
        api = self.api()
        api.conversation_history.append(dict(role='user', text='Earlier question'))
        self.assertTrue(api.set_language('en')['ok'])
        self.assertEqual(self.api().language, 'en')
        api.client = Mock()
        api.client.chat.completions.create.return_value.choices = [Mock(message=Mock(content='Answer'))]
        with patch.object(drawer, 'GLOBAL_WINDOW', Mock()):
            api._ask_ai('Domanda in italiano')
        messages = api.client.chat.completions.create.call_args.kwargs['messages']
        self.assertIn('Always answer in English.', messages[0]['content'])
        self.assertEqual(messages[1]['content'], 'Earlier question')

    def test_lens_interpretation_uses_chosen_language(self):
        api = self.api()
        api.set_language('en')
        api._lens_answers['job'] = dict(question='Question', result=None)
        with patch.object(drawer, 'answer_from_lens', return_value=dict(ok=True, text='Answer', interpreted=True)) as answer:
            api._interpret_lens('job', dict(ok=True, text='Results'))
        self.assertIn('Always answer in English.', answer.call_args.kwargs['system_prompt'])

    def test_failed_save_keeps_current_language(self):
        api = self.api()
        with patch.object(drawer, 'save_language', side_effect=OSError('read only')):
            self.assertFalse(api.set_language('en')['ok'])
        self.assertEqual(api.language, 'it')

    def test_lens_language_preserves_image_session(self):
        target = google_language_url('https://lens.google.com/search?p=IMAGE&hl=it&q=cat', 'en')
        self.assertIn('p=IMAGE', target)
        self.assertIn('hl=en', target)
        self.assertNotIn('hl=it', target)
        set_language('en')
        window = Mock()
        session = LensSession(b'image', visible=True, window_factory=Mock(return_value=window))
        session._navigate('https://www.google.com/imghp?hl=it')
        self.assertEqual(session.window_factory.call_args.kwargs['url'], 'https://www.google.com/imghp?hl=en')

    def test_native_chat_loads_saved_language_before_displaying_content(self):
        set_language('en')
        path = Path(self.directory.name) / 'capture.png'
        path.write_bytes(b'capture')
        webview = MagicMock()
        with patch.dict(sys.modules, {'webview': webview}), patch.object(drawer, 'GROQ_API_KEY', None), \
             patch.object(drawer, 'GLOBAL_WINDOW', None):
            drawer.run_drawer_app(str(path), 0, 0, 560, 680)
        html = webview.create_window.call_args.kwargs['html']
        self.assertIn('applyLanguage({"ok": true, "language": "en"', html)
