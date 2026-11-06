import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app_runtime import child_command, child_environment
import portable_main


class PortableRuntimeTests(unittest.TestCase):
    def test_independent_frozen_chat_uses_its_own_extraction(self):
        with patch.object(sys, 'frozen', True, create=True), \
                patch.dict(os.environ, {'SHAKESEARCH_TEST': 'preserved'}):
            environment = child_environment('drawer')
            self.assertEqual(environment['PYINSTALLER_RESET_ENVIRONMENT'], '1')
            self.assertEqual(environment['SHAKESEARCH_TEST'], 'preserved')
            self.assertNotIn('PYINSTALLER_RESET_ENVIRONMENT', os.environ)

    def test_bundled_worker_reuses_its_parents_extraction(self):
        with patch.object(sys, 'frozen', True, create=True):
            self.assertNotIn('PYINSTALLER_RESET_ENVIRONMENT', child_environment('lens_worker'))

    def test_bundle_smoke_test_dispatch(self):
        for flag, child in [('--self-test', False), ('--self-test-child', True)]:
            with patch.object(sys, 'argv', ['ShakeSearch.exe', flag]), \
                    patch('portable_main.smoke_test', return_value=0) as smoke:
                self.assertEqual(portable_main.main(), 0)
                smoke.assert_called_once_with(child=child)

    def test_source_launch_keeps_script_and_arguments(self):
        with patch.object(sys, 'frozen', False, create=True):
            command = child_command('drawer', 'capture with spaces.png', -20, 40, 560, 680)
        self.assertEqual(Path(command[1]).name, 'drawer.py')
        self.assertEqual(command[2:], ['capture with spaces.png', '-20', '40', '560', '680'])

    def test_frozen_launch_reuses_exe_without_python_script(self):
        with patch.object(sys, 'frozen', True, create=True), patch.object(sys, 'executable', 'C:/ShakeSearch.exe'):
            self.assertEqual(child_command('lens_worker', 560, 680, 'LensProfile'),
                             ['C:/ShakeSearch.exe', '--role', 'lens_worker', '560', '680', 'LensProfile'])

    def test_frozen_worker_dispatch_preserves_size_and_profile(self):
        arguments = ['ShakeSearch.exe', '--role', 'lens_worker', '560', '680', 'LensTextProfile']
        with patch.object(sys, 'argv', arguments), patch('multiprocessing.freeze_support'), \
             patch('lens_worker.main', return_value=0) as worker:
            self.assertEqual(portable_main.main(), 0)
            worker.assert_called_once_with(560, 680, 'LensTextProfile')

    def test_frozen_drawer_dispatch_preserves_negative_monitor_position(self):
        arguments = ['ShakeSearch.exe', '--role', 'drawer', 'capture.png', '-560', '40', '560', '680']
        with patch.object(sys, 'argv', arguments), patch('multiprocessing.freeze_support'), \
             patch('drawer.run_drawer_app') as drawer:
            portable_main.main()
            drawer.assert_called_once_with('capture.png', -560, 40, 560, 680)

    def test_unknown_role_is_rejected(self):
        with self.assertRaises(ValueError):
            child_command('unknown')
