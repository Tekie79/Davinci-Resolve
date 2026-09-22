import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from meher_resolve_hub.services.elevenlabs_diarization_service import (
    ElevenLabsDiarizationAnalyzer,
)


class ElevenLabsDiarizationTests(unittest.TestCase):
    def analyzer(self, **kwargs):
        return ElevenLabsDiarizationAnalyzer(
            audio_path="/tmp/example.mp3",
            api_key="test-key",
            **kwargs
        )

    def test_groups_contiguous_words_by_speaker(self):
        analyzer = self.analyzer(include_transcript=True)
        response = {
            "words": [
                {"type": "word", "speaker_id": "speaker_0", "start": 0.0, "end": 0.4, "text": "ሰላም"},
                {"type": "spacing", "speaker_id": "speaker_0", "start": 0.4, "end": 0.41, "text": " "},
                {"type": "word", "speaker_id": "speaker_0", "start": 0.41, "end": 0.8, "text": "ማይክ"},
                {"type": "word", "speaker_id": "speaker_1", "start": 1.0, "end": 1.3, "text": "hello"},
            ]
        }
        segments = analyzer._segments_from_words(response)
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0]["speaker"], "UNKNOWN_speaker_0")
        self.assertEqual(segments[0]["start_seconds"], 0.0)
        self.assertEqual(segments[0]["end_seconds"], 0.8)
        self.assertIn("ሰላም", segments[0]["transcript"])
        self.assertEqual(segments[1]["speaker"], "UNKNOWN_speaker_1")

    def test_speaker_library_identifier_is_preserved(self):
        analyzer = self.analyzer(use_speaker_library=True)
        response = {
            "words": [
                {"type": "word", "speaker_id": "Mike", "start": 2.0, "end": 2.5, "text": "x"},
            ]
        }
        segment = analyzer._segments_from_words(response)[0]
        self.assertEqual(segment["speaker"], "Mike")
        self.assertEqual(segment["evidence_status"], "AUDIO_CONFIRMED")
        self.assertTrue(segment["audio_confirmation"])

    def test_num_speakers_validation(self):
        analyzer = self.analyzer(num_speakers=33)
        class Dummy:
            speech_to_text = None
        with self.assertRaisesRegex(Exception, "between 1 and 32"):
            analyzer._request(Dummy())


if __name__ == "__main__":
    unittest.main()
