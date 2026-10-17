import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

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


if __name__ == '__main__':
    unittest.main()
