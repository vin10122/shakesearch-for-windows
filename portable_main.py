"""Frozen entry point, including the application's isolated GUI workers."""
import multiprocessing
import sys


def main():
    multiprocessing.freeze_support()
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
        if role == 'ocr_viewer':
            from ocr_viewer import main as viewer_main
            return viewer_main()
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
