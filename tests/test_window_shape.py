import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import window_shape


class WindowShapeTests(unittest.TestCase):
    def install(self, scale=1, region=123, success=1):
        form = MagicMock()
        form.Resize.__iadd__.return_value = form.Resize
        form.DeviceDpi = 96 * scale
        form.ClientSize.Width, form.ClientSize.Height = 560 * scale, 760 * scale
        form.Handle.ToInt64.return_value = 2**33 + 7
        window = Mock(native=form)
        gdi = MagicMock()
        gdi.CreateRoundRectRgn.return_value = region
        user = MagicMock()
        user.SetWindowRgn.return_value = success
        fullscreen = Mock(return_value=False)
        with patch.object(window_shape.sys, 'platform', 'win32'), \
             patch.object(window_shape.ctypes, 'windll', SimpleNamespace(gdi32=gdi, user32=user), create=True):
            window_shape.install_drawer_shape(window, fullscreen)
        return form, gdi, user, fullscreen

    def test_region_removes_padding_at_windows_dpi_and_preserves_64_bit_handles(self):
        _, gdi, user, _ = self.install(scale=2)
        gdi.CreateRoundRectRgn.assert_called_once_with(24, 16, 1097, 1505, 128, 128)
        user.SetWindowRgn.assert_called_once_with(2**33 + 7, 123, True)
        gdi.DeleteObject.assert_not_called()

    def test_resize_updates_shape_and_fullscreen_removes_clipping(self):
        form, gdi, user, fullscreen = self.install()
        resize = form.Resize.__iadd__.call_args.args[0]
        form.ClientSize.Width = 800
        resize()
        self.assertEqual(gdi.CreateRoundRectRgn.call_args.args[2], 789)
        fullscreen.return_value = True
        resize()
        user.SetWindowRgn.assert_called_with(2**33 + 7, None, True)

    def test_failed_region_install_releases_only_unowned_region(self):
        with self.assertLogs('shakesearch', level='ERROR'):
            _, gdi, _, _ = self.install(success=0)
        gdi.DeleteObject.assert_called_once_with(123)
