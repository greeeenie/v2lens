import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from v2lens import app_paths
from v2lens.template_editor import TemplateConflict
from v2lens.web_panel import Bridge


class PortableTests(unittest.TestCase):
    def test_prefers_exe_folder_and_keeps_state_local(self):
        with tempfile.TemporaryDirectory(prefix='v2lens чужая папка ') as folder:
            directory=Path(folder)
            (directory/'v2rayN.exe').touch()
            with patch.object(app_paths,'APP_HOME',directory),patch.object(app_paths,'FROZEN',True):
                self.assertEqual(app_paths.find_client(),directory.resolve())
                self.assertEqual(app_paths.state_directory(directory),directory/'V2Lens-data')
            self.assertEqual(app_paths.find_client(directory),directory.resolve())

    def test_saved_template_reload_success_and_failure_are_distinct(self):
        bridge=Bridge.__new__(Bridge)
        bridge._template=Mock(client=Path('client'))
        bridge._template.active_mode.return_value='tun'
        bridge._template.save.return_value={'revision':'new','enabled':True}
        with patch('v2lens.web_panel.reload_client',return_value=True) as reload:
            self.assertTrue(bridge.save_template('{}','old',True)['reloaded'])
            reload.assert_called_once_with(Path('client'))
        with patch('v2lens.web_panel.reload_client',side_effect=ValueError('Reload failed')):
            result=bridge.save_template('{}','old',True)
            self.assertTrue(result['ok'])
            self.assertEqual(result['revision'],'new')
            self.assertEqual(result['reload_error'],'Reload failed')
        bridge._template.save.side_effect=TemplateConflict('Changed elsewhere')
        with patch('v2lens.web_panel.reload_client') as reload:
            self.assertFalse(bridge.save_template('{}','old',True)['ok'])
            reload.assert_not_called()

    def test_reload_off_or_disabled_template_never_reloads(self):
        bridge=Bridge.__new__(Bridge)
        bridge._template=Mock(client=Path('client'))
        with patch('v2lens.web_panel.reload_client') as reload:
            for enabled,auto in [(True,False),(False,True)]:
                bridge._template.save.return_value={'revision':'new','enabled':enabled}
                self.assertTrue(bridge.save_template('{}','old',auto)['ok'])
            reload.assert_not_called()

    def test_inactive_template_does_not_restart_active_mode(self):
        bridge=Bridge.__new__(Bridge)
        bridge._template=Mock(client=Path('client'))
        bridge._template.active_mode.return_value='tun'
        bridge._template.save.return_value={'revision':'new','enabled':True}
        with patch('v2lens.web_panel.reload_client') as reload:
            result=bridge.save_template('{}','old',True,'standard')
            self.assertEqual(result['applies_when'],'standard')
            reload.assert_not_called()

    def test_auto_reload_preference_survives_other_preferences(self):
        with tempfile.TemporaryDirectory() as folder:
            bridge=Bridge.__new__(Bridge)
            bridge._state=Path(folder)
            bridge._preferences_lock=threading.Lock()
            bridge.set_auto_reload(True)
            bridge.set_hide_unknown(True)
            self.assertTrue(bridge.get_preferences()['auto_reload'])
            self.assertTrue(json.loads((Path(folder)/'preferences.json').read_text())['auto_reload'])


if __name__=='__main__':unittest.main()
