import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import drawer

class LensOnlyTests(unittest.TestCase):
    def test_raw_results_and_current_chat_size(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / 'capture.png'
            image.write_bytes(b'capture')
            api = drawer.DrawerApi(str(image), (0, 0, 560, 680))
            window = Mock(width=720, height=810)
            result = dict(ok=True, text='Lens result', links=[])
            with patch.object(drawer, 'GLOBAL_WINDOW', window), patch.object(drawer, 'LensProcessClient') as factory:
                worker = factory.return_value
                worker.submit.return_value = 'job'
                worker.poll.return_value = dict(done=True, result=result)
                self.assertTrue(api.send_to_lens('Question')['ok'])
                factory.assert_called_once_with(b'capture', window_size=(720, 810))
                self.assertEqual(api.poll_lens('job')['result'], result)
                api.cancel_lens()
                worker.close.assert_called_once()
