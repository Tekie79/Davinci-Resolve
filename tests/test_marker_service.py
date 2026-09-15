import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from meher_resolve_hub.models.marker import MarkerRecord
from meher_resolve_hub.history import OperationHistory
from meher_resolve_hub.resolve_context import ResolveContextService
from meher_resolve_hub.services.marker_service import MarkerService
from tests.fakes import FakeProject, FakeResolve, FakeTimeline, FailingMarkerTimeline


def record_for(timeline):
    return MarkerRecord("timeline", "timeline", 10, 10, 11, 2, "Blue", "Old", "Note", "x", source_object=timeline)


class MarkerServiceTests(unittest.TestCase):
    def service(self, timeline): return MarkerService(ResolveContextService(FakeResolve(FakeProject(timeline))))

    def test_range_relationships(self):
        record = record_for(FakeTimeline())
        self.assertEqual(self.service(record.source_object).edit_range(record, start=9).duration_frames, 3)
        self.assertEqual(self.service(record.source_object).edit_range(record, end=14).duration_frames, 5)
        self.assertEqual(self.service(record.source_object).edit_range(record, duration=8).end_frame, 17)
        moved = self.service(record.source_object).edit_range(record, move=5)
        self.assertEqual((moved.start_frame, moved.end_frame, moved.duration_frames), (15, 16, 2))

    def test_replace_marker_verifies_success(self):
        timeline = FailingMarkerTimeline(fail_new=False)
        result = self.service(timeline).replace_marker(record_for(timeline), record_for(timeline).copy(frame=20, start_frame=20, end_frame=21, name="New"))
        self.assertTrue(result.success); self.assertIn(20, timeline.markers); self.assertNotIn(10, timeline.markers)

    def test_replace_marker_verifies_custom_data(self):
        timeline = FailingMarkerTimeline(fail_new=False)
        original = record_for(timeline)
        candidate = original.copy(custom_data='{"type":"review"}')
        result = self.service(timeline).replace_marker(original, candidate)
        self.assertTrue(result.success)
        self.assertEqual(timeline.GetMarkerCustomData(10), '{"type":"review"}')

    def test_failed_replacement_restores_original(self):
        timeline = FailingMarkerTimeline(fail_new=True, fail_rollback=False)
        result = self.service(timeline).replace_marker(record_for(timeline), record_for(timeline).copy(frame=20, start_frame=20, end_frame=21))
        self.assertFalse(result.success); self.assertIn(10, timeline.markers); self.assertIn("restored", result.errors[0])

    def test_rollback_failure_is_prominent(self):
        timeline = FailingMarkerTimeline(fail_new=True, fail_rollback=True)
        result = self.service(timeline).replace_marker(record_for(timeline), record_for(timeline).copy(frame=20, start_frame=20, end_frame=21))
        self.assertFalse(result.success); self.assertIn("CRITICAL", result.errors[0])

    def test_batch_range_preview_and_delete(self):
        timeline = FailingMarkerTimeline(fail_new=False)
        service = self.service(timeline); record = record_for(timeline)
        preview = service.preview_batch([record], "range", "Extend End", "5")
        self.assertEqual(preview.changed, 1); self.assertEqual(preview.changes[0].context["candidate"].duration_frames, 7)
        delete = service.preview_batch([record], "delete", "Set", "")
        self.assertEqual(delete.changes[0].after, "Deleted")

    def test_add_and_batch_delete_are_undoable(self):
        timeline = FakeTimeline()
        history = OperationHistory()
        service = MarkerService(ResolveContextService(FakeResolve(FakeProject(timeline))), history)
        added = service.add_marker(timeline, 20, "Green", "New", custom_data="tag")
        self.assertTrue(added.success); self.assertIn(20, timeline.markers)
        self.assertTrue(history.undo().success); self.assertNotIn(20, timeline.markers)

        timeline.markers[10] = {"color": "Blue", "name": "Old", "note": "Note", "duration": 2, "customData": "x"}
        record = record_for(timeline)
        deleted = service.apply_preview(service.preview_batch([record], "delete", "Set", ""))
        self.assertTrue(deleted.success); self.assertNotIn(10, timeline.markers)
        self.assertTrue(history.undo().success); self.assertIn(10, timeline.markers)

    def test_add_accepts_resolve_none_return_when_marker_was_written(self):
        class NoneReturningTimeline(FakeTimeline):
            def AddMarker(self, frame, color, name, note, duration, custom_data=""):
                super().AddMarker(frame, color, name, note, duration, custom_data)
                return None

        timeline = NoneReturningTimeline()
        result = self.service(timeline).add_marker(timeline, 20, "Green", "New")
        self.assertTrue(result.success)
        self.assertEqual(timeline.markers[20]["name"], "New")

    def test_replace_and_delete_accept_none_return_after_verified_write(self):
        class NoneReturningTimeline(FailingMarkerTimeline):
            def DeleteMarkerAtFrame(self, frame):
                super().DeleteMarkerAtFrame(frame)
                return None

            def AddMarker(self, frame, color, name, note, duration, custom_data=""):
                super().AddMarker(frame, color, name, note, duration, custom_data)
                return None

        timeline = NoneReturningTimeline(fail_new=False)
        service = self.service(timeline)
        original = record_for(timeline)
        replacement = original.copy(frame=20, start_frame=20, end_frame=21, name="Updated")
        result = service.replace_marker(original, replacement)
        self.assertTrue(result.success)
        self.assertIn(20, timeline.markers)
        deleted = service.apply_preview(service.preview_batch([replacement], "delete", "Set", ""))
        self.assertTrue(deleted.success)
        self.assertNotIn(20, timeline.markers)

    def test_marker_lookup_accepts_numeric_string_keys(self):
        marker = {"color": "Green", "name": "New", "note": "", "duration": 1, "customData": ""}
        self.assertIs(MarkerService._marker_at_frame({"20.0": marker}, 20), marker)


if __name__ == "__main__": unittest.main()
