import tempfile
import unittest
import wave
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from meher_resolve_hub.resolve_context import ResolveContextService
from meher_resolve_hub.services.timeline_audio_export_service import TimelineAudioExportService
from tests.fakes import FakeMediaPool, FakeFolder, FakeResolve


class SelectTimeline:
    def GetName(self): return "YSEW_EP01_SC04_RESTAURANT_SELECT"
    def GetUniqueId(self): return "select-timeline"
    def GetStartFrame(self): return 100
    def GetEndFrame(self): return 200
    def GetSettings(self): return {"timelineFrameRate": "24"}


class RenderProject:
    def __init__(self):
        self.timeline = SelectTimeline()
        self.pool = FakeMediaPool(FakeFolder())
        self.current = {"format": "QuickTime", "codec": "H264"}
        self.mode = 0
        self.settings = {}
        self.job_id = "job-1"
        self.deleted = []

    def GetName(self): return "Project"
    def GetUniqueId(self): return "project"
    def GetCurrentTimeline(self): return self.timeline
    def GetMediaPool(self): return self.pool
    def GetSettings(self): return {"timelineFrameRate": "24"}

    def GetRenderFormats(self): return {"Wave": "wav", "QuickTime": "mov"}
    def GetRenderCodecs(self, render_format):
        if str(render_format).lower() in ("wave", "wav"):
            return {"Linear PCM": "LinearPCM"}
        return {"H.264": "H264"}

    def GetCurrentRenderFormatAndCodec(self): return dict(self.current)

    def SetCurrentRenderFormatAndCodec(self, render_format, codec):
        if str(render_format).lower() in ("wave", "wav") and codec in ("LinearPCM", "Linear PCM"):
            self.current = {"format": render_format, "codec": codec}
            return True
        if render_format == "QuickTime" and codec == "H264":
            self.current = {"format": render_format, "codec": codec}
            return True
        return False

    def GetCurrentRenderMode(self): return self.mode
    def SetCurrentRenderMode(self, value): self.mode = int(value); return True

    def SetRenderSettings(self, settings):
        self.settings = dict(settings)
        return True

    def AddRenderJob(self): return self.job_id

    def StartRendering(self, job_id):
        if job_id != self.job_id:
            return False
        target = Path(self.settings["TargetDir"])
        target.mkdir(parents=True, exist_ok=True)
        path = target / (self.settings["CustomName"] + ".wav")
        with wave.open(str(path), "wb") as writer:
            writer.setnchannels(1)
            writer.setsampwidth(2)
            writer.setframerate(int(self.settings.get("AudioSampleRate", 16000)))
            writer.writeframes(b"\x00\x00" * 1000)
        return True

    def IsRenderingInProgress(self): return False
    def GetRenderJobStatus(self, job_id): return {"JobStatus": "Complete", "CompletionPercentage": 100}
    def DeleteRenderJob(self, job_id): self.deleted.append(job_id); return True


class FakeResolveWithRender(FakeResolve):
    pass


class TimelineAudioExportTests(unittest.TestCase):
    def test_select_audio_render_is_verified_and_previous_format_restored(self):
        project = RenderProject()
        resolve = FakeResolveWithRender(project)
        service = TimelineAudioExportService(ResolveContextService(resolve))

        with tempfile.TemporaryDirectory() as folder:
            result = service.export_select_timeline_audio(output_dir=folder, preferred_format="wav")
            self.assertTrue(result.success)
            self.assertTrue(Path(result.path).is_file())
            self.assertEqual(project.current, {"format": "QuickTime", "codec": "H264"})
            self.assertEqual(project.mode, 0)
            self.assertIn("job-1", project.deleted)
            self.assertFalse(project.settings["ExportVideo"])
            self.assertTrue(project.settings["ExportAudio"])

    def test_non_select_timeline_is_rejected(self):
        project = RenderProject()
        project.timeline.GetName = lambda: "PROGRAM_ROUGH_CUT"
        service = TimelineAudioExportService(ResolveContextService(FakeResolveWithRender(project)))
        result = service.export_select_timeline_audio()
        self.assertFalse(result.success)
        self.assertIn("not a Select timeline", result.errors[0])


if __name__ == "__main__":
    unittest.main()
