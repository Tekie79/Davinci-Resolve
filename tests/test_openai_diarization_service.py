import tempfile
import unittest
import wave
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from meher_resolve_hub.services.openai_diarization_service import OpenAIDiarizationAnalyzer


class FakeResponse:
    def __init__(self, segments):
        self.segments = segments


def write_wav(path, seconds=1.0, sample_rate=16000):
    frames = int(seconds * sample_rate)
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate)
        writer.writeframes(b"\x00\x00" * frames)


class FakeAnalyzer(OpenAIDiarizationAnalyzer):
    def __init__(self, *args, responses=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.responses = list(responses or [])
        self.calls = 0

    def _client(self):
        return object()

    def _transcribe_chunk(self, client, path, known_names, known_refs):
        index = min(self.calls, len(self.responses) - 1)
        self.calls += 1
        return self.responses[index]


class OpenAIDiarizationAnalyzerTests(unittest.TestCase):
    def test_generic_speaker_is_marked_unknown_without_reference(self):
        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / "scene.wav"
            write_wav(audio)
            analyzer = FakeAnalyzer(
                audio,
                responses=[FakeResponse([
                    {"speaker": "A", "start": 0.1, "end": 0.7, "text": "ignored"}
                ])],
            )
            segments = analyzer.analyze(None, 24.0)
            self.assertEqual(len(segments), 1)
            self.assertEqual(segments[0]["speaker"], "UNKNOWN_A")
            self.assertEqual(segments[0]["transcript"], "")
            self.assertEqual(segments[0]["source"], "openai:gpt-4o-transcribe-diarize")

    def test_known_speaker_name_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / "scene.wav"
            reference = Path(folder) / "mike.wav"
            write_wav(audio)
            write_wav(reference)
            analyzer = FakeAnalyzer(
                audio,
                known_speaker_references={"Mike": reference},
                responses=[FakeResponse([
                    {"speaker": "Mike", "start": 0.0, "end": 0.8, "text": "hello"}
                ])],
            )
            segments = analyzer.analyze(None, 24.0)
            self.assertEqual(segments[0]["speaker"], "Mike")
            self.assertEqual(segments[0]["identity_confidence"], 1.0)

    def test_transcript_is_optional(self):
        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / "scene.wav"
            write_wav(audio)
            analyzer = FakeAnalyzer(
                audio,
                include_transcript=True,
                responses=[FakeResponse([
                    {"speaker": "A", "start": 0.0, "end": 0.8, "text": "mixed dialogue"}
                ])],
            )
            segments = analyzer.analyze(None, 24.0)
            self.assertEqual(segments[0]["transcript"], "mixed dialogue")

    def test_large_wav_is_split_below_requested_limit(self):
        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / "scene.wav"
            write_wav(audio, seconds=3.0, sample_rate=1000)
            analyzer = OpenAIDiarizationAnalyzer(
                audio,
                api_key="test",
                max_upload_bytes=1500,
                chunk_overlap_seconds=0.1,
            )
            chunks = analyzer._wav_chunks()
            self.assertGreater(len(chunks), 1)
            try:
                for chunk, _, _, _, cleanup in chunks:
                    self.assertTrue(chunk.is_file())
                    self.assertTrue(cleanup)
            finally:
                parents = set()
                for chunk, _, _, _, cleanup in chunks:
                    if cleanup:
                        parents.add(chunk.parent)
                        if chunk.exists():
                            chunk.unlink()
                for parent in parents:
                    if parent.exists():
                        parent.rmdir()


if __name__ == "__main__":
    unittest.main()
