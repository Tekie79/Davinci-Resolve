import inspect
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from meher_resolve_hub import mcp_server
from tests.fakes import FakeFolder, FakeMediaPool, FakeProject, FakeResolve, FakeTimeline, FakeTimelineItem, FakeClip


class MCPServerTests(unittest.TestCase):
    def test_scene_tokens(self):
        self.assertIn("SC04", mcp_server._scene_tokens("4"))
        self.assertIn("SC4.2", mcp_server._scene_tokens("4.2"))

    def test_voice_references_only_use_requested_characters(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "Mike.mp3").write_bytes(b"mike")
            (root / "Sam.wav").write_bytes(b"sam")
            (root / "CJ.mp3").write_bytes(b"cj")

            refs, warnings = mcp_server._voice_references(
                ["Mike", "Sam"], reference_dir=folder
            )

            self.assertEqual(set(refs), {"Mike", "Sam"})
            self.assertNotIn("CJ", refs)
            self.assertEqual(warnings, [])

    def test_voice_reference_limit_is_four(self):
        with self.assertRaisesRegex(RuntimeError, "maximum of four"):
            mcp_server._voice_references(
                ["A", "B", "C", "D", "E"], reference_dir="/tmp"
            )

    def test_openai_key_is_not_mcp_tool_argument(self):
        signature = inspect.signature(mcp_server.analyze_select_speakers_and_mark)
        self.assertNotIn("openai_api_key", signature.parameters)
        self.assertNotIn("api_key", signature.parameters)

    def test_speaker_mcp_exposes_codex_mp3_options(self):
        signature = inspect.signature(mcp_server.analyze_select_speakers_and_mark)
        self.assertIn("audio_render_preset", signature.parameters)
        self.assertIn("audio_primary_dir", signature.parameters)
        self.assertIn("audio_fallback_dir", signature.parameters)

    def test_visual_and_precomputed_speaker_tools_are_exposed(self):
        visual = inspect.signature(mcp_server.export_active_speaker_visual_samples)
        apply_segments = inspect.signature(mcp_server.apply_speaker_segments_to_clips)
        self.assertIn("sample_fps", visual.parameters)
        self.assertIn("segments", apply_segments.parameters)
        self.assertIn("mode", apply_segments.parameters)

    def test_keyword_rename_tool_has_no_filesystem_rename_argument(self):
        signature = inspect.signature(mcp_server.rename_clips_from_keywords)
        self.assertIn("source", signature.parameters)
        self.assertIn("mode", signature.parameters)
        self.assertNotIn("file_path", signature.parameters)
        self.assertNotIn("rename_files", signature.parameters)

    def test_find_reference_bin_by_path(self):
        ref = FakeFolder("CODEX_REF")
        stills = FakeFolder("STILLS", children=[ref])
        media = FakeFolder("01_MEDIA", children=[stills])
        root = FakeFolder("Master", children=[media])
        pool = FakeMediaPool(root)
        found = mcp_server._find_bin_by_path(
            pool, "Master/01_MEDIA/STILLS/CODEX_REF"
        )
        self.assertIs(found, ref)

    def test_active_speaker_visual_export_produces_temporal_samples(self):
        import asyncio
        from unittest.mock import patch

        clip = FakeClip("media-1", "Mike_MCU_T01", {"Keywords": "Character=Mike"})
        item = FakeTimelineItem(clip, start=100, end=124)
        timeline = FakeTimeline([item])
        timeline.GetName = lambda: "YSEW_EP01_SC04_SELECT"
        project = FakeProject(timeline)
        resolve = FakeResolve(project)

        with patch.object(mcp_server, "_resolve", return_value=resolve):
            result = asyncio.run(
                mcp_server.export_active_speaker_visual_samples(
                    sample_fps=6,
                    max_frames_per_clip=6,
                    max_clips=1,
                )
            )

        self.assertEqual(result["timeline"], "YSEW_EP01_SC04_SELECT")
        self.assertEqual(len(result["clips"]), 1)
        samples = result["clips"][0]["samples"]
        self.assertGreaterEqual(len(samples), 3)
        for sample in samples:
            self.assertTrue(Path(sample["image_path"]).is_file())

        asyncio.run(
            mcp_server.cleanup_visual_analysis_frames(
                result["temporary_directory"]
            )
        )
        self.assertFalse(Path(result["temporary_directory"]).exists())

    def test_visual_cleanup_rejects_non_temp_directory(self):
        with self.assertRaisesRegex(RuntimeError, "Refusing"):
            import asyncio
            asyncio.run(mcp_server.cleanup_visual_analysis_frames("/tmp/not-owned"))


if __name__ == "__main__":
    unittest.main()
