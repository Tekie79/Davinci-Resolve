import tempfile
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from meher_resolve_hub.history import OperationHistory
from meher_resolve_hub.services.metadata_service import MetadataService, metadata_operation
from meher_resolve_hub.services.rename_service import RenameService, render_template, transform_name
from tests.fakes import FakeClip


class MetadataRenameTests(unittest.TestCase):
    def records(self, clips, history=None): return MetadataService(history).build_records(clips)

    def test_metadata_operations(self):
        self.assertEqual(metadata_operation("A", "Append", "B"), "AB")
        self.assertEqual(metadata_operation("ABC", "Find / Replace", "B", "x"), "AxC")
        self.assertEqual(metadata_operation("A", "Clear", ""), "")

    def test_metadata_preview_fill_blanks_and_verified_apply(self):
        service = MetadataService(); records = service.build_records([FakeClip("1", "One", {"Scene": ""}), FakeClip("2", "Two", {"Scene": "9"})])
        preview = service.preview_batch(records, "Scene", "Set", "12", blanks_only=True)
        self.assertEqual((preview.changed, preview.unchanged), (1, 1))
        result = service.apply_preview(preview)
        self.assertTrue(result.success); self.assertEqual(records[0].metadata["Scene"], "12"); self.assertEqual(records[1].metadata["Scene"], "9")

    def test_metadata_silent_failure_is_reported(self):
        service = MetadataService(); record = service.build_records([FakeClip("1", "One", {"Scene": "1"}, set_metadata=False)])[0]
        result = service.set_field(record, "Scene", "2")
        self.assertFalse(result.success); self.assertEqual(result.failed, 1)

    def test_csv_export_and_import_preview(self):
        service = MetadataService(); record = service.build_records([FakeClip("1", "One", {"Scene": "1"})])[0]
        with tempfile.TemporaryDirectory() as folder:
            path = service.export_csv([record], Path(folder) / "metadata.csv", ["Scene"])
            text = path.read_text(encoding="utf-8-sig").replace(",1", ",2")
            path.write_text(text, encoding="utf-8-sig")
            preview = service.preview_csv_import([record], path)
            self.assertEqual(preview.changes[0].after, "2")

    def test_template_missing_tokens_and_numbering(self):
        value, missing = render_template("{Scene}_{Index}_{Take}", {"Scene": "12", "Index": "1", "Take": ""}, 7, 3)
        self.assertEqual(value, "12_007_"); self.assertEqual(missing, ["Take"])

    def test_rename_conflicts_and_transformations(self):
        records = self.records([FakeClip("1", "A", {"Scene": "12"}), FakeClip("2", "B", {"Scene": "12"})])
        preview = RenameService().preview(records, "{Scene}")
        self.assertEqual([item.status for item in preview.changes], ["Conflict", "Conflict"])
        self.assertEqual(transform_name("A  B", prefix="x_", whitespace=True, case="Upper"), "X_A_B")

    def test_rename_apply_and_undo(self):
        history = OperationHistory(); service = MetadataService().build_records([FakeClip("1", "Old")]); rename = RenameService(history)
        result = rename.apply_preview(rename.preview(service, "New_{Index}"))
        self.assertTrue(result.success); self.assertEqual(service[0].media_pool_item.GetName(), "New_1")
        undo = history.undo(); self.assertTrue(undo.success); self.assertEqual(service[0].media_pool_item.GetName(), "Old")


if __name__ == "__main__": unittest.main()
