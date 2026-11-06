"""Frozen entry point, including the application's isolated GUI workers."""
import multiprocessing
import sys


def smoke_test(child=False):
    """Validate bundled native libraries and an independent onefile child."""
    import subprocess
    import cv2
    import numpy as np
    from PIL import Image
    from PySide6.QtGui import QImage
    import webview.platforms.edgechromium
    import win32clipboard
    from app_icon import icon_path
    from app_runtime import child_environment
    from desktop_input import verify_native_hotkey

    assert icon_path().is_file(), 'Bundled icon is missing'
    assert not QImage(8, 8, QImage.Format.Format_ARGB32).isNull()
    assert Image.new('RGB', (8, 8)).size == (8, 8)
    assert cv2.cvtColor(np.zeros((8, 8, 3), np.uint8), cv2.COLOR_BGR2GRAY).shape == (8, 8)
    verify_native_hotkey()
    if not child:
        result = subprocess.run([sys.executable, '--self-test-child'],
                                env=child_environment('drawer'), capture_output=True,
                                text=True, timeout=120)
        if result.returncode or 'ShakeSearch bundle OK' not in result.stdout:
            raise RuntimeError('Bundled child failed: ' + result.stdout + result.stderr)
    print('ShakeSearch bundle OK', flush=True)
    return 0


def main():
    multiprocessing.freeze_support()
    if len(sys.argv) == 2 and sys.argv[1] in ('--self-test', '--self-test-child'):
        return smoke_test(child=sys.argv[1] == '--self-test-child')
    if len(sys.argv) >= 3 and sys.argv[1] == '--role':
        role = sys.argv[2]
        sys.argv = [sys.argv[0]] + sys.argv[3:]
        if role == 'drawer':
            from drawer import run_drawer_app
            if len(sys.argv) != 6:
                raise ValueError('Invalid drawer arguments')
            return run_drawer_app(sys.argv[1], *map(int, sys.argv[2:]))
        if role == 'lens_worker':
            from lens_worker import main as worker_main
            return worker_main(int(sys.argv[1]), int(sys.argv[2]), sys.argv[3])
        raise ValueError(f'Unknown application role: {role}')
    from shakesearch import main as capture_main
    return capture_main()


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:
        import traceback
        traceback.print_exc()
        if '--role' not in sys.argv and sys.stdin is not None and sys.stdin.isatty():
            input("ShakeSearch non si è avviato. Premi Invio per chiudere...")
        raise
