"""Local Xray access-log viewer. Route labels come exclusively from Xray logs."""
import argparse
import collections
import datetime as dt
import json
from pathlib import Path
import re
import socket
import sys
import threading
import time

import psutil
from app_paths import find_client, state_directory

ROUTES = {'proxy': 'Proxy', 'direct': 'Direct', 'block': 'Blocked', 'dns': 'DNS Xray'}
LINE = re.compile(r'^(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}\.\d+) from (\S+) (accepted|rejected) (\S+) \[([^\]]+)\]')


def endpoint(value):
    proto, addr = value.split(':', 1)
    host, port = addr.rsplit(':', 1)
    return proto.upper(), host.strip('[]'), int(port)


def record_key(record):
    return tuple(record.get(field) for field in (
        'time', 'protocol', 'source', 'local_port', 'destination', 'port', 'inbound', 'outbound'))


def parse_line(line):
    match = LINE.search(line)
    if not match:
        return None
    timestamp, source, verdict, target, detour = match.groups()
    try:
        protocol, ip, port = endpoint(source)
        _, target_ip, target_port = endpoint(target)
        inbound, outbound = re.split(r'\s*(?:->|>>)\s*', detour, maxsplit=1)
        stamp = dt.datetime.strptime(timestamp, '%Y/%m/%d %H:%M:%S.%f').timestamp()
    except (ValueError, TypeError):
        return None
    return dict(time=stamp, protocol=protocol, source=ip, local_port=port,
                destination=target_ip, port=target_port, inbound=inbound,
                outbound=outbound, verdict=verdict, app='Unknown process', pid=None,
                path='', owner_evidence='The process could not be matched to this connection. It may have already closed or predate the viewer.')


