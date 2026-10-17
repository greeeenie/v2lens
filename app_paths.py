"""Locate a portable v2rayN installation without machine-specific paths."""
import hashlib
import os
from pathlib import Path
import sys
import tempfile

import psutil


ASSETS = Path(__file__).resolve().parent
FROZEN = bool(getattr(sys, 'frozen', False))
APP_HOME = Path(sys.executable).resolve().parent if FROZEN else ASSETS


def find_client(explicit=None):
    if explicit:
        client = Path(explicit).resolve()
        if not (client/'v2rayN.exe').is_file():
            raise ValueError('The selected folder does not contain v2rayN.exe.')
        return client
    for candidate in dict.fromkeys([APP_HOME, Path.cwd()]):
        if (candidate/'v2rayN.exe').is_file():
            return candidate.resolve()
    running = set()
    for process in psutil.process_iter(['name', 'exe']):
        if (process.info['name'] or '').lower() == 'v2rayn.exe' and process.info['exe']:
            running.add(Path(process.info['exe']).resolve().parent)
    if len(running) == 1:
        return running.pop()
    raise ValueError('Place V2Lens.exe next to v2rayN.exe and start v2rayN first. '
                     'You can also select a folder with --v2ray-dir PATH.')


def state_directory(client):
    preferred = APP_HOME/('V2Lens-data' if FROZEN else 'state')
    key = hashlib.sha256(str(client).lower().encode()).hexdigest()[:16]
    fallback = Path(os.environ.get('LOCALAPPDATA', str(Path.home())))/'V2Lens'/key
    for directory in [preferred, fallback]:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryFile(dir=directory):
                pass
            return directory
        except OSError:
            continue
    raise OSError('Unable to create the local application state folder.')
