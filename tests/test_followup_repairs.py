"""Regression tests for the v0.3.23 follow-up; no live Resolve is required."""
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

from meher_resolve_hub.models.marker import MarkerRecord
from meher_resolve_hub.models.operation import OperationResult
from meher_resolve_hub.history import OperationHistory
from meher_resolve_hub.resolve_context import ResolveContextService
from meher_resolve_hub.services.marker_service import MarkerService
from meher_resolve_hub.services.metadata_service import MetadataService
from meher_resolve_hub.services.rename_service import RenameService, clip_tokens
from meher_resolve_hub.services.still_service import StillService
from meher_resolve_hub.services.health_service import HealthService
from meher_resolve_hub.thumbnails import ThumbnailCache
from meher_resolve_hub.ui.shell import ResolveHubShell
from meher_resolve_hub.ui.components import tree as build_tree
from tests.fakes import FakeClip, FakeProject, FakeResolve, FakeTimeline
from tests.test_ui_tree_adapter import FakeBuildTree


def marker(frame=10, name="Old", color="Blue", note="", duration=2):
    return MarkerRecord("timeline", "timeline", frame, frame, frame + duration - 1, duration, color, name, note)


def make_shell(records, search="", color="All", sort="Timecode"):
    shell = ResolveHubShell.__new__(ResolveHubShell)
    timeline = FakeTimeline()
    context = ResolveContextService(FakeResolve(FakeProject(timeline)))
    browser = FakeBuildTree()
    items = {"MarkerTree": browser, "MarkerSelectionCount": NS(Text=""), "MarkerSearch": NS(Text=search), "MarkerType": NS(CurrentText="All"), "MarkerSort": NS(CurrentText=sort)}
    shell.window = NS(GetItems=lambda: items)
    shell.ui = NS(Icon=lambda spec: spec["File"])
    shell.app = NS(context=context, markers=MarkerService(context))
    shell.workspace = "Markers"
    shell.marker_records, shell.filtered_markers = list(records), list(records)
    shell._selected_marker_frames = {records[0].start_frame} if records else set()
    shell._active_marker_frame = records[0].start_frame if records else None
    shell._marker_selection_anchor = shell._active_marker_frame
    shell._marker_state = shell._marker_state_signature("timeline", records)
    shell._populating_marker_tree = shell._syncing_marker_selection = False
    shell._loading_marker_thumbnail = shell._marker_thumbnail_dirty = False
    shell._color_selection = {"MarkerColor": color}
    shell._sync_marker_editor_fields = lambda value: None
    shell._set_marker_thumbnail = lambda *args: None
    shell._report_result = lambda *args: None
    shell._populate_tree("MarkerTree", [shell._marker_row_values(index, value) for index, value in enumerate(records)])
    shell.refreshes = 0
    def refresh(**kwargs):
        shell.refreshes += 1
        shell.filtered_markers = MarkerService.filter_markers(shell.marker_records, items["MarkerSearch"].Text, shell._color_selection["MarkerColor"], sort=items["MarkerSort"].CurrentText)
        if shell._active_marker_frame not in {value.start_frame for value in shell.filtered_markers}:
            shell._active_marker_frame = None
    shell._refresh_markers = refresh
    return shell, items


class IconControl:
    def __init__(self):
        self.icon_writes = []
        self.updates = 0
    def __setattr__(self, name, value):
        if name == "Icon":
            self.icon_writes.append(value)
        object.__setattr__(self, name, value)
    def Update(self):
        self.updates += 1


