"""Editor fold persistence uses local UI state, without touching the template DB."""
import json
from pathlib import Path
import tempfile
import threading
import unittest

from v2lens.web_panel import Bridge


class EditorStateTests(unittest.TestCase):
    def bridge(self, state):
        bridge = Bridge.__new__(Bridge)
        bridge._state = state
        bridge._preferences_lock = threading.Lock()
        return bridge

    def test_state_survives_a_new_bridge(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder)
            first = self.bridge(state)
            self.assertEqual(first.get_editor_state(), {'folds': []})
            value = {'folds': [[], ['routing'], ['routing', 'rules', 0]]}
            first.set_editor_state(value)
            self.assertEqual(self.bridge(state).get_editor_state(), value)
            self.assertEqual(json.loads((state/'editor.json').read_text()), value)
            first.set_editor_state({'folds': []})
            self.assertEqual(self.bridge(state).get_editor_state(), {'folds': []})

    def test_corrupt_state_and_invalid_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder)
            bridge = self.bridge(state)
            (state/'editor.json').write_text('{broken')
            self.assertEqual(bridge.get_editor_state(), {'folds': []})
            for folds in [None, {}, [True], [[True]], [[-1]], [[{}]]]:
                with self.assertRaises(ValueError):
                    bridge.set_editor_state({'folds': folds})
            self.assertEqual((state/'editor.json').read_text(), '{broken')


if __name__ == '__main__':
    unittest.main()
