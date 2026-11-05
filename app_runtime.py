"""Launch the same application roles from source or a frozen Windows bundle."""
from pathlib import Path
import sys


def child_command(role, *arguments):
    if role not in {'drawer', 'lens_worker', 'ocr_viewer'}:
        raise ValueError(f'Unknown application role: {role}')
    if getattr(sys, 'frozen', False):
        command = [sys.executable, '--role', role]
    else:
        executable = Path(sys.executable)
        if executable.name.lower() == 'pythonw.exe' and executable.with_name('python.exe').is_file():
            executable = executable.with_name('python.exe')
        command = [str(executable), str(Path(__file__).with_name(role + '.py'))]
    return command + [str(argument) for argument in arguments]
