import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from meher_resolve_hub.services.keyword_clip_rename_service import (
    KeywordClipRenameService,
    parse_keywords,
)
from meher_resolve_hub.services.metadata_service import MetadataService
from meher_resolve_hub.services.rename_service import RenameService
from tests.fakes import FakeClip


class KeywordClipRenameTests(unittest.TestCase):
    def records(self, clips):
        return MetadataService().build_records(clips)

    def test_parse_key_value_keywords(self):
        parsed = parse_keywords(
            "Name=Mike; ShotType=Medium Close Up; Frames=103245-103612"
        )
        self.assertEqual(parsed.subject, "Mike")
        self.assertEqual(parsed.shot_type, "MCU")
        self.assertEqual(parsed.frame_start, 103245)
        self.assertEqual(parsed.frame_end, 103612)

    def test_parse_aliases_and_explicit_take(self):
        parsed = parse_keywords(
            "Character: Sam | Shot: CU | FrameStart: 0 | FrameEnd: 44 | Take: T3"
        )
        self.assertEqual(parsed.subject, "Sam")
        self.assertEqual(parsed.shot_type, "CU")
        self.assertEqual(parsed.frame_start, 0)
        self.assertEqual(parsed.frame_end, 44)
        self.assertEqual(parsed.explicit_take, 3)

    def test_compact_keywords(self):
        parsed = parse_keywords("Mike, MCU, 120-180")
        self.assertEqual(
            (parsed.subject, parsed.shot_type, parsed.frame_start, parsed.frame_end),
            ("Mike", "MCU", 120, 180),
        )

    def test_two_shot_subject_is_compacted(self):
        parsed = parse_keywords("Character=Mike+Sam; ShotType=2 Shot")
        self.assertEqual(parsed.subject, "MikeSam")
        self.assertEqual(parsed.shot_type, "2SHOT")

    def test_missing_shot_type_requires_review(self):
        record = self.records(
            [FakeClip("1", "A001", {"Keywords": "Character=Mike"})]
        )[0]
        preview = KeywordClipRenameService().preview([record])
        change = preview.changes[0]
        self.assertEqual(change.status, "REVIEW_REQUIRED")
        self.assertEqual(change.after, "A001")

    def test_frames_order_take_numbers(self):
        records = self.records([
            FakeClip("1", "Later", {"Keywords": "Name=Mike; ShotType=MCU; Frames=200-220"}),
            FakeClip("2", "Earlier", {"Keywords": "Name=Mike; ShotType=MCU; Frames=100-120"}),
        ])
        preview = KeywordClipRenameService().preview(records)
        values = {change.before: change.after for change in preview.changes}
        self.assertEqual(values["Earlier"], "Mike_MCU_T01")
        self.assertEqual(values["Later"], "Mike_MCU_T02")

    def test_timeline_order_hint_used_when_frames_missing(self):
        records = self.records([
            FakeClip("1", "Later", {"Keywords": "Name=Mike; ShotType=CU"}),
            FakeClip("2", "Earlier", {"Keywords": "Name=Mike; ShotType=CU"}),
        ])
        preview = KeywordClipRenameService().preview(
            records,
            order_hints={"1": 200, "2": 100},
        )
        values = {change.before: change.after for change in preview.changes}
        self.assertEqual(values["Earlier"], "Mike_CU_T01")
        self.assertEqual(values["Later"], "Mike_CU_T02")

    def test_explicit_take_is_reserved(self):
        records = self.records([
            FakeClip("1", "Explicit", {"Keywords": "Name=Mike; ShotType=MCU; Take=2"}),
            FakeClip("2", "Auto", {"Keywords": "Name=Mike; ShotType=MCU"}),
        ])
        preview = KeywordClipRenameService().preview(records)
        values = {change.before: change.after for change in preview.changes}
        self.assertEqual(values["Explicit"], "Mike_MCU_T02")
        self.assertEqual(values["Auto"], "Mike_MCU_T01")

    def test_apply_renames_resolve_label_not_file_path(self):
        clip = FakeClip(
            "1",
            "A001.MOV",
            {"Keywords": "Name=Mike; ShotType=MCU"},
            {"File Path": "/Volumes/Camera/A001.MOV"},
        )
        records = self.records([clip])
        service = KeywordClipRenameService(RenameService())
        preview = service.preview(records)
        result = service.apply_preview(preview)
        self.assertTrue(result.success)
        self.assertEqual(clip.GetName(), "Mike_MCU_T01")
        self.assertEqual(clip.GetClipProperty("File Path"), "/Volumes/Camera/A001.MOV")

    def test_blocker_prevents_partial_apply(self):
        clips = [
            FakeClip("1", "A", {"Keywords": "Name=Mike; ShotType=MCU"}),
            FakeClip("2", "B", {"Keywords": "Name=Sam"}),
        ]
        records = self.records(clips)
        service = KeywordClipRenameService(RenameService())
        preview = service.preview(records)
        result = service.apply_preview(preview)
        self.assertFalse(result.success)
        self.assertEqual(clips[0].GetName(), "A")
        self.assertEqual(clips[1].GetName(), "B")


if __name__ == "__main__":
    unittest.main()
