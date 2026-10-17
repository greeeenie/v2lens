"""Correlate local ETW byte counters with identified access-log connections."""
import ctypes
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from app_paths import ASSETS


def group_key(record):
    return tuple(record.get(field) for field in ('app', 'pid', 'protocol', 'destination', 'port', 'outbound'))


class TrafficMonitor:
    def __init__(self, state):
        self.state = Path(state)
        self.requested = False
        self.error = ''
        self.samples = {}

    def enable(self):
        if self.requested:
            return True
        source = ASSETS/'traffic-helper'
        version = hashlib.sha256((source/'TrafficObserver.exe').read_bytes()).hexdigest()[:16]
        directory = self.state/'runtime'/version/'traffic-helper'
        if not (directory/'TrafficObserver.exe').is_file():
            directory.mkdir(parents=True, exist_ok=True)
            for path in source.rglob('*'):
                if path.is_file() and path.suffix.lower() in ('.exe', '.dll'):
                    target = directory/path.relative_to(source)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, target)
        executable = directory/'TrafficObserver.exe'
        shell = ctypes.windll.shell32.ShellExecuteW
        shell.restype = ctypes.c_void_p
        shell.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p,
                          ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_int]
        arguments = subprocess.list2cmdline([str(os.getpid()), str(self.state/'traffic.json')])
        result = shell(None, 'runas', str(executable), arguments, str(executable.parent), 0) or 0
        self.requested = result > 32
        self.error = '' if self.requested else 'Traffic permission was not granted.'
        return self.requested

    def attach(self, records):
        status = {'status': 'starting' if self.requested else 'off', 'error': self.error}
        try:
            data = json.loads((self.state/'traffic.json').read_text(encoding='utf-8-sig'))
            if data.get('viewer_pid') != os.getpid():
                return status
            if time.time()-data.get('updated', 0) > 5:
                self.requested = False
                return {'status': 'unavailable', 'error': 'Traffic observer stopped responding.'}
            status = {key: data.get(key) for key in ('status', 'started', 'lost_events', 'error')}
            if data.get('status') != 'running':
                self.requested = False
                return status
        except (OSError, ValueError, TypeError, AttributeError):
            return status

        # Only an exact process, local endpoint and peer match can own bytes.
        # Ambiguous or missing matches remain unavailable, never a guessed zero.
        endpoints = {}
        groups = {}
        for record in records:
            if not record.get('pid') or not record.get('path'):
                continue
            key = group_key(record)
            groups.setdefault(key, []).append(record)
            local = (record['protocol'], record['pid'], record['source'], record['local_port'])
            endpoints.setdefault(local, []).append(record)
        totals = {}
        for flow in data.get('flows', []):
            local = (flow.get('protocol'), flow.get('pid'), flow.get('local'), flow.get('local_port'))
            candidates = endpoints.get(local, [])
            matched = set()
            for record in candidates:
                peer = record.get('remote_ip', record['destination'])
                port = record.get('remote_port', record['port'])
                try:
                    same_ip = ipaddress.ip_address(peer) == ipaddress.ip_address(flow['remote'])
                except ValueError:
                    same_ip = False
                if same_ip and port == flow.get('remote_port') and record['time'] <= flow.get('last', 0)+1:
                    matched.add(group_key(record))
            if len(matched) != 1:
                continue
            key = next(iter(matched))
            counter = totals.setdefault(key, {'sent': 0, 'received': 0})
            counter['sent'] += max(0, int(flow.get('sent', 0)))
            counter['received'] += max(0, int(flow.get('received', 0)))
        for key, counter in totals.items():
            previous = self.samples.get(key)
            updated = data['updated']
            if previous and updated == previous['updated']:
                counter.update(up_rate=previous['up_rate'], down_rate=previous['down_rate'])
            elif previous and updated > previous['updated']:
                elapsed = updated-previous['updated']
                counter.update(up_rate=max(0, counter['sent']-previous['sent'])/elapsed,
                               down_rate=max(0, counter['received']-previous['received'])/elapsed)
            else:
                counter.update(up_rate=0, down_rate=0)
            self.samples[key] = dict(counter, updated=updated)
            for record in groups[key]:
                record['traffic'] = counter
        self.samples = {key: value for key, value in self.samples.items() if key in groups}
        return status
