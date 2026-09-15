import hashlib
import tempfile
import unittest
from pathlib import Path

from meher_resolve_hub.history import OperationHistory
from meher_resolve_hub.navigation import NavigationEngine
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
    def test_navigation_waits_for_delayed_none_returning_playhead(self):
        class DelayedTimeline(FakeTimeline):
            def __init__(self):
                super().__init__()
                self.pending = None
                self.polls = 0

            def SetCurrentTimecode(self, value):
                self.pending = str(value)
                self.polls = 0
                return None

            def GetCurrentTimecode(self):
                if self.pending is not None:
                    self.polls += 1
                    if self.polls >= 2:
                        self.timecode = self.pending
                        self.pending = None
                return self.timecode

        timeline = DelayedTimeline()
        engine = NavigationEngine(ResolveContextService(FakeResolve(FakeProject(timeline))))
        result = engine.set_playhead("01:00:01:00")
        self.assertTrue(result.success)
        self.assertEqual(timeline.GetCurrentTimecode(), "01:00:01:00")

    def test_thumbnail_export_failure_restores_playhead(self):
        timeline = FakeTimeline()
        resolve = FakeResolve(FakeProject(timeline, export=False))
        original = timeline.GetCurrentTimecode()
        with tempfile.TemporaryDirectory() as folder:
            result = ThumbnailCache(ResolveContextService(resolve), folder).generate(timeline, 124, "key", 24)
        self.assertFalse(result.success)
        self.assertEqual(timeline.GetCurrentTimecode(), original)

    def test_thumbnail_waits_for_each_marker_frame_before_export(self):
        class DelayedTimeline(FakeTimeline):
            def __init__(self):
                super().__init__()
                self.pending = None
                self.polls = 0

            def SetCurrentTimecode(self, value):
                self.pending = str(value)
                self.polls = 0
                return True

            def GetCurrentTimecode(self):
                if self.pending is not None:
                    self.polls += 1
                    if self.polls >= 2:
                        self.timecode = self.pending
                        self.pending = None
                return self.timecode

        class FrameProject(FakeProject):
            def ExportCurrentFrameAsStill(self, path):
                Path(path).write_text(self.timeline.GetCurrentTimecode(), encoding="utf-8")
                return True

        timeline = DelayedTimeline()
        project = FrameProject(timeline)
        resolve = FakeResolve(project)
        with tempfile.TemporaryDirectory() as folder:
            cache = ThumbnailCache(ResolveContextService(resolve), folder, settle_delay=0)
            first = cache.generate(timeline, 124, "first", 24)
            second = cache.generate(timeline, 148, "second", 24)
            self.assertTrue(first.success)
            self.assertTrue(second.success)
            self.assertNotEqual(Path(first.details[0]["path"]).read_text(), Path(second.details[0]["path"]).read_text())

    def test_thumbnail_accepts_none_return_when_resolve_writes_the_file(self):
        class NoneReturningProject(FakeProject):
            def ExportCurrentFrameAsStill(self, path):
                Path(path).write_bytes(b"png")
                return None

        timeline = FakeTimeline()
        resolve = FakeResolve(NoneReturningProject(timeline))
        with tempfile.TemporaryDirectory() as folder:
            result = ThumbnailCache(ResolveContextService(resolve), folder, settle_delay=0).generate(timeline, 124, "key", 24)
        self.assertTrue(result.success)
        self.assertEqual(result.changed, 1)

    def test_thumbnail_export_exception_is_reported_and_restores_playhead(self):
        class RaisingProject(FakeProject):
            def ExportCurrentFrameAsStill(self, path):
                raise RuntimeError("export unavailable")

        timeline = FakeTimeline()
        original = timeline.GetCurrentTimecode()
        resolve = FakeResolve(RaisingProject(timeline))
        with tempfile.TemporaryDirectory() as folder:
            result = ThumbnailCache(ResolveContextService(resolve), folder, settle_delay=0).generate(timeline, 124, "key", 24)
        self.assertFalse(result.success)
        self.assertIn("export unavailable", result.errors[0])
        self.assertEqual(timeline.GetCurrentTimecode(), original)

    def test_thumbnail_cache_version_invalidates_bad_captures(self):
        timeline = FakeTimeline()
        cache = ThumbnailCache(ResolveContextService(FakeResolve(FakeProject(timeline))))
        key = cache.cache_key("project", "timeline", "marker", 10, "Blue")
        legacy = hashlib.sha1("project|timeline|marker|10|Blue".encode("utf-8")).hexdigest()
        self.assertNotEqual(key, legacy)
        self.assertEqual(cache.size, (960, 540))

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
