import sys
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock, patch

import browser_window

URL = 'http://127.0.0.1:12345/token'
VIVALDI = r'C:\Users\Someone\AppData\Local\Vivaldi\Application\vivaldi.exe'


class BrowserWindowTests(unittest.TestCase):
    def test_known_browsers_receive_explicit_new_window_flag(self):
        for name in ('chrome.exe', 'msedge.exe', 'brave.exe', 'vivaldi.exe', 'opera.exe'):
            with self.subTest(browser=name):
                executable = rf'C:\Program Files\Browser\{name}'
                command = browser_window.browser_command(executable, URL)
                self.assertEqual(command[0], executable)
                self.assertIn('--new-window', command)
                self.assertEqual(command[-1], URL)
        self.assertEqual(browser_window.browser_command('firefox.exe', URL),
                         ['firefox.exe', '-new-window', URL])
        self.assertIsNone(browser_window.browser_command('unknown.exe', URL))

    def test_https_association_selects_actual_default_browser(self):
        registry = MagicMock(HKEY_CURRENT_USER=1, HKEY_CLASSES_ROOT=2)
        def open_key(root, path):
            if 'Software\\Classes' in path:
                raise FileNotFoundError(path)
            return MagicMock()
        registry.OpenKey.side_effect = open_key
        registry.QueryValueEx.side_effect = lambda key, name: (
            ('VivaldiHTM', 1) if name == 'ProgId' else (f'"{VIVALDI}" --single-argument "%1"', 1))
        with patch.dict(sys.modules, {'winreg': registry}):
            self.assertEqual(browser_window.windows_default_browser(), VIVALDI)
        self.assertTrue(any(call.args[0] == 2 and 'VivaldiHTM' in call.args[1]
                            for call in registry.OpenKey.call_args_list))

    def test_windows_launches_separate_browser_then_focuses_new_window(self):
        with patch.object(browser_window.sys, 'platform', 'win32'), \
             patch.object(browser_window, 'windows_default_browser', return_value=VIVALDI), \
             patch.object(browser_window, 'browser_windows', return_value=[100]), \
             patch.object(browser_window, 'foreground_new_browser_window') as focus, \
             patch.object(browser_window.subprocess, 'Popen') as launch, \
             patch.object(browser_window.webbrowser, 'open') as generic:
            self.assertTrue(browser_window.open_browser_window(URL))
        command = launch.call_args.args[0]
        self.assertEqual(command[0], VIVALDI)
        self.assertIn('--new-window', command)
        self.assertEqual(command[-1], URL)
        self.assertTrue(launch.call_args.kwargs['close_fds'])
        focus.assert_called_once_with(VIVALDI, {100})
        generic.assert_not_called()

    def test_unknown_browser_uses_default_handler_with_new_window_request(self):
        with patch.object(browser_window.sys, 'platform', 'win32'), \
             patch.object(browser_window, 'windows_default_browser', return_value='unknown.exe'), \
             patch.object(browser_window.webbrowser, 'open', return_value=True) as generic:
            self.assertTrue(browser_window.open_browser_window(URL))
        generic.assert_called_once_with(URL, new=1, autoraise=True)

    def test_focus_targets_new_browser_window_not_existing_window(self):
        gui = Mock()
        gui.IsIconic.return_value = True
        constants = SimpleNamespace(SW_RESTORE=9, HWND_TOP=0, SWP_NOMOVE=2, SWP_NOSIZE=1, SWP_SHOWWINDOW=64)
        with patch.dict(sys.modules, {'win32gui': gui, 'win32con': constants}), \
             patch.object(browser_window, 'browser_windows', return_value=[100, 200]):
            browser_window.foreground_new_browser_window(VIVALDI, {100})
        gui.ShowWindow.assert_called_once_with(200, 9)
        gui.SetForegroundWindow.assert_called_once_with(200)
        self.assertEqual(gui.SetWindowPos.call_args.args[0], 200)

    def test_window_detection_matches_browser_and_releases_process_handles(self):
        handles = {1: Mock(), 2: Mock()}
        api = SimpleNamespace(OpenProcess=Mock(side_effect=lambda access, inherit, pid: handles[pid]))
        process = SimpleNamespace(
            GetWindowThreadProcessId=lambda hwnd: (10, hwnd),
            GetModuleFileNameEx=lambda handle, module: VIVALDI.upper() if handle is handles[1] else r'C:\other.exe')
        gui = SimpleNamespace(
            IsWindowVisible=lambda hwnd: hwnd != 3,
            EnumWindows=lambda callback, extra: [callback(hwnd, extra) for hwnd in (1, 2, 3)])
        with patch.dict(sys.modules, {'win32api': api, 'win32process': process, 'win32gui': gui}):
            self.assertEqual(browser_window.browser_windows(VIVALDI), [1])
        for handle in handles.values():
            handle.Close.assert_called_once()
