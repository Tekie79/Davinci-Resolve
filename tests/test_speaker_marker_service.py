import json
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from meher_resolve_hub.resolve_context import ResolveContextService
from meher_resolve_hub.services.speaker_marker_service import SpeakerMarkerService
from tests.fakes import FakeClip, FakeProject, FakeResolve, FakeTimeline


class MarkerTimelineItem:
    def __init__(self, identity, name, start, duration):
        self.identity = identity
        self.name = name
        self.start = start
        self.duration = duration
        self.markers = {}
        self.clip = FakeClip("media-" + identity, name)

    def GetUniqueId(self): return self.identity
    def GetName(self): return self.name
    def GetMediaPoolItem(self): return self.clip
    def GetStart(self): return self.start
    def GetEnd(self): return self.start + self.duration
    def GetDuration(self): return self.duration
    def GetMarkers(self): return dict(self.markers)
    def GetMarkerCustomData(self, frame): return self.markers.get(frame, {}).get("customData", "")

    def AddMarker(self, frame, color, name, note, duration, custom_data=""):
        if frame in self.markers:
            return False
        self.markers[int(frame)] = {
            "color": color,
            "name": name,
            "note": note,
            "duration": int(duration),
            "customData": custom_data,
        }
        return True

    def DeleteMarkerAtFrame(self, frame):
        if int(frame) not in self.markers:
            return False
        del self.markers[int(frame)]
        return True


class SelectTimeline(FakeTimeline):
    def __init__(self, items):
        super().__init__(items=items)
        self.items = list(items)

    def GetName(self): return "YSEW_EP01_SC04_RESTAURANT_SELECT"
    def GetStartFrame(self): return 100
    def GetEndFrame(self): return 200
    def GetTrackCount(self, track_type): return 1 if track_type == "video" else 0
    def GetItemListInTrack(self, track_type, index):
        return list(self.items) if track_type == "video" and index == 1 else []