class FollowupUITests(unittest.TestCase):
    def test_thumbnail_swap_does_not_resize_tables_or_blank_twice(self):
        control = IconControl()
        shell = ResolveHubShell.__new__(ResolveHubShell)
        shell.window = NS(GetItems=lambda: {"MarkerThumb": control})
        shell.ui = NS(Icon=lambda spec: spec["File"])
        resized = []
        shell._resize_marker_thumbnail = lambda: resized.append(True)
        shell._set_marker_thumbnail("/tmp/hub-image.png")
        self.assertEqual(resized, [])
        self.assertEqual(len(control.icon_writes), 1)
        self.assertEqual(control.updates, 1)

    def test_identical_thumbnail_is_not_repainted(self):
        control = IconControl()
        shell = ResolveHubShell.__new__(ResolveHubShell)
        shell.window = NS(GetItems=lambda: {"MarkerThumb": control})
        shell.ui = NS(Icon=lambda spec: spec["File"])
        shell._resize_marker_thumbnail = lambda: None
        shell._set_marker_thumbnail("/tmp/hub-image.png")
        shell._set_marker_thumbnail("/tmp/hub-image.png")
        self.assertEqual(len(control.icon_writes), 1)

    def test_unchanged_window_geometry_does_not_reassign_column_widths(self):
        shell = ResolveHubShell.__new__(ResolveHubShell)
        shell.window = NS(Geometry=[0, 0, 1240, 780], GetItems=lambda: {"MarkerThumb": NS()})
        resized = []
        shell._resize_marker_table_columns = lambda: resized.append("marker")
        shell._resize_other_tree_columns = lambda: resized.append("other")
        shell._resize_marker_thumbnail(); shell._resize_marker_thumbnail()
        self.assertEqual(resized, ["marker", "other"])

    def test_no_horizontal_overflow_on_narrow_marker_browser(self):
        for width in (280, 390, 520, 659, 1200):
            with self.subTest(width=width):
                self.assertLessEqual(sum(ResolveHubShell._marker_table_column_widths(width)), width - 24)

    def test_marker_tree_uses_logical_selection_and_uniform_geometry(self):
        ui = NS(Tree=lambda properties: properties)
        props = build_tree(ui, "MarkerTree", ("Preview", "Name"))
        self.assertEqual(props["SelectionMode"], "NoSelection")
        self.assertTrue(props["UniformRowHeights"])
        self.assertFalse(props["WordWrap"])
        self.assertEqual(props["IconSize"], [96, 54])

    def test_click_paint_never_toggles_native_selected_flag(self):
        shell, items = make_shell([marker()])
        row = items["MarkerTree"].items[0]
        class CountSelection(type(row)):
            def __setattr__(self, name, value):
                if name == "Selected":
                    self.selection_writes += 1
                object.__setattr__(self, name, value)
        row.__class__ = CountSelection
        row.selection_writes = 0
        shell._paint_marker_rows({10})
        self.assertEqual(row.selection_writes, 0)
        self.assertFalse(shell._populating_marker_tree)

    def test_numeric_modifier_flags_preserve_multiselection(self):
        value = ResolveHubShell._marker_click_modifiers({"Modifiers": 0x02000000 | 0x10000000})
        self.assertIn("shift", value)
        self.assertIn("meta", value)

    def test_readonly_notes_preview_cannot_discard_hidden_text(self):
        original = marker(note="Line one\n" + "x" * 140)
        shell, items = make_shell([original])
        commits = []
        shell._commit_marker_update = lambda *args: commits.append(args)
        shell._restore_marker_row = lambda value: None
        row = items["MarkerTree"].items[0]
        row.Text[6] = "Truncated edit"
        shell._marker_tree_item_changed({"item": row, "column": 6})
        self.assertEqual(commits, [])
        self.assertEqual(original.note, "Line one\n" + "x" * 140)

    def test_recolor_recomputes_filter_membership(self):
        original = marker()
        shell, _ = make_shell([original], color="Blue")
        shell._sync_marker_update(original, original.copy(color="Green"))
        self.assertEqual(shell.filtered_markers, [])
        self.assertEqual(shell.refreshes, 1)

    def test_rename_recomputes_search_membership(self):
        original = marker(name="Old")
        shell, _ = make_shell([original], search="Old")
        shell._sync_marker_update(original, original.copy(name="New"))
        self.assertEqual(shell.filtered_markers, [])

    def test_move_recomputes_timecode_sort_order(self):
        first, second = marker(10), marker(20, name="Second")
        shell, _ = make_shell([first, second])
        shell._sync_marker_update(first, MarkerService.edit_range(first, move=20))
        self.assertEqual([value.start_frame for value in shell.filtered_markers], [20, 30])
        self.assertEqual(shell._active_marker_frame, 30)

    def test_rename_recomputes_alphabetical_order(self):
        first, second = marker(10, "A"), marker(20, "B")
        shell, _ = make_shell([first, second], sort="Name")
        shell._sync_marker_update(first, first.copy(name="Z"))
        self.assertEqual([value.name for value in shell.filtered_markers], ["B", "Z"])

    def test_ordinary_rename_keeps_in_place_fast_path(self):
        original = marker()
        shell, items = make_shell([original])
        shell._sync_marker_update(original, original.copy(name="Renamed"))
        self.assertEqual(shell.refreshes, 0)
        self.assertEqual(items["MarkerTree"].items[0].Text[1], "Renamed")

    def test_clear_selection_does_not_fall_back_to_stale_native_item(self):
        original = marker()
        shell, _ = make_shell([original])
        shell._selected_marker_frames.clear()
        shell._active_marker_frame = None
        shell._tree_marker = lambda: original
        self.assertIsNone(shell._current_marker())

    def test_selecting_uncached_marker_queues_instead_of_exporting(self):
        original = marker()
        shell, _ = make_shell([original])
        shell.app.thumbnails = NS(enabled=True, cache_key=lambda *args: "key", get=lambda key: None, generate=lambda *args: self.fail("A click exported a frame synchronously"))
        shell._populate_marker_editor(original)
        self.assertEqual(len(shell._thumbnail_jobs), 1)
        self.assertTrue(shell._marker_thumbnail_dirty)

    def test_thumbnail_key_does_not_depend_on_marker_name_or_color(self):
        original = marker()
        shell, _ = make_shell([original])
        shell.app.thumbnails = NS(cache_key=lambda *args: args)
        self.assertEqual(shell._marker_thumbnail_key(original), shell._marker_thumbnail_key(original.copy(name="Other", color="Green")))

    def test_moving_marker_invalidates_old_image_and_queues_refresh(self):
        original = marker()
        original.thumbnail_path = "old.png"
        shell, _ = make_shell([original])
        shell.app.thumbnails = NS(enabled=True, cache_key=lambda *args: "key", get=lambda key: None)
        shell.app.markers.replace_marker = lambda *args, **kwargs: OperationResult(True, changed=1)
        moved = MarkerService.edit_range(original, move=3)
        shell._commit_marker_update(original, moved, "Move", "Moved")
        self.assertIsNone(moved.thumbnail_path)
        self.assertEqual(len(shell._thumbnail_jobs), 1)

    def test_marker_rows_reserve_thumbnail_height_before_load(self):
        shell, items = make_shell([marker(), marker(20)])
        for row in items["MarkerTree"].items:
            self.assertEqual(row.SizeHint[0][1], 64)


