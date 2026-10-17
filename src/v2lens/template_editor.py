"""Read and validate the two independent native v2rayN Xray templates."""
from contextlib import closing
import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import threading


class TemplateError(ValueError):
    pass


class TemplateConflict(TemplateError):
    pass


class TemplateStore:
    FIELDS = {'tun': 'TunConfig', 'standard': 'Config'}

    @classmethod
    def field(cls, mode):
        if mode not in cls.FIELDS:
            raise TemplateError('Unknown template mode.')
        return cls.FIELDS[mode]

    def __init__(self, client, validator=None):
        self.client = Path(client)
        self.database = self.client / 'guiConfigs/guiNDB.db'
        self._validator = validator or self._validate_core
        self._lock = threading.Lock()

    def _connect(self, writable=False):
        connection = sqlite3.connect(self.database.resolve().as_uri() + ('?mode=rw' if writable else '?mode=ro'), uri=True, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _read(connection):
        rows = connection.execute('SELECT Id, Enabled, Config, TunConfig, AddProxyOnly, ProxyDetour FROM FullConfigTemplateItem WHERE CoreType=2').fetchall()
        if len(rows) != 1:
            raise TemplateError('The Xray template could not be identified. Open Full Config Template Setting in v2rayN first.')
        return dict(rows[0])

    @classmethod
    def _revision(cls, row, mode='tun'):
        value = {key:row[key] for key in ['Id','Enabled','AddProxyOnly','ProxyDetour',cls.field(mode)]}
        value['mode'] = mode
        return hashlib.sha256(json.dumps(value, sort_keys=True).encode('utf-8')).hexdigest()

    def active_mode(self):
        try:
            runtime = json.loads((self.client/'binConfigs/config.json').read_text(encoding='utf-8-sig'))
            return self._runtime_mode(runtime)
        except (OSError, ValueError, TypeError):
            return None

    @staticmethod
    def _runtime_mode(runtime):
        return 'tun' if any(item.get('protocol')=='tun' for item in runtime.get('inbounds',[]) if isinstance(item,dict)) else 'standard'

    def load(self, mode='tun'):
        field = self.field(mode)
        with closing(self._connect()) as connection:
            row = self._read(connection)
        return {'text': row[field] or '', 'revision': self._revision(row,mode), 'enabled': bool(row['Enabled']), 'mode':mode}

    @staticmethod
    def _parse(text, mode='tun'):
        if not isinstance(text, str) or len(text.encode('utf-8')) > 2 * 1024 * 1024:
            raise TemplateError('Expected a JSON template smaller than 2 MB.')
        try:
            def invalid_constant(value):
                raise ValueError('Invalid JSON value: ' + value)
            template = json.loads(text, parse_constant=invalid_constant)
        except json.JSONDecodeError as error:
            raise TemplateError(f'JSON line {error.lineno}, column {error.colno}: {error.msg}') from error
        if not isinstance(template, dict):
            raise TemplateError('The template must be a JSON object.')
        inbounds = template.get('inbounds')
        if mode == 'tun' and (not isinstance(inbounds, list) or not any(isinstance(item, dict) and item.get('protocol') == 'tun' and item.get('tag') == 'tun' for item in inbounds)):
            raise TemplateError('The TUN template must contain an inbound tagged "tun" with protocol "tun".')
        if mode == 'standard':
            if not isinstance(inbounds,list) or not inbounds:
                raise TemplateError('The Without TUN template must contain at least one inbound.')
            if any(isinstance(item,dict) and item.get('protocol')=='tun' for item in inbounds):
                raise TemplateError('A Without TUN template cannot contain a TUN inbound.')
        return template

    def _validate_core(self, template, row):
        try:
            runtime = json.loads((self.client / 'binConfigs/config.json').read_text(encoding='utf-8-sig'))
        except (OSError, ValueError) as error:
            raise TemplateError('Start v2rayN once before saving this template.') from error
        try:
            previous = json.loads(row[self.field(self._runtime_mode(runtime))] or '{}')
        except ValueError:
            previous = {}
        if not isinstance(previous, dict):
            previous = {}
        # Remove the previous template's extra outbounds before appending the new ones.
        old_tags = {item.get('tag') for item in previous.get('outbounds', []) if isinstance(item, dict)}
        outbounds = [item for item in runtime.get('outbounds', []) if item.get('tag') not in old_tags]
        if row['AddProxyOnly']:
            outbounds = [item for item in outbounds if item.get('protocol') not in ('freedom', 'blackhole', 'dns')]
        if not outbounds:
            raise TemplateError('The selected proxy is unavailable. Start v2rayN first.')
        if row['ProxyDetour']:
            raise TemplateError('This template uses an upstream detour. Validate and edit it in v2rayN.')
        extra = template.get('outbounds', [])
        if not isinstance(extra, list):
            raise TemplateError('outbounds must be an array.')
        candidate = copy.deepcopy(template)
        candidate['outbounds'] = outbounds + extra
        environment = os.environ.copy()
        environment['xray.location.asset'] = str(self.client / 'bin')
        environment['xray.location.cert'] = str(self.client / 'bin')
        with tempfile.TemporaryDirectory(prefix='xray-template-check-') as directory:
            filename = Path(directory) / 'config.json'
            filename.write_text(json.dumps(candidate, ensure_ascii=False), encoding='utf-8')
            completed = subprocess.run([str(self.client / 'bin/xray/xray.exe'), 'run', '-test', '-c', str(filename)],
                                       env=environment, capture_output=True, timeout=15,
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if completed.returncode:
            details = (completed.stdout + completed.stderr).decode('utf-8', errors='replace').strip().splitlines()
            reason = next((line for line in reversed(details) if 'Failed to start:' in line), details[-1] if details else 'Invalid configuration')
            raise TemplateError(reason.replace('Failed to start: ', '', 1))

    def save(self, text, revision, mode='tun'):
        field = self.field(mode)
        template = self._parse(text,mode)
        with self._lock:
            with closing(self._connect()) as connection:
                row = self._read(connection)
            if self._revision(row,mode) != revision:
                raise TemplateConflict('The template changed in v2rayN. Your edits have been kept. Load the latest version before saving.')
            self._validator(template, row)
            with closing(self._connect(writable=True)) as connection:
                with connection:
                    connection.execute('BEGIN IMMEDIATE')
                    current = self._read(connection)
                    if self._revision(current,mode) != revision:
                        raise TemplateConflict('The template changed while checking. Your edits have been kept. Load the latest version before saving.')
                    connection.execute(f'UPDATE FullConfigTemplateItem SET {field}=? WHERE Id=? AND CoreType=2', (text, row['Id']))
                    current[field] = text
            return {'revision': self._revision(current,mode), 'enabled': bool(current['Enabled']), 'mode':mode}
