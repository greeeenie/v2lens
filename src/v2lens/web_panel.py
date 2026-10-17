"""A minimal local WebView2 connection viewer and full TUN template editor."""
import datetime as dt
import json
import sqlite3
import subprocess
from pathlib import Path
import threading
import time
import webview
from .traffic import TrafficMonitor
from .template_editor import TemplateConflict, TemplateStore
from .app_paths import ASSETS
from .client_reload import reload_client


def resized_bounds(bounds, minimum, edge, dx, dy):
    if edge not in ('left','right','top','bottom','top-left','top-right','bottom-left','bottom-right'):
        raise ValueError('Invalid resize edge')
    x,y,width,height=bounds
    if 'left' in edge:
        changed=max(minimum[0],width-dx)
        x+=width-changed;width=changed
    elif 'right' in edge:width=max(minimum[0],width+dx)
    if 'top' in edge:
        changed=max(minimum[1],height-dy)
        y+=height-changed;height=changed
    elif 'bottom' in edge:height=max(minimum[1],height+dy)
    return x,y,width,height


class Bridge:
    def __init__(self, collector, state):
        self._collector = collector
        self._state = state
        self._window = None
        self._maximized = False
        self._preferences_lock = threading.Lock()
        self._resize_lock = threading.Lock()
        self._traffic = TrafficMonitor(state)
        self._template = TemplateStore(collector.client)

    def get_template(self, mode='tun'):
        try:
            return {'ok': True, **self._template.load(mode)}
        except (OSError, ValueError, sqlite3.Error) as error:
            return {'ok': False, 'error': str(error)}

    def save_template(self, text, revision, auto_reload=False, mode='tun'):
        try:
            if not isinstance(auto_reload, bool):
                raise ValueError('Expected an auto-reload checkbox state')
            result = {'ok': True, **self._template.save(text, revision, mode)}
        except TemplateConflict as error:
            return {'ok': False, 'error': str(error), 'conflict': True}
        except (OSError, ValueError, sqlite3.Error) as error:
            return {'ok': False, 'error': str(error)}
        except subprocess.TimeoutExpired:
            return {'ok': False, 'error': 'Xray validation timed out. The template was not saved.'}
        if auto_reload and result['enabled']:
            try:
                active = self._template.active_mode()
                if active == mode:
                    reload_client(self._template.client)
                    result['reloaded'] = True
                elif active is None:
                    result['reload_error'] = 'Cannot identify the active mode. Use Reload in v2rayN.'
                else:
                    result['applies_when'] = mode
            except (OSError, ValueError) as error:
                result['reload_error'] = str(error)
        return result

    def _editor_state_path(self, mode):
        TemplateStore.field(mode)
        return self._state/('editor.json' if mode=='tun' else 'editor-standard.json')

    def get_editor_state(self, mode='tun'):
        path = self._editor_state_path(mode)
        with self._preferences_lock:
            try:
                value = json.loads(path.read_text(encoding='utf-8'))
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

    def set_editor_state(self, value, mode='tun'):
        path = self._editor_state_path(mode)
        folds = self._validate_folds(value['folds'])
        with self._preferences_lock:
            temp = path.with_suffix('.tmp')
            temp.write_text(json.dumps({'folds': folds}), encoding='utf-8')
            temp.replace(path)
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
            if value.get('sort_field') in ('app', 'protocol', 'gateway', 'route', 'time', 'traffic'):
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
        if field not in ('app', 'protocol', 'gateway', 'route', 'time', 'traffic') or direction not in ('asc', 'desc'):
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

    def begin_resize(self, edge):
        resized_bounds((0,0,0,0),(0,0),edge,0,0)
        import ctypes
        from ctypes import wintypes
        from System import Action
        native = self._window.native
        # Borderless WinForms has no Windows sizing frame. Track the held drag
        # and update native bounds on its UI thread, including outside WebView.
        if not self._resize_lock.acquire(blocking=False):return
        try:
            user32 = ctypes.WinDLL('user32',use_last_error=True)
            user32.GetAsyncKeyState.restype = ctypes.c_short
            user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
            start = wintypes.POINT()
            if not user32.GetAsyncKeyState(1)&0x8000 or not user32.GetCursorPos(ctypes.byref(start)):return
            initial=[]
            def capture():
                if str(native.WindowState)!='Maximized':
                    initial.extend([(native.Left,native.Top,native.Width,native.Height),(native.MinimumSize.Width,native.MinimumSize.Height)])
            native.Invoke(Action(capture))
            if not initial:return
            previous=initial[0]
            while not self._collector.stop.is_set() and user32.GetAsyncKeyState(1)&0x8000:
                cursor=wintypes.POINT()
                if not user32.GetCursorPos(ctypes.byref(cursor)):break
                bounds=resized_bounds(*initial,edge,cursor.x-start.x,cursor.y-start.y)
                if bounds!=previous:
                    native.Invoke(Action(lambda: native.SetBounds(*bounds)))
                    previous=bounds
                time.sleep(1/60)
        finally:
            self._resize_lock.release()

    def maximize(self):
        if self._maximized:
            self._window.restore()
        else:
            self._window.maximize()
        self._maximized = not self._maximized
        return self._maximized

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
        min_size=(690, 450), resizable=True, frameless=True, easy_drag=False, shadow=True,
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
        webview.start(gui='edgechromium', debug=False, private_mode=True, icon=str(ASSETS/'v2lens.ico'))
    finally:
        collector.stop.set()
