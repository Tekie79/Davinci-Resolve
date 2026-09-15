import tempfile
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from meher_resolve_hub.models.clip import ClipRecord
from meher_resolve_hub.models.marker import MarkerRecord
from meher_resolve_hub.resolve_context import ResolveContextService
from meher_resolve_hub.services.health_service import HealthService
from meher_resolve_hub.services.still_service import StillService
from tests.fakes import FakeClip, FakeFolder, FakeMediaPool, FakeProject, FakeResolve, FakeTimeline, FakeTimelineItem


class HealthStillTests(unittest.TestCase):
    def test_health_is_conservative_and_groups_real_issues(self):
        clip_a = FakeClip("a", "A.mov", {"Scene": ""}, {"File Path": "/missing/A.mov", "FPS": "29.97", "Resolution": "3840 x 2160", "Frames": "5", "Video Codec": "H.264", "Type": "Video", "Audio": "No Audio", "File Name": "A.mov"})
        clip_b = FakeClip("b", "A.mov", {"Scene": "2"}, {"File Path": "/other/A.mov", "FPS": "24", "Resolution": "1920 x 1080", "Frames": "5", "Video Codec": "ProRes", "File Name": "A.mov"})
        records = [ClipRecord(item.identity, item, name=item.name, file_path=item.properties["File Path"], metadata=item.metadata, properties=item.properties) for item in (clip_a, clip_b)]
        report = HealthService().scan(records, 24, ["1920x1080"], ["Scene"], ["ProRes"], 12, {"b"})
        categories = {item.category for item in report.issues}
        self.assertTrue({"Offline", "Frame Rate", "Resolution", "Metadata", "Codec", "Short Clip", "Audio", "Duplicate Name", "Unused"}.issubset(categories))
        self.assertIn("Missing Proxy", report.skipped_checks)

    def test_health_export_json_and_csv(self):
        report = HealthService().scan([], scope="Empty")
        with tempfile.TemporaryDirectory() as folder:
            json_path = HealthService.export(report, Path(folder) / "report.json")
            csv_path = HealthService.export(report, Path(folder) / "report.csv")
            self.assertIn('"scope": "Empty"', json_path.read_text())
            self.assertIn("category,severity", csv_path.read_text(encoding="utf-8-sig"))

    def test_health_does_not_mark_resolve_display_name_offline(self):
        clip = FakeClip("a", "A.mov", {}, {"File Path": "A.mov"})
        record = ClipRecord(clip.identity, clip, name=clip.name, file_path="A.mov", properties=clip.properties)
        report = HealthService().scan([record])
        self.assertNotIn("Offline", {item.category for item in report.issues})
        self.assertIn("Offline", report.skipped_checks)

    def test_marker_queue_and_conflicts(self):
        timeline = FakeTimeline(); project = FakeProject(timeline); service = StillService(FakeResolve(project), ResolveContextService(FakeResolve(project)))
        marker = MarkerRecord("timeline", "timeline", 0, 0, 0, 1, "Green", "Best", "", thumbnail_path="cached.png", source_object=timeline)
        queue = service.queue_from_markers([marker], "{Timeline}_{Marker}_{Index}", 24, "Project", "Timeline", timeline)
        self.assertEqual(queue[0].filename, "Timeline_Best_1.png")
        self.assertEqual(queue[0].thumbnail_path, "cached.png")
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / queue[0].filename).write_bytes(b"png"); service.detect_conflicts(queue, folder); self.assertEqual(queue[0].status, "Conflict")

    def test_batch_capture_restores_playhead(self):
        clip = FakeClip("c", "Clip", {"Scene": "1"}); item = FakeTimelineItem(clip, 100, 124); timeline = FakeTimeline([item]); project = FakeProject(timeline, FakeMediaPool(FakeFolder()))
        resolve = FakeResolve(project); service = StillService(resolve, ResolveContextService(resolve)); original = timeline.GetCurrentTimecode()
        queue = service.queue_from_timeline_items([item], "Middle", "{Clip}_{Index}", 24, "Project", "Timeline", timeline)
        with tempfile.TemporaryDirectory() as folder:
            result = service.execute_queue(queue, folder, import_to_bin=False)
            self.assertTrue(result.success); self.assertTrue(Path(queue[0].output_path).is_file()); self.assertEqual(timeline.GetCurrentTimecode(), original)

    def test_batch_capture_waits_for_each_requested_frame(self):
        class DelayedTimeline(FakeTimeline):
            def __init__(self, items):
                super().__init__(items)
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

        clip = FakeClip("c", "Clip")
        items = [FakeTimelineItem(clip, 100, 124), FakeTimelineItem(clip, 148, 172)]
        timeline = DelayedTimeline(items)
        project = FrameProject(timeline, FakeMediaPool(FakeFolder()))
        resolve = FakeResolve(project)
        service = StillService(resolve, ResolveContextService(resolve))
        queue = service.queue_from_timeline_items(items, "First", "{Index}", 24, "Project", "Timeline", timeline)
        with tempfile.TemporaryDirectory() as folder:
            result = service.execute_queue(queue, folder, import_to_bin=False)
            self.assertTrue(result.success)
            frames = [Path(item.output_path).read_text(encoding="utf-8") for item in queue]
            self.assertEqual(frames, ["01:00:00:00", "01:00:02:00"])


if __name__ == "__main__": unittest.main()
