import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from v2lens.template_editor import TemplateConflict, TemplateError, TemplateStore


class TemplateStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='template-editor-test-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / 'guiConfigs').mkdir()
        self.path = self.root / 'guiConfigs/guiNDB.db'
        self.template = {'inbounds': [{'protocol': 'tun', 'tag': 'tun'}], 'routing': {'rules': []}}
        self.original = json.dumps(self.template, indent=2)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('CREATE TABLE FullConfigTemplateItem(Id TEXT, CoreType INTEGER, Enabled INTEGER, TunConfig TEXT, AddProxyOnly INTEGER, ProxyDetour TEXT, Config TEXT)')
            connection.execute('INSERT INTO FullConfigTemplateItem VALUES(?,2,1,?,0,NULL,?)', ('xray-template', self.original, 'regular config retained'))
            connection.execute('CREATE TABLE RoutingItem(RuleSet TEXT)')
            connection.execute("INSERT INTO RoutingItem VALUES('ordinary rules retained')")
        self.validations = []
        self.store = TemplateStore(self.root, validator=lambda value, row: self.validations.append(value))

    def stored(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            return connection.execute('SELECT TunConfig FROM FullConfigTemplateItem').fetchone()[0]

    def external_change(self, text):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('UPDATE FullConfigTemplateItem SET TunConfig=?', (text,))

    def test_roundtrip_preserves_other_settings(self):
        loaded = self.store.load()
        edited = self.original + '\n'
        saved = self.store.save(edited, loaded['revision'])
        self.assertEqual(self.stored(), edited)
        self.assertEqual(self.store.load()['revision'], saved['revision'])
        self.assertNotEqual(saved['revision'], loaded['revision'])
        self.assertEqual(self.validations, [self.template])
        with closing(sqlite3.connect(self.path)) as connection, connection:
            self.assertEqual(connection.execute('SELECT Enabled,AddProxyOnly,ProxyDetour,Config FROM FullConfigTemplateItem').fetchone(), (1, 0, None, 'regular config retained'))
            self.assertEqual(connection.execute('SELECT RuleSet FROM RoutingItem').fetchone()[0], 'ordinary rules retained')

    def test_invalid_json_and_missing_tun_do_not_write(self):
        revision = self.store.load()['revision']
        for invalid in ('{bad json}', '[]', '{"inbounds": []}'):
            with self.assertRaises(TemplateError):
                self.store.save(invalid, revision)
        self.assertEqual(self.stored(), self.original)
        self.assertEqual(self.validations, [])

    def test_core_validation_failure_does_not_write(self):
        def reject(value, row):
            raise TemplateError('Invalid Xray outbound')
        self.store._validator = reject
        with self.assertRaisesRegex(TemplateError, 'Invalid Xray'):
            self.store.save(self.original + '\n', self.store.load()['revision'])
        self.assertEqual(self.stored(), self.original)

    def test_stale_editor_cannot_overwrite_external_edit(self):
        revision = self.store.load()['revision']
        external = self.original + '\n\n'
        self.external_change(external)
        with self.assertRaises(TemplateConflict):
            self.store.save(self.original + '\n', revision)
        self.assertEqual(self.stored(), external)
        self.assertEqual(self.validations, [])

    def test_change_during_validation_is_also_preserved(self):
        revision = self.store.load()['revision']
        external = self.original + '\n\n'
        self.store._validator = lambda value, row: self.external_change(external)
        with self.assertRaises(TemplateConflict):
            self.store.save(self.original + '\n', revision)
        self.assertEqual(self.stored(), external)

    def test_save_does_not_enable_disabled_template(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('UPDATE FullConfigTemplateItem SET Enabled=0')
        loaded = self.store.load()
        self.assertFalse(self.store.save(self.original + '\n', loaded['revision'])['enabled'])

    def test_modes_save_independently_and_have_separate_revisions(self):
        tun=self.store.load('tun')
        standard=self.store.load('standard')
        text=json.dumps({'inbounds':[{'tag':'socks','protocol':'socks','port':2081}]})
        result=self.store.save(text,standard['revision'],'standard')
        self.assertEqual(self.store.load('standard')['text'],text)
        self.assertEqual(self.store.load('tun'),tun)
        self.assertEqual(result['mode'],'standard')
        self.store.save(self.original+'\n',tun['revision'],'tun')
        self.assertEqual(self.store.load('standard')['revision'],result['revision'])

    def test_wrong_mode_or_mode_token_never_overwrites_a_template(self):
        tun=self.store.load('tun')
        standard=self.store.load('standard')
        with self.assertRaises(TemplateError):self.store.save(self.original,standard['revision'],'standard')
        plain='{"inbounds":[{"tag":"socks","protocol":"socks","port":2081}]}'
        with self.assertRaises(TemplateConflict):self.store.save(plain,tun['revision'],'standard')
        with self.assertRaises(TemplateError):self.store.save(plain,tun['revision'],'bad-column')
        self.assertEqual(self.store.load('tun'),tun)
        self.assertEqual(self.store.load('standard'),standard)

    def test_standard_template_native_validation_while_tun_is_running(self):
        (self.root/'binConfigs').mkdir()
        runtime={'inbounds':[{'tag':'tun','protocol':'tun'}], 'outbounds':[
            {'tag':'proxy','protocol':'socks','settings':{'servers':[{'address':'127.0.0.1','port':1080}]}},
            {'tag':'old-tun-extra','protocol':'blackhole'}]}
        (self.root/'binConfigs/config.json').write_text(json.dumps(runtime))
        old=json.loads(self.original);old['outbounds']=[{'tag':'old-tun-extra','protocol':'blackhole'}]
        self.external_change(json.dumps(old))
        plain={'inbounds':[{'tag':'socks','protocol':'socks','port':2081}]}
        candidates=[]
        def native_check(args,**kwargs):
            candidates.append(json.loads(Path(args[-1]).read_text()))
            return SimpleNamespace(returncode=0,stdout=b'',stderr=b'')
        self.store._validator=self.store._validate_core
        with patch('v2lens.template_editor.subprocess.run',side_effect=native_check):
            self.store.save(json.dumps(plain),self.store.load('standard')['revision'],'standard')
        self.assertEqual(candidates[0]['inbounds'],plain['inbounds'])
        self.assertEqual([item['tag'] for item in candidates[0]['outbounds']],['proxy'])

    def test_empty_template_loads_without_changing_the_other_mode(self):
        with closing(self.store._connect(writable=True)) as connection,connection:
            connection.execute('UPDATE FullConfigTemplateItem SET Config=NULL')
        self.assertEqual(self.store.load('standard')['text'],'')
        self.assertEqual(self.store.load('tun')['text'],self.original)


if __name__ == '__main__':
    unittest.main()
