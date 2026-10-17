"""Request v2rayN's native F5 Reload and confirm that its Xray process changes."""
import ctypes
from ctypes import wintypes
from pathlib import Path
import time

import psutil


class ReloadError(ValueError):
    pass


def client_process(client):
    executable = (Path(client)/'v2rayN.exe').resolve()
    for process in psutil.process_iter(['name', 'exe']):
        if (process.info['name'] or '').lower() == 'v2rayn.exe' and process.info['exe']:
            if Path(process.info['exe']).resolve() == executable:
                return process
    raise ReloadError('v2rayN is not running. Start it and use Reload there.')


def core_processes(process):
    try:
        return {(child.pid, child.create_time()) for child in process.children(recursive=True)
                if child.name().lower() == 'xray.exe'}
    except psutil.Error as error:
        raise ReloadError('Cannot inspect v2rayN. Run Connections with the same administrator rights as v2rayN.') from error


def request_reload(process):
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostMessageW.restype = wintypes.BOOL
    windows = []

    @callback_type
    def inspect(hwnd, _):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == process.pid:
            title = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, title, len(title))
            if 'v2rayn' in title.value.lower():
                windows.append(hwnd)
        return True

    user32.EnumWindows(inspect, 0)
    if len(windows) != 1:
        raise ReloadError('Cannot identify the v2rayN main window. Open it and try saving again.')
    # F5 is handled by MainWindow_KeyDown in both standard Windows clients.
    scan = user32.MapVirtualKeyW(0x74, 0) << 16
    if not user32.PostMessageW(windows[0], 0x100, 0x74, 1 | scan):
        raise ReloadError('Reload was blocked. Run Connections with the same administrator rights as v2rayN.')
    user32.PostMessageW(windows[0], 0x101, 0x74, 1 | scan | 0xC0000000)


def reload_client(client, timeout=12):
    process = client_process(client)
    before = core_processes(process)
    if not before:
        raise ReloadError('No running Xray core found. Enable the Xray profile in v2rayN first.')
    request_reload(process)
    deadline = time.monotonic()+timeout
    while time.monotonic() < deadline:
        time.sleep(.15)
        after = core_processes(process)
        if after and after.isdisjoint(before):
            # Confirm the new process survives startup, rather than just being spawned.
            time.sleep(.6)
            if after & core_processes(process):
                return True
    raise ReloadError('No Xray restart was confirmed. The template is saved; use Reload in v2rayN.')
