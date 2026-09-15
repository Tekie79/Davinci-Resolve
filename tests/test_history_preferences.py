import tempfile
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from meher_resolve_hub.history import OperationHistory
from meher_resolve_hub.models.operation import OperationRecord, OperationResult
from meher_resolve_hub.preferences import Preferences, valid_window_geometry


class HistoryPreferencesTests(unittest.TestCase):
    def test_history_serialization_and_guarded_undo(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "history.json"; history = OperationHistory(path); record = OperationRecord("test", "Change", ["1"], {"1": "a"}, {"1": "b"}); history.add(record)
            loaded = OperationHistory(path); loaded.load(); self.assertEqual(loaded.peek().label, "Change")
            loaded.register("test", lambda value: OperationResult(True, changed=1)); result = loaded.undo(); self.assertTrue(result.success); self.assertIsNone(loaded.peek())

    def test_failed_undo_keeps_history(self):
        history = OperationHistory(); history.add(OperationRecord("test", "Change", ["1"], {}, {})); history.register("test", lambda value: OperationResult(False, failed=1))
        self.assertFalse(history.undo().success); self.assertIsNotNone(history.peek())

    def test_preferences_merge_defaults_and_persist(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"; prefs = Preferences(path); prefs.load(); prefs.set("general", "last_workspace", "Health")
            loaded = Preferences(path); loaded.load(); self.assertEqual(loaded.get("general", "last_workspace"), "Health"); self.assertTrue(loaded.get("thumbnails", "enabled"))

    def test_invalid_resolve_geometry_falls_back_to_default(self):
        self.assertEqual(valid_window_geometry([1, 2, 3, 4]), [120, 80, 1240, 780])
        self.assertEqual(valid_window_geometry([160, 90, 1280, 800]), [160, 90, 1280, 800])

    def test_invalid_saved_geometry_is_sanitized_on_load(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            path.write_text('{"general":{"window_geometry":[1,2,3,4]}}', encoding="utf-8")
            prefs = Preferences(path); prefs.load()
            self.assertEqual(prefs.get("general", "window_geometry"), [120, 80, 1240, 780])


if __name__ == "__main__": unittest.main()