class FollowupRenameTests(unittest.TestCase):
    def setup_service(self, clips):
        history = OperationHistory()
        records = MetadataService().build_records(clips)
        return RenameService(history), records, history

    def test_stale_rename_preview_does_not_overwrite_native_name(self):
        clip = FakeClip("a", "A.mov")
        service, records, _ = self.setup_service([clip])
        preview = service.preview(records, prefix="NEW_")
        clip.name = "Director changed name"
        result = service.apply_preview(preview)
        self.assertFalse(result.success)
        self.assertEqual(clip.name, "Director changed name")

    def test_changed_template_metadata_requires_new_preview(self):
        clip = FakeClip("a", "A.mov", {"Scene": "12"})
        service, records, _ = self.setup_service([clip])
        preview = service.preview(records, template="{Scene}_{Index}")
        clip.metadata["Scene"] = "13"
        self.assertFalse(service.apply_preview(preview).success)
        self.assertEqual(clip.name, "A.mov")

    def test_rename_write_verified_even_when_binding_returns_none(self):
        class NoneClip(FakeClip):
            def SetName(self, value):
                self.name = value
                return None
        clip = NoneClip("a", "A.mov")
        service, records, _ = self.setup_service([clip])
        self.assertTrue(service.apply_preview(service.preview(records, prefix="NEW_")).success)
        self.assertEqual(clip.name, "NEW_A")

    def test_invalid_preview_name_cannot_bypass_apply_validation(self):
        clip = FakeClip("a", "A.mov")
        service, records, _ = self.setup_service([clip])
        preview = service.preview(records, prefix="NEW_")
        preview.changes[0].after = ""
        self.assertFalse(service.apply_preview(preview).success)
        self.assertEqual(clip.name, "A.mov")

    def test_entire_stale_plan_is_blocked_before_first_write(self):
        first, second = FakeClip("a", "A.mov"), FakeClip("b", "B.mov")
        service, records, _ = self.setup_service([first, second])
        preview = service.preview(records, template="{Index}")
        second.name = "Changed"
        self.assertFalse(service.apply_preview(preview).success)
        self.assertEqual(first.name, "A.mov")
        self.assertEqual(second.name, "Changed")

    def test_partial_rename_undo_can_be_retried(self):
        first, second = FakeClip("a", "A.mov"), FakeClip("b", "B.mov")
        service, records, history = self.setup_service([first, second])
        self.assertTrue(service.apply_preview(service.preview(records, template="{Index}")).success)
        second.set_name_result = False
        self.assertFalse(history.undo().success)
        self.assertEqual(first.name, "A.mov")
        second.set_name_result = True
        self.assertTrue(history.undo().success)
        self.assertEqual(second.name, "B.mov")

    def test_original_name_preserves_non_extension_periods(self):
        clip = FakeClip("a", "EP01.Scene12.MCU")
        records = MetadataService().build_records([clip])
        self.assertEqual(clip_tokens(records[0])["Original"], "EP01.Scene12.MCU")

    def test_single_metadata_edit_rejects_stale_selection(self):
        clip = FakeClip("a", "A.mov", {"Scene": "1"})
        service = MetadataService()
        record = service.build_records([clip])[0]
        clip.metadata["Scene"] = "Native change"
        self.assertFalse(service.set_field(record, "Scene", "2").success)
        self.assertEqual(clip.metadata["Scene"], "Native change")


