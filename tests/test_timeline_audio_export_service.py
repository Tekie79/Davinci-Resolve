import tempfile
import unittest
import wave
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from meher_resolve_hub.resolve_context import ResolveContextService
from meher_resolve_hub.services.timeline_audio_export_service import (
    TimelineAudioExportService,
    DEFAULT_RENDER_PRESET,
)
from tests.fakes import FakeMediaPool, FakeFolder, FakeResolve


class SelectTimeline:
    def GetName(self): return "YSEW_EP01_SC04_RESTAURANT_SELECT"
    def GetUniqueId(self): return "select-timeline"
    def GetStartFrame(self): return 100
    def GetEndFrame(self): return 200
    def GetSettings(self): return {"timelineFrameRate": "24"}


class RenderProject:
    def __init__(self, preset_available=True):
        self.timeline = SelectTimeline()
        self.pool = FakeMediaPool(FakeFolder())
        self.current = {"format": "QuickTime", "codec": "H264"}
        self.mode = 1
        self.settings = {}
        self.job_id = "job-1"
        self.deleted = []
        self.preset_available = preset_available
        self.loaded_preset = ""

    def GetName(self): return "Project"
    def GetUniqueId(self): return "project"
    def GetCurrentTimeline(self): return self.timeline
    def GetMediaPool(self): return self.pool
    def GetSettings(self): return {"timelineFrameRate": "24"}

    def LoadRenderPreset(self, name):
        if self.preset_available and name == DEFAULT_RENDER_PRESET:
            self.loaded_preset = name
            self.current = {"format": "MP3", "codec": "mp3"}
            return True
        return False

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
        stem = self.settings["CustomName"]
        if str(self.current.get("format", "")).lower() == "mp3":
            (target / (stem + ".mp3")).write_bytes(b"ID3" + b"x" * 200)
        else:
            path = target / (stem + ".wav")
            with wave.open(str(path), "wb") as writer:
                writer.setnchannels(1)
                writer.setsampwidth(2)
                writer.setframerate(int(self.settings.get("AudioSampleRate", 16000)))
                writer.writeframes(b"\x00\x00" * 1000)
        return True

    def IsRenderingInProgress(self): return False
    def GetRenderJobStatus(self, job_id):
        return {"JobStatus": "Complete", "CompletionPercentage": 100}
    def DeleteRenderJob(self, job_id):
        self.deleted.append(job_id)
        return True


class FakeResolveWithRender(FakeResolve):
    pass


class TimelineAudioExportTests(unittest.TestCase):
    def service(self, project):
        return TimelineAudioExportService(
            ResolveContextService(FakeResolveWithRender(project))
        )

    def test_codex_mp3_preset_is_primary_and_named_from_select_timeline(self):
        project = RenderProject(preset_available=True)
        previous = dict(project.current)

        with tempfile.TemporaryDirectory() as folder:
            result = self.service(project).export_select_timeline_audio(
                output_dir=folder
            )

            self.assertTrue(result.success)
            self.assertEqual(Path(result.path).name, "YSEW_EP01_SC04_RESTAURANT_SELECT_mp3.mp3")
            self.assertEqual(result.details["analysis_format"], "mp3")
            self.assertFalse(result.details["used_wav_fallback"])
            self.assertEqual(result.details["render_preset"], "Codex_Mp3")
            self.assertEqual(result.details["directory_role"], "explicit")
            self.assertTrue(result.details["persistent"])
            self.assertTrue(Path(result.path).is_file())
            self.assertEqual(project.current, previous)
            self.assertEqual(project.mode, 1)
            self.assertIn("job-1", project.deleted)
            self.assertFalse(project.settings["ExportVideo"])
            self.assertTrue(project.settings["ExportAudio"])

    def test_missing_preset_uses_wav_fallback(self):
        project = RenderProject(preset_available=False)
        previous = dict(project.current)

        with tempfile.TemporaryDirectory() as folder:
            result = self.service(project).export_select_timeline_audio(
                output_dir=folder
            )

            self.assertTrue(result.success)
            self.assertEqual(Path(result.path).name, "YSEW_EP01_SC04_RESTAURANT_SELECT_mp3.wav")
            self.assertEqual(result.details["analysis_format"], "wav")
            self.assertTrue(result.details["used_wav_fallback"])
            self.assertTrue(any("Codex_Mp3" in value for value in result.warnings))
            self.assertEqual(project.current, previous)
            self.assertEqual(project.mode, 1)

    def test_oversize_mp3_uses_chunkable_wav_fallback(self):
        project = RenderProject(preset_available=True)

        with tempfile.TemporaryDirectory() as folder:
            result = self.service(project).export_select_timeline_audio(
                output_dir=folder,
                max_direct_upload_bytes=8,
            )

            self.assertTrue(result.success)
            self.assertEqual(result.details["analysis_format"], "wav")
            self.assertTrue(result.details["used_wav_fallback"])
            self.assertTrue(any("larger" in value for value in result.warnings))

    def test_unavailable_primary_directory_uses_fallback_directory(self):
        project = RenderProject(preset_available=True)

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            invalid_primary = root / "not-a-directory"
            invalid_primary.write_text("file", encoding="utf-8")
            fallback = root / "fallback"

            result = self.service(project).export_select_timeline_audio(
                primary_output_dir=invalid_primary,
                fallback_output_dir=fallback,
            )

            self.assertTrue(result.success)
            self.assertEqual(result.details["directory_role"], "fallback")
            self.assertEqual(Path(result.path).parent, fallback)
            self.assertTrue(any("Primary" in value for value in result.warnings))

    def test_explicit_wav_mode_skips_mp3_preset(self):
        project = RenderProject(preset_available=True)

        with tempfile.TemporaryDirectory() as folder:
            result = self.service(project).export_select_timeline_audio(
                output_dir=folder,
                preferred_format="wav",
            )

            self.assertTrue(result.success)
            self.assertEqual(result.details["analysis_format"], "wav")
            self.assertEqual(project.loaded_preset, "")

    def test_non_select_timeline_is_rejected(self):
        project = RenderProject()
        project.timeline.GetName = lambda: "PROGRAM_ROUGH_CUT"
        result = self.service(project).export_select_timeline_audio()
        self.assertFalse(result.success)
        self.assertIn("not a Select timeline", result.errors[0])


if __name__ == "__main__":
    unittest.main()