class Collector:
    def __init__(self, client=None, state=None):
        self.client = Path(client) if client else find_client()
        self.state = Path(state) if state else state_directory(self.client)
        self.records = collections.deque(maxlen=3000)
        self.owners = {}
        self.current = {}
        self.peers = {}
        self.process_cache = {}
        self.offsets = {}
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.error = ''
        self.log_path = ''
        self.serial = 0
        self.last_scan = 0
        self.remembered_owners = {}
        # Preserve an attribution already observed for this exact historical event.
        # Never attach an old PID to a different connection that reused its port.
        try:
            saved = json.loads((self.state/'snapshot.json').read_text(encoding='utf-8'))
            for record in saved.get('records', [])[-300:]:
                if (isinstance(record.get('pid'), int) and record['pid'] > 0
                        and time.time()-900 < record.get('time', 0) <= time.time()+1):
                    self.remembered_owners[record_key(record)] = {
                        field: record[field] for field in ('app', 'pid', 'path', 'owner_evidence', 'remote_ip', 'remote_port') if field in record}
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        self.thread = threading.Thread(target=self.run, daemon=True)

    def scan_owners(self):
        now = time.time()
        found = collections.defaultdict(set)
        peers = collections.defaultdict(set)
        for conn in psutil.net_connections(kind='inet'):
            if not conn.laddr or not conn.pid:
                continue
            proto = 'TCP' if conn.type == socket.SOCK_STREAM else 'UDP'
            found[(proto, conn.laddr.ip, conn.laddr.port)].add(conn.pid)
            if conn.raddr:
                peers[(proto, conn.laddr.ip, conn.laddr.port, conn.pid)].add((conn.raddr.ip, conn.raddr.port))
            if conn.pid not in self.process_cache:
                try:
                    proc = psutil.Process(conn.pid)
                    self.process_cache[conn.pid] = (proc.name(), proc.exe(), proc.create_time())
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    self.process_cache[conn.pid] = (f'PID {conn.pid}', '', now)
        self.current = dict(found)
        self.peers = dict(peers)
        for key, pids in found.items():
            self.owners[key] = (now, pids)
        self.owners = {key: value for key, value in self.owners.items() if now-value[0] < 4}
        live_pids = {pid for pids in found.values() for pid in pids}
        self.process_cache = {pid: value for pid, value in self.process_cache.items() if pid in live_pids}
        self.last_scan = now

    def owner(self, record):
        # Old log entries must never be attributed to a newly reused source port.
        if abs(self.last_scan-record['time']) > 4:
            return
        key = (record['protocol'], record['source'], record['local_port'])
        candidates = self.current.get(key)
        if not candidates:
            wildcard = (record['protocol'], '::' if ':' in record['source'] else '0.0.0.0', record['local_port'])
            candidates = self.current.get(wildcard)
        if not candidates:
            seen, candidates = self.owners.get(key, (0, set()))
            if abs(seen-record['time']) > 2:
                return
        if len(candidates) != 1:
            return
        pid = next(iter(candidates))
        name, path, created = self.process_cache.get(pid, (f'PID {pid}', '', time.time()))
        if created > record['time'] + 0.2:
            return
        record.update(app=name, pid=pid, path=path, owner_evidence='Windows source address, port and protocol matched to the Xray log')
        peers = self.peers.get((*key, pid), set())
        if len(peers) == 1:
            remote_ip, remote_port = next(iter(peers))
            record.update(remote_ip=remote_ip, remote_port=remote_port)

    def read_logs(self):
        # v2rayN keeps the startup day's filename even across midnight.
        paths = []
        try:
            config = json.loads((self.client / 'binConfigs/config.json').read_text(encoding='utf-8-sig'))
            if config.get('log', {}).get('access'):
                path = Path(config['log']['access'])
                paths.append(path if path.is_absolute() else self.client/path)
        except (OSError, ValueError):
            pass
        if not paths:
            paths = sorted((self.client/'guiLogs').glob('Vaccess_*.txt'), key=lambda p:p.stat().st_mtime)[-1:]
        if not paths:
            self.error = 'No Xray access log found. Enable file logging in v2rayN.'
            return
        self.log_path = str(paths[0])
        for path in paths:
            if not path.exists():
                continue
            size = path.stat().st_size
            initial = path not in self.offsets
            offset = self.offsets.get(path, max(0, size-128*1024))
            if size < offset:
                offset = 0
            with path.open('rb') as handle:
                handle.seek(offset)
                if initial and offset:
                    handle.readline()
                while True:
                    start = handle.tell()
                    raw = handle.readline()
                    if not raw or not raw.endswith(b'\n'):
                        handle.seek(start)
                        break
                    record = parse_line(raw.decode('utf-8', errors='replace'))
                    if record and record['time'] > time.time()-900:
                        self.serial += 1
                        record['id'] = self.serial
                        previous = self.remembered_owners.get(record_key(record))
                        if previous:
                            record.update(previous)
                        else:
                            self.owner(record)
                        self.records.append(record)
                self.offsets[path] = handle.tell()

    def run(self):
        while not self.stop.is_set():
            try:
                with self.lock:
                    self.scan_owners()
                    self.read_logs()
                    for record in list(self.records)[-150:]:
                        if record['pid'] is None:
                            self.owner(record)
                    self.error = '' if self.log_path else self.error
            except (OSError, psutil.Error, ValueError) as exc:
                self.error = str(exc)
            self.stop.wait(0.35)

    def snapshot(self):
        now = time.time()
        with self.lock:
            records = [dict(r) for r in self.records if now-r['time'] < 900]
            current = dict(self.current)
        for record in records:
            key=(record['protocol'],record['source'],record['local_port'])
            record['active'] = (record['protocol']=='TCP' and record['pid'] is not None
                                and record['pid'] in current.get(key,set()))
        return records



def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--collect-seconds',type=float)
    parser.add_argument('--v2ray-dir')
    parser.add_argument('--diagnose', type=Path)
    parser.add_argument('--smoke-test', type=Path)
    parser.add_argument('--reload-test', type=Path)
    args=parser.parse_args()
    client=find_client(args.v2ray_dir)
    state=state_directory(client)
    if args.reload_test:
        from client_reload import reload_client
        try:
            report={'ok':reload_client(client)}
        except Exception as error:
            report={'ok':False,'error':str(error)}
        args.reload_test.write_text(json.dumps(report),encoding='utf-8')
        return
    if args.diagnose:
        from app_paths import ASSETS
        from web_panel import Bridge
        report={'client':str(client),'state':str(state),'assets':str(ASSETS),
                'database':(client/'guiConfigs/guiNDB.db').is_file(),
                'panel':(ASSETS/'panel.html').is_file(),'editor':(ASSETS/'json-editor.js').is_file(),
                'traffic_helper':(ASSETS/'traffic-helper/TrafficObserver.exe').is_file()}
        args.diagnose.write_text(json.dumps(report,indent=2),encoding='utf-8')
        return
    collector=Collector(client,state);collector.thread.start()
    if args.collect_seconds:
        time.sleep(args.collect_seconds);collector.stop.set()
        print(json.dumps(collector.snapshot(),ensure_ascii=False,indent=2));return
    from web_panel import run
    run(collector, state, smoke_test=args.smoke_test)


if __name__=='__main__':
    try:
        main()
    except Exception as error:
        if getattr(sys, 'frozen', False):
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,str(error),'V2Lens',0x10)
        else:
            raise
