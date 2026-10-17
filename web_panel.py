"""A minimal local WebView2 connection viewer and full TUN template editor."""
import datetime as dt
import json
import sqlite3
import subprocess
from pathlib import Path
import threading
import webview
from traffic import TrafficMonitor
from template_editor import TemplateConflict, TemplateStore
from app_paths import ASSETS
from client_reload import reload_client


class Bridge:
    def __init__(self, collector, state):
        self._collector = collector
        self._state = state
        self._window = None
        self._maximized = False
        self._preferences_lock = threading.Lock()
        self._traffic = TrafficMonitor(state)
        self._template = TemplateStore(collector.client)

    def get_template(self):
        try:
            return {'ok': True, **self._template.load()}
        except (OSError, ValueError, sqlite3.Error) as error:
            return {'ok': False, 'error': str(error)}

    def save_template(self, text, revision, auto_reload=False):
        try:
            if not isinstance(auto_reload, bool):
                raise ValueError('Expected an auto-reload checkbox state')
            result = {'ok': True, **self._template.save(text, revision)}
        except TemplateConflict as error:
            return {'ok': False, 'error': str(error), 'conflict': True}
        except (OSError, ValueError, sqlite3.Error) as error:
            return {'ok': False, 'error': str(error)}
        except subprocess.TimeoutExpired:
            return {'ok': False, 'error': 'Xray validation timed out. The template was not saved.'}
        if auto_reload and result['enabled']:
            try:
                reload_client(self._template.client)
                result['reloaded'] = True
            except (OSError, ValueError) as error:
                result['reload_error'] = str(error)
        return result

    def get_editor_state(self):
        with self._preferences_lock:
            try:
                value = json.loads((self._state/'editor.json').read_text(encoding='utf-8'))
                return {'folds': self._validate_folds(value['folds'])}
            except (OSError, ValueError, KeyError, TypeError):
                return {'folds': []}

    @staticmethod
    def _validate_folds(folds):
        if not isinstance(folds, list) or len(folds) > 10000:
            raise ValueError('Invalid editor fold state')
        for path in folds:
            if not isinstance(path, list) or len(path) > 128 or any(
                not isinstance(part, str) and (type(part) is not int or part < 0) for part in path
            ):
                raise ValueError('Invalid editor fold path')
        return folds

    def set_editor_state(self, value):
        folds = self._validate_folds(value['folds'])
        with self._preferences_lock:
            temp = self._state/'editor.tmp'
            temp.write_text(json.dumps({'folds': folds}), encoding='utf-8')
            temp.replace(self._state/'editor.json')
        return True

    def snapshot(self):
        records = self._collector.snapshot()
        traffic = self._traffic.attach(records)
        result = {'records': records, 'error': self._collector.error,
                  'updated': dt.datetime.now().strftime('%H:%M:%S'), 'traffic': traffic}
        # Retain the local diagnostic snapshot used by the existing checks.
        try:
            data = {'updated': dt.datetime.now().isoformat(), 'records': records[-300:]}
            temp = self._state/'snapshot.tmp'
            temp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
            temp.replace(self._state/'snapshot.json')
        except OSError:
            pass
        return result

    def _read_preferences(self):
        defaults = {'hide_unknown': False, 'group_by_app': False, 'sort_field': 'app', 'sort_direction': 'asc', 'auto_reload': False}
        try:
            value = json.loads((self._state/'preferences.json').read_text(encoding='utf-8'))
            defaults['hide_unknown'] = value.get('hide_unknown') is True
            defaults['group_by_app'] = value.get('group_by_app') is True
            defaults['auto_reload'] = value.get('auto_reload') is True
            if value.get('sort_field') in ('app', 'protocol', 'route', 'time', 'traffic'):
                defaults['sort_field'] = value['sort_field']
            if value.get('sort_direction') in ('asc', 'desc'):
                defaults['sort_direction'] = value['sort_direction']
        except (OSError, ValueError, AttributeError):
            pass
        return defaults

    def get_preferences(self):
        with self._preferences_lock:
            return self._read_preferences()

    def _update_preferences(self, **updates):
        with self._preferences_lock:
            value = self._read_preferences()
            value.update(updates)
            temp = self._state/'preferences.tmp'
            temp.write_text(json.dumps(value), encoding='utf-8')
            temp.replace(self._state/'preferences.json')

    def set_hide_unknown(self, value):
        if not isinstance(value, bool):
            raise ValueError('Expected a checkbox state')
        self._update_preferences(hide_unknown=value)
        return True

    def set_sort(self, field, direction):
        if field not in ('app', 'protocol', 'route', 'time', 'traffic') or direction not in ('asc', 'desc'):
            raise ValueError('Invalid sort order')
        self._update_preferences(sort_field=field, sort_direction=direction)
        return True

    def set_group_by_app(self, value):
        if not isinstance(value, bool):
            raise ValueError('Expected a checkbox state')
        self._update_preferences(group_by_app=value)
        return True

    def set_auto_reload(self, value):
        if not isinstance(value, bool):
            raise ValueError('Expected a checkbox state')
        self._update_preferences(auto_reload=value)
        return True

    def enable_traffic(self):
        return self._traffic.enable()

    def minimize(self):
        self._window.minimize()

    def maximize(self):
        if self._maximized:
            self._window.restore()
        else:
            self._window.maximize()
        self._maximized = not self._maximized

    def close(self):
        self._collector.stop.set()
        self._window.destroy()


def run(collector, state, smoke_test=None):
    bridge = Bridge(collector, state)
    html = (ASSETS/'panel.html').read_text(encoding='utf-8')
    editor = (ASSETS/'json-editor.js').read_text(encoding='utf-8')
    html = html.replace('<!-- JSON_EDITOR_BUNDLE -->', '<script>'+editor.replace('</script', '<\\/script')+'</script>')
    webview.settings['ALLOW_FILE_URLS'] = False
    bridge._window = webview.create_window(
        'V2Lens', html=html, js_api=bridge, width=980, height=720,
        min_size=(690, 450), frameless=True, easy_drag=False, shadow=True,
        background_color='#111315', text_select=True)
    bridge._window.events.closed += lambda: collector.stop.set()
    if smoke_test:
        def verify_window():
            import time
            try:
                bridge._window.evaluate_js("switchView('template')")
                time.sleep(2)
                report = bridge._window.evaluate_js("({editor:!!document.querySelector('.cm-editor'),text:getTemplateEditor().getValue(),checkbox:!!document.getElementById('auto-reload'),status:document.getElementById('template-status').textContent})")
                smoke_test.write_text(json.dumps(report),encoding='utf-8')
            except Exception as error:
                smoke_test.write_text(json.dumps({'error':str(error)}),encoding='utf-8')
            finally:
                bridge.close()
        bridge._window.events.loaded += verify_window
    try:
        webview.start(gui='edgechromium', debug=False, private_mode=True, icon=str(ASSETS/'assets/v2lens.ico'))
    finally:
        collector.stop.set()
