"""Regression tests from the v0.3.22 source audit; no live Resolve required."""

import unittest

from meher_resolve_hub.history import OperationHistory
from meher_resolve_hub.models.operation import Change, PreviewSummary
from meher_resolve_hub.resolve_context import ResolveContextService
from meher_resolve_hub.services.marker_service import MarkerService
from meher_resolve_hub.services.metadata_service import MetadataService
from tests.fakes import FakeClip, FakeProject, FakeResolve, FakeTimeline


class IdentifiedTimeline(FakeTimeline):
    def __init__(self, identity="timeline-a", **kwargs):
        super().__init__(**kwargs)
        self.identity = identity

    def GetUniqueId(self):
        return self.identity


class StringKeyTimeline(IdentifiedTimeline):
    def GetMarkers(self):
        return {str(frame): dict(info) for frame, info in self.markers.items()}


class MarkerAuditTests(unittest.TestCase):
    def setUp(self):
        self.timeline = IdentifiedTimeline()
        self.project = FakeProject(self.timeline)
        self.history = OperationHistory()
        self.service = MarkerService(
            ResolveContextService(FakeResolve(self.project)), self.history
        )

    def add(self, frame=10, name="Original"):
        self.timeline.AddMarker(frame, "Blue", name, "original note", 2, "external-data")
        return next(item for item in self.service.list_markers() if item.frame == frame)

    def edit(self):
        original = self.add()
        self.assertTrue(self.service.replace_marker(original, original.copy(name="Edited")).success)
        return original

    def test_undo_edit_preserves_later_native_notes(self):
        self.edit()
        self.timeline.markers[10]["note"] = "director changed this in Resolve"
        result = self.history.undo()
        self.assertFalse(result.success)
        self.assertEqual(self.timeline.markers[10]["note"], "director changed this in Resolve")
        self.assertEqual(self.timeline.markers[10]["name"], "Edited")

    def test_undo_add_preserves_later_native_notes(self):
        self.assertTrue(self.service.add_marker(self.timeline, 10, "Blue", "Added").success)
        self.timeline.markers[10]["note"] = "new review note"
        result = self.history.undo()
        self.assertFalse(result.success)
        self.assertEqual(self.timeline.markers[10]["note"], "new review note")

    def test_undo_edit_never_targets_another_timeline(self):
        self.edit()
        other = IdentifiedTimeline("timeline-b", markers={10: dict(self.timeline.markers[10])})
        self.project.timeline = other
        result = self.history.undo()
        self.assertFalse(result.success)
        self.assertEqual(other.markers[10]["name"], "Edited")
        self.assertEqual(self.timeline.markers[10]["name"], "Edited")

    def test_undo_add_never_deletes_lookalike_on_another_timeline(self):
        self.assertTrue(self.service.add_marker(self.timeline, 10, "Blue", "Added").success)
        other = IdentifiedTimeline("timeline-b", markers={10: dict(self.timeline.markers[10])})
        self.project.timeline = other
        result = self.history.undo()
        self.assertFalse(result.success)
        self.assertIn(10, other.markers)
        self.assertIn(10, self.timeline.markers)

    def test_string_key_collision_does_not_delete_unrelated_marker(self):
        self.timeline = StringKeyTimeline()
        self.project.timeline = self.timeline
        original = self.add()
        self.timeline.AddMarker(20, "Red", "Do not delete", "review", 1, "foreign")
        before = {frame: dict(info) for frame, info in self.timeline.markers.items()}
        candidate = self.service.edit_range(original, move=10)
        result = self.service.replace_marker(original, candidate)
        self.assertFalse(result.success)
        self.assertEqual(self.timeline.markers, before)

    def test_batch_move_handles_selected_destination_markers(self):
        self.add(10, "A")
        self.add(20, "B")
        preview = self.service.preview_batch(self.service.list_markers(), "start_frame", "Move", "10")
        result = self.service.apply_preview(preview)
        self.assertTrue(result.success)
        self.assertEqual(set(self.timeline.markers), {20, 30})
        self.assertEqual(self.timeline.markers[20]["name"], "A")
        self.assertEqual(self.timeline.markers[30]["name"], "B")
        self.assertTrue(self.history.undo().success)
        self.assertEqual(set(self.timeline.markers), {10, 20})

    def test_batch_range_preview_rejects_negative_start(self):
        original = self.add()
        preview = self.service.preview_batch([original], "range", "Extend Start", "20")
        self.assertEqual(preview.changes[0].status, "Invalid")
        self.assertEqual(preview.changed, 0)

    def test_batch_range_preview_rejects_zero_duration(self):
        original = self.add()
        preview = self.service.preview_batch([original], "range", "Set Duration", "0")
        self.assertEqual(preview.changes[0].status, "Invalid")
        self.assertEqual(preview.changed, 0)


class MetadataAuditTests(unittest.TestCase):
    def setUp(self):
        self.clip = FakeClip("clip-1", "Camera Clip", {"Scene": "1", "Take": "1"})
        self.history = OperationHistory()
        self.service = MetadataService(self.history)
        self.record = self.service.build_records([self.clip])[0]

    def test_multi_field_preview_undo_restores_all_fields_once(self):
        preview = PreviewSummary([
            Change("clip-1", "Camera Clip", "Scene", "1", "2", "Ready", source=self.record),
            Change("clip-1", "Camera Clip", "Take", "1", "3", "Ready", source=self.record),
        ])
        self.assertTrue(self.service.apply_preview(preview).success)
        self.assertTrue(self.history.undo().success)
        self.assertEqual(self.clip.metadata, {"Scene": "1", "Take": "1"})

    def test_stale_batch_preview_does_not_overwrite_native_edit(self):
        preview = self.service.preview_batch([self.record], "Scene", "Set", "2")
        self.clip.metadata["Scene"] = "director edit"
        result = self.service.apply_preview(preview)
        self.assertFalse(result.success)
        self.assertEqual(self.clip.metadata["Scene"], "director edit")
        self.assertIsNone(self.history.peek())


if __name__ == "__main__":
    unittest.main()
