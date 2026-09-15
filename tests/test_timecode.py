import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from meher_resolve_hub.timecode import TimecodeError, clamp_frame, frames_to_timecode, nudge_frame, timecode_to_frames


class TimecodeTests(unittest.TestCase):
    def test_round_trip_non_drop(self):
        for frame in (0, 1, 23, 24, 86401):
            self.assertEqual(timecode_to_frames(frames_to_timecode(frame, 24), 24), frame)

    def test_drop_frame_known_hour_and_round_trip(self):
        self.assertEqual(timecode_to_frames("01:00:00;00", 29.97), 107892)
        self.assertEqual(frames_to_timecode(107892, 29.97, drop_frame=True), "01:00:00;00")

    def test_timeline_start_offset(self):
        self.assertEqual(timecode_to_frames("01:00:01:00", 24, "01:00:00:00"), 24)
        self.assertEqual(frames_to_timecode(24, 24, "01:00:00:00"), "01:00:01:00")

    def test_invalid_drop_rate_is_rejected(self):
        with self.assertRaises(TimecodeError): timecode_to_frames("00:01:00;00", 24)

    def test_nudge_and_clamp(self):
        self.assertEqual(nudge_frame(5, -10, 0, 100), 0)
        self.assertEqual(clamp_frame(110, 0, 100), 100)


if __name__ == "__main__": unittest.main()