class FollowupStillTests(unittest.TestCase):
    def make_service(self, project_class=FakeProject):
        timeline = FakeTimeline()
        project = project_class(timeline)
        resolve = FakeResolve(project)
        service = StillService(resolve, ResolveContextService(resolve))
        queue = service.queue_from_markers([marker()], "{Marker}_{Index}", 24, "Project", "Timeline", timeline)
        return service, queue, project

    def test_file_appearing_after_preview_is_never_overwritten(self):
        service, queue, _ = self.make_service()
        with tempfile.TemporaryDirectory() as folder:
            service.detect_conflicts(queue, folder)
            destination = Path(folder) / queue[0].filename
            destination.write_bytes(b"KEEP")
            result = service.execute_queue(queue, folder, import_to_bin=False)
            self.assertFalse(result.success)
            self.assertEqual(destination.read_bytes(), b"KEEP")

    def test_repeat_capture_does_not_overwrite_or_duplicate_gallery(self):
        service, queue, _ = self.make_service()
        with tempfile.TemporaryDirectory() as folder:
            self.assertTrue(service.execute_queue(queue, folder, import_to_bin=False).success)
            self.assertEqual(service.execute_queue(queue, folder, import_to_bin=False).changed, 0)
            self.assertEqual(len(service.gallery), 1)

    def test_invalid_queue_path_cannot_escape_output_folder(self):
        service, queue, _ = self.make_service()
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "stills"
            queue[0].filename = "../escape.png"
            result = service.execute_queue(queue, output, import_to_bin=False)
            self.assertFalse(result.success)
            self.assertFalse((Path(folder) / "escape.png").exists())

    def test_none_returning_export_with_new_file_is_accepted(self):
        class NoneProject(FakeProject):
            def ExportCurrentFrameAsStill(self, path):
                Path(path).write_bytes(b"png")
                return None
        service, queue, _ = self.make_service(NoneProject)
        with tempfile.TemporaryDirectory() as folder:
            self.assertTrue(service.execute_queue(queue, folder, import_to_bin=False).success)

    def test_async_still_export_waits_for_its_new_file(self):
        class AsyncProject(FakeProject):
            def ExportCurrentFrameAsStill(self, path):
                def write():
                    try:
                        Path(path).write_bytes(b"png")
                    except FileNotFoundError:
                        pass
                self.writer = threading.Timer(0.04, write)
                self.writer.start()
                return None
        service, queue, project = self.make_service(AsyncProject)
        with tempfile.TemporaryDirectory() as folder:
            result = service.execute_queue(queue, folder, import_to_bin=False)
            project.writer.join()
            self.assertTrue(result.success)

    def test_gallery_fallback_cannot_reuse_unrelated_existing_png(self):
        class EmptyGalleryProject(FakeProject):
            def ExportCurrentFrameAsStill(self, path):
                return False
            def GetGallery(self):
                return NS(GetCurrentStillAlbum=lambda: NS(ExportStills=lambda *args: True))
        service, _, project = self.make_service(EmptyGalleryProject)
        project.timeline.GrabStill = lambda: object()
        with tempfile.TemporaryDirectory() as folder:
            unrelated = Path(folder) / "unrelated.png"
            unrelated.write_bytes(b"KEEP")
            self.assertIsNone(service._export_current(project, project.timeline, Path(folder) / "new.png"))
            self.assertEqual(unrelated.read_bytes(), b"KEEP")

    def test_exclusive_publication_refuses_export_time_collision(self):
        service, queue, project = self.make_service()
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / queue[0].filename
            def export(path):
                destination.write_bytes(b"OTHER WRITER")
                Path(path).write_bytes(b"png")
                return True
            project.ExportCurrentFrameAsStill = export
            result = service.execute_queue(queue, folder, import_to_bin=False)
            self.assertFalse(result.success)
            self.assertEqual(destination.read_bytes(), b"OTHER WRITER")

    def test_case_insensitive_duplicate_queue_names_are_both_conflicts(self):
        service, queue, project = self.make_service()
        queue += service.queue_from_markers([marker(20)], "{Index}", 24, "Project", "Timeline", project.timeline)
        queue[0].filename, queue[1].filename = "Image.png", "image.png"
        with tempfile.TemporaryDirectory() as folder:
            service.detect_conflicts(queue, folder)
            self.assertEqual([item.status for item in queue], ["Conflict", "Conflict"])

    def test_export_failure_leaves_no_final_partial_png(self):
        class PartialProject(FakeProject):
            def ExportCurrentFrameAsStill(self, path):
                Path(path).write_bytes(b"partial")
                raise RuntimeError("export interrupted")
        service, queue, _ = self.make_service(PartialProject)
        with tempfile.TemporaryDirectory() as folder:
            self.assertFalse(service.execute_queue(queue, folder, import_to_bin=False).success)
            self.assertFalse((Path(folder) / queue[0].filename).exists())
            self.assertFalse(list(Path(folder).glob(".resolve-hub-export-*")))

    def test_capture_and_import_counts_captured_asset_only_once(self):
        service, queue, _ = self.make_service()
        with tempfile.TemporaryDirectory() as folder:
            result = service.execute_queue(queue, folder, import_to_bin=True)
            self.assertTrue(result.success)
            self.assertEqual(result.changed, 1)