class SpeakerMarkerServiceTests(unittest.TestCase):
    def setUp(self):
        self.a = MarkerTimelineItem("a", "Mike_MCU_T01", 100, 50)
        self.b = MarkerTimelineItem("b", "Sam_CU_T02", 150, 50)
        self.timeline = SelectTimeline([self.a, self.b])
        self.service = SpeakerMarkerService(
            ResolveContextService(FakeResolve(FakeProject(self.timeline)))
        )
        self.colors = {"Mike": "Blue", "Sam": "Yellow"}

    def test_apply_creates_clip_relative_ranges_and_preserves_manual_marker(self):
        self.a.AddMarker(2, "Green", "Strong Moment", "", 1, "")
        result = self.service.analyze_select_speakers_and_mark(
            segments=[
                {"speaker": "Mike", "start_frame": 110, "end_frame": 120},
                {"speaker": "Sam", "start_frame": 155, "end_frame": 165},
            ],
            speaker_colors=self.colors,
        )
        self.assertTrue(result.success)
        self.assertEqual(self.a.markers[10]["name"], "DIALOGUE — Mike")
        self.assertEqual(self.a.markers[10]["color"], "Blue")
        self.assertEqual(self.a.markers[10]["duration"], 10)
        self.assertEqual(self.b.markers[5]["name"], "DIALOGUE — Sam")
        self.assertEqual(self.b.markers[5]["color"], "Yellow")
        self.assertEqual(self.b.markers[5]["duration"], 10)
        self.assertEqual(self.a.markers[2]["name"], "Strong Moment")

    def test_cross_clip_turn_is_split_at_clip_boundary(self):
        result = self.service.analyze_select_speakers_and_mark(
            segments=[{"speaker": "Mike", "start_frame": 145, "end_frame": 155}],
            speaker_colors=self.colors,
        )
        self.assertTrue(result.success)
        self.assertEqual(self.a.markers[45]["duration"], 5)
        self.assertEqual(self.b.markers[0]["duration"], 5)
        self.assertEqual(self.a.markers[45]["name"], "DIALOGUE — Mike")
        self.assertEqual(self.b.markers[0]["name"], "DIALOGUE — Mike")

    def test_short_same_speaker_pause_merges(self):
        result = self.service.analyze_select_speakers_and_mark(
            segments=[
                {"speaker": "Mike", "start_frame": 110, "end_frame": 120},
                {"speaker": "Mike", "start_frame": 125, "end_frame": 130},
            ],
            speaker_colors=self.colors,
            merge_gap_ms=350,
        )
        self.assertTrue(result.success)
        self.assertEqual(self.a.markers[10]["duration"], 20)
        generated = [m for m in self.a.markers.values() if m["name"].startswith("DIALOGUE")]
        self.assertEqual(len(generated), 1)

    def test_rerun_is_idempotent(self):
        segments = [{"speaker": "Mike", "start_frame": 110, "end_frame": 120}]
        first = self.service.analyze_select_speakers_and_mark(
            segments=segments, speaker_colors=self.colors
        )
        second = self.service.analyze_select_speakers_and_mark(
            segments=segments, speaker_colors=self.colors
        )
        self.assertTrue(first.success)
        self.assertTrue(second.success)
        self.assertEqual(second.unchanged, 1)
        self.assertEqual(len(self.a.markers), 1)

    def test_manual_collision_stops_before_mutation(self):
        self.a.AddMarker(10, "Red", "Manual", "Keep me", 3, "")
        result = self.service.analyze_select_speakers_and_mark(
            segments=[{"speaker": "Mike", "start_frame": 110, "end_frame": 120}],
            speaker_colors=self.colors,
        )
        self.assertFalse(result.success)
        self.assertIn("Manual marker collision", result.errors[0])
        self.assertEqual(self.a.markers[10]["name"], "Manual")
        self.assertEqual(len(self.a.markers), 1)

    def test_preview_does_not_write(self):
        result = self.service.analyze_select_speakers_and_mark(
            segments=[{"speaker": "Mike", "start_frame": 110, "end_frame": 120}],
            speaker_colors=self.colors,
            mode="preview",
        )
        self.assertTrue(result.success)
        self.assertEqual(result.changed, 1)
        self.assertEqual(self.a.markers, {})

    def test_exact_start_overlap_becomes_one_overlap_marker(self):
        result = self.service.analyze_select_speakers_and_mark(
            segments=[
                {"speaker": "Mike", "start_frame": 110, "end_frame": 120},
                {"speaker": "Sam", "start_frame": 110, "end_frame": 118},
            ],
            speaker_colors=self.colors,
        )
        self.assertTrue(result.success)
        self.assertEqual(self.a.markers[10]["name"], "OVERLAP — Mike + Sam")
        self.assertEqual(self.a.markers[10]["color"], "Fuchsia")
        self.assertEqual(self.a.markers[10]["duration"], 10)

    def test_unsupported_color_falls_back_to_supported_unknown_color(self):
        result = self.service.analyze_select_speakers_and_mark(
            segments=[{"speaker": "Sam", "start_frame": 155, "end_frame": 165}],
            speaker_colors={"Sam": "Orange"},
        )
        self.assertTrue(result.success)
        self.assertEqual(self.b.markers[5]["color"], "Cream")
        self.assertTrue(any("Unsupported marker color" in value for value in result.warnings))

    def test_hybrid_evidence_is_preserved_in_custom_data(self):
        result = self.service.analyze_select_speakers_and_mark(
            segments=[{
                "speaker": "Mike",
                "start_frame": 110,
                "end_frame": 120,
                "source": "hybrid-audio-visual",
                "audio_confirmation": True,
                "visual_confirmation": True,
                "speaker_visibility": "onscreen",
                "evidence_status": "CONFIRMED",
            }],
            speaker_colors=self.colors,
        )
        self.assertTrue(result.success)
        data = json.loads(self.a.markers[10]["customData"])
        self.assertTrue(data["audio_confirmation"])
        self.assertTrue(data["visual_confirmation"])
        self.assertEqual(data["speaker_visibility"], "onscreen")
        self.assertEqual(data["evidence_status"], "CONFIRMED")
        self.assertIn("Visibility: onscreen", self.a.markers[10]["note"])

    def test_visibility_change_prevents_same_speaker_merge(self):
        result = self.service.analyze_select_speakers_and_mark(
            segments=[
                {
                    "speaker": "Mike",
                    "start_frame": 110,
                    "end_frame": 120,
                    "audio_confirmation": True,
                    "speaker_visibility": "onscreen",
                    "evidence_status": "CONFIRMED",
                },
                {
                    "speaker": "Mike",
                    "start_frame": 121,
                    "end_frame": 130,
                    "audio_confirmation": True,
                    "speaker_visibility": "offscreen",
                    "evidence_status": "AUDIO_CONFIRMED",
                },
            ],
            speaker_colors=self.colors,
            merge_gap_ms=350,
        )
        self.assertTrue(result.success)
        generated = [
            marker for marker in self.a.markers.values()
            if marker["name"].startswith("DIALOGUE")
        ]
        self.assertEqual(len(generated), 2)

    def test_missing_analysis_backend_is_explicit(self):
        result = self.service.analyze_select_speakers_and_mark(
            segments=None, speaker_colors=self.colors
        )
        self.assertFalse(result.success)
        self.assertIn("Speaker analysis backend is unavailable", result.errors[0])

    def test_analyzer_adapter_is_supported(self):
        class Analyzer:
            def analyze(self, timeline, fps):
                self.timeline = timeline
                self.fps = fps
                return [{"speaker": "Mike", "start_frame": 110, "end_frame": 120}]

        analyzer = Analyzer()
        result = self.service.analyze_select_speakers_and_mark(
            analyzer=analyzer, speaker_colors=self.colors
        )
        self.assertTrue(result.success)
        self.assertIs(analyzer.timeline, self.timeline)
        self.assertEqual(analyzer.fps, 24.0)
        self.assertIn(10, self.a.markers)


if __name__ == "__main__":
    unittest.main()
