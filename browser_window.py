"""Open the user's browser in a separate window and request foreground focus."""
import logging
import ntpath
import re
import subprocess
import sys
import time
import webbrowser

logger = logging.getLogger('shakesearch')


def windows_default_browser():
    """Read the HTTPS association without running its registry command in a shell."""
    import winreg

    choice = r'Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice'
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, choice) as key:
            prog_id = winreg.QueryValueEx(key, 'ProgId')[0]
        for root, path in (
                (winreg.HKEY_CURRENT_USER, rf'Software\Classes\{prog_id}\shell\open\command'),
                (winreg.HKEY_CLASSES_ROOT, rf'{prog_id}\shell\open\command')):
            try:
                with winreg.OpenKey(root, path) as key:
                    command = winreg.QueryValueEx(key, '')[0]
            except OSError:
                continue
            match = re.match(r'\s*(?:"([^"\r\n]+\.exe)"|([^"\r\n]+?\.exe))(?:\s|$)', command, re.I)
            if match:
                return ntpath.expandvars(match.group(1) or match.group(2))
    except OSError:
        pass
    return None


def browser_command(executable, url):
    name = ntpath.basename(executable).lower()
    if name == 'firefox.exe':
        return [executable, '-new-window', url]
    if name in {'chrome.exe', 'chromium.exe', 'msedge.exe', 'brave.exe',
                'vivaldi.exe', 'opera.exe', 'opera_gx.exe', 'browser.exe'}:
        return [executable, '--new-window', '--window-size=900,740', url]
    return None


def browser_windows(executable):
    """Find visible windows owned by this browser, including an existing process."""
    import win32api
    import win32gui
    import win32process

    expected = ntpath.normcase(ntpath.normpath(executable))
    matches = []

    def visit(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        handle = None
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            handle = win32api.OpenProcess(0x1000, False, pid)  # Limited query access only.
            # With a null module, Windows 10+ accepts limited-query access.
            actual = win32process.GetModuleFileNameEx(handle, 0)
            if ntpath.normcase(ntpath.normpath(actual)) == expected:
                matches.append(hwnd)
        except Exception:
            pass  # Other apps may deny access to their process metadata.
        finally:
            if handle is not None:
                handle.Close()

    win32gui.EnumWindows(visit, None)
    return matches


def foreground_new_browser_window(executable, previous, timeout=4):
    import win32con
    import win32gui

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        windows = [hwnd for hwnd in browser_windows(executable) if hwnd not in previous]
        if windows:
            hwnd = windows[-1]
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, 0, 0, 0, 0,
                                  win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW)
            try:
                win32gui.SetForegroundWindow(hwnd)
            except Exception:
                logger.info('Windows declined explicit browser focus; foreground request was sent')
            return
        time.sleep(.05)
    logger.info('New browser window was not detected before the focus timeout')


def open_browser_window(url):
    if sys.platform == 'win32':
        try:
            executable = windows_default_browser()
            command = browser_command(executable, url) if executable else None
            if command:
                try:
                    previous = set(browser_windows(executable))
                except Exception:
                    previous = None
                subprocess.Popen(command, close_fds=True)
                if previous is not None:
                    try:
                        foreground_new_browser_window(executable, previous)
                    except Exception:
                        logger.exception('Unable to explicitly focus the browser window')
                return True
        except Exception:
            logger.exception('Separate browser launch failed; trying the default URL handler')
    # Windows' generic URL handler cannot guarantee new-window behavior for an
    # unknown browser. Known browsers above receive their explicit window flag.
    return webbrowser.open(url, new=1, autoraise=True)
