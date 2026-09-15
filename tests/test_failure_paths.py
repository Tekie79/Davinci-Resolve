import tempfile
import unittest
from pathlib import Path

from meher_resolve_hub.history import OperationHistory
from meher_resolve_hub.models.clip import ClipRecord
from meher_resolve_hub.resolve_context import ResolveContextService
from meher_resolve_hub.services.metadata_service import MetadataService
from meher_resolve_hub.services.rename_service import RenameService
from meher_resolve_hub.services.still_service import StillError, StillService
from meher_resolve_hub.thumbnails import ThumbnailCache
from tests.fakes import FakeClip, FakeProject, FakeResolve, FakeTimeline


class GalleryAlbum:
    def ExportStills(self, stills, folder, prefix, image_format):
        Path(folder, prefix + ".png").write_bytes(b"png")
        return image_format == "png" and bool(stills)


class Gallery:
    def GetCurrentStillAlbum(self):
        return GalleryAlbum()


class GalleryTimeline(FakeTimeline):
    def GrabStill(self):
        return object()


class GalleryProject(FakeProject):
    def GetGallery(self):
        return Gallery()


class FailurePathTests(unittest.TestCase):
    def test_thumbnail_export_failure_restores_playhead(self):
        timeline = FakeTimeline()
        resolve = FakeResolve(FakeProject(timeline, export=False))
        original = timeline.GetCurrentTimecode()
        with tempfile.TemporaryDirectory() as folder:
            result = ThumbnailCache(ResolveContextService(resolve), folder).generate(timeline, 124, "key", 24)
        self.assertFalse(result.success)
        self.assertEqual(timeline.GetCurrentTimecode(), original)

    def test_still_capture_reports_missing_project_and_timeline(self):
        with self.assertRaises(StillError):
            StillService(FakeResolve(None), ResolveContextService(FakeResolve(None))).capture_current_frame()
        resolve = FakeResolve(FakeProject(None))
        with self.assertRaises(StillError):
            StillService(resolve, ResolveContextService(resolve)).capture_current_frame()

    def test_gallery_fallback_captures_when_direct_export_fails(self):
        timeline = GalleryTimeline()
        project = GalleryProject(timeline, export=False)
        resolve = FakeResolve(project)
        service = StillService(resolve, ResolveContextService(resolve))
        try:
            context = service.capture_current_frame()
            self.assertEqual(context["timeline_name"], "Timeline")
            self.assertTrue(service.preview_path.is_file())
        finally:
            service.cleanup_preview()

    def test_partial_metadata_batch_failure_is_reported_per_clip(self):
        good = FakeClip("good", "Good", {"Scene": "1"})
        bad = FakeClip("bad", "Bad", {"Scene": "1"}, set_metadata=False)
        records = [ClipRecord(item.identity, item, name=item.name, metadata=dict(item.metadata)) for item in (good, bad)]
        service = MetadataService()
        preview = service.preview_batch(records, "Scene", "Set", "2")
        result = service.apply_preview(preview)
        self.assertFalse(result.success)
        self.assertEqual((result.changed, result.failed), (1, 1))
        self.assertIn("Bad", result.errors[0])

    def test_stale_rename_target_blocks_undo_and_keeps_history(self):
        history = OperationHistory()
        service = RenameService(history)
        clip = FakeClip("clip", "Before")
        record = ClipRecord("clip", clip, name="Before")
        result = service.apply_preview(service.preview([record], template="After"))
        self.assertTrue(result.success)
        service._clips.clear()
        undone = history.undo()
        self.assertFalse(undone.success)
        self.assertIsNotNone(history.peek())


if __name__ == "__main__":
    unittest.main()