class FollowupHealthCacheTests(unittest.TestCase):
    def test_known_empty_timeline_marks_clips_unused(self):
        record = MetadataService().build_records([FakeClip("a", "A.mov")])[0]
        report = HealthService().scan([record], used_ids=set())
        self.assertEqual(sum(issue.category == "Unused" for issue in report.issues), 1)

    def test_unknown_usage_is_not_treated_as_empty_timeline(self):
        record = MetadataService().build_records([FakeClip("a", "A.mov")])[0]
        report = HealthService().scan([record], used_ids=None)
        self.assertNotIn("Unused", {issue.category for issue in report.issues})
        self.assertIn("Unused", report.skipped_checks)

    def test_clear_cache_preserves_unrelated_pngs(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = ThumbnailCache(None, folder=folder)
            owned = cache.path_for(cache.cache_key("p", "t", "m", 1))
            owned.write_bytes(b"png")
            unrelated = Path(folder) / "camera-original.png"
            unrelated.write_bytes(b"KEEP")
            self.assertEqual(cache.clear(), 1)
            self.assertTrue(unrelated.exists())

    def test_stale_cache_cleanup_preserves_unrelated_pngs(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = ThumbnailCache(None, folder=folder)
            unrelated = Path(folder) / "camera-original.png"
            unrelated.write_bytes(b"KEEP")
            self.assertEqual(cache.delete_stale([]), 0)
            self.assertTrue(unrelated.exists())

    def test_zero_byte_thumbnail_is_a_cache_miss(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = ThumbnailCache(None, folder=folder)
            key = cache.cache_key("p", "t", "m", 1)
            cache.path_for(key).touch()
            self.assertIsNone(cache.get(key))


if __name__ == "__main__":
    unittest.main()
