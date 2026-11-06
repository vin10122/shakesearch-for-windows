"""Launch the same application roles from source or a frozen Windows bundle."""
from pathlib import Path
import os
import sys


def child_environment(role):
    environment = os.environ.copy()
    if getattr(sys, 'frozen', False) and role == 'drawer':
        # The chat can outlive the capture app. Give it its own onefile extraction
        # so closing the parent cannot remove libraries still used by the chat.
        environment['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    return environment


def child_command(role, *arguments):
    if role not in {'drawer', 'lens_worker'}:
        raise ValueError(f'Unknown application role: {role}')
    if getattr(sys, 'frozen', False):
        command = [sys.executable, '--role', role]
    else:
        executable = Path(sys.executable)
        if executable.name.lower() == 'pythonw.exe' and executable.with_name('python.exe').is_file():
            executable = executable.with_name('python.exe')
        command = [str(executable), str(Path(__file__).with_name(role + '.py'))]
    return command + [str(argument) for argument in arguments]
