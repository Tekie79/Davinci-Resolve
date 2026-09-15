import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from meher_resolve_hub.ui.shell import ResolveHubShell
from meher_resolve_hub.models.marker import MarkerRecord
from meher_resolve_hub.models.operation import OperationResult
from meher_resolve_hub.services.marker_service import MarkerService
from tests.fakes import FakeTimeline


class FakeTreeItem:
    def __init__(self, index):
        self.Text = [str(index)]
        self.Selected = False


class FakeMethodTree:
    """Matches Resolve's documented CurrentItem()/SelectedItems() API."""

    def __init__(self, count=4):
        self.items = [FakeTreeItem(index) for index in range(count)]
        self.scrolled_to = None

    def CurrentItem(self):
        return next((item for item in self.items if item.Selected), None)

    def SelectedItems(self):
        return [item for item in self.items if item.Selected]

    def TopLevelItemCount(self):
        return len(self.items)

    def TopLevelItem(self, index):
        return self.items[index]

    def ScrollToItem(self, item):
        self.scrolled_to = item


class FakePropertyTree(FakeMethodTree):
    @property
    def CurrentItem(self):
        return next((item for item in self.items if item.Selected), None)

    @property
    def SelectedItems(self):
        return [item for item in self.items if item.Selected]

    @property
    def TopLevelItemCount(self):
        return len(self.items)


class FakeWindow:
    def __init__(self, tree):
        self.tree = tree
        self.selection_count = type("Label", (), {"Text": ""})()

    def GetItems(self):
        return {"MarkerTree": self.tree, "MarkerSelectionCount": self.selection_count}


class FakeClosableWindow:
    def __init__(self, geometry=None):
        self.Geometry = geometry or [100, 100, 1200, 780]
        self.hidden = False

    def Hide(self):
        self.hidden = True


class FakeDispatcher:
    def __init__(self):
        self.exited = False

    def ExitLoop(self):
        self.exited = True


class FakeBuildTreeItem:
    def __init__(self):
        self.Text = [""] * 7
        self.Icon = {}
        self.TextAlignment = {}
        self.SizeHint = {}
        self.flags = {}
        self.TextColor = {}
        self.BackgroundColor = {}
        self.background_calls = []

    def GetFlags(self):
        return self.flags

    def SetFlags(self, flags):
        self.flags = flags

    def SetTextColor(self, column, color):
        self.TextColor[column] = color

    def SetBackgroundColor(self, column, color):
        self.BackgroundColor[column] = color
        self.background_calls.append(column)


class FakeBuildTree:
    def __init__(self):
        self.items = []

    def Clear(self):
        self.items = []

    def NewItem(self):
        return FakeBuildTreeItem()

    def AddTopLevelItem(self, item):
        self.items.append(item)

    def TopLevelItem(self, index):
        return self.items[index]

    def TopLevelItemCount(self):
        return len(self.items)



class FakePreferences:
    def get(self, section, key, default=None):
        return False


class FakeStills:
    def cleanup_preview(self):
        raise RuntimeError("cleanup failure must not block closing")


class TreeAdapterTests(unittest.TestCase):
    def test_reads_documented_method_api(self):
        tree = FakeMethodTree()
        tree.items[2].Selected = True
        self.assertEqual(ResolveHubShell._tree_current_index(tree), 2)
        self.assertEqual(ResolveHubShell._tree_selected_indices(tree), [2])

    def test_reads_property_api_variant(self):
        tree = FakePropertyTree()
        tree.items[1].Selected = True
        self.assertEqual(ResolveHubShell._tree_current_index(tree), 1)

    def test_programmatic_selection_uses_tree_item_selected(self):
        tree = FakeMethodTree()
        tree.items[0].Selected = True
        self.assertTrue(ResolveHubShell._select_tree_index(tree, 3))
        self.assertEqual(ResolveHubShell._tree_selected_indices(tree), [3])
        self.assertIs(tree.scrolled_to, tree.items[3])

    def test_select_all_and_clear(self):
        tree = FakeMethodTree(3)
        self.assertEqual(ResolveHubShell._set_tree_selection(tree, True), 3)
        self.assertEqual(ResolveHubShell._tree_selected_indices(tree), [0, 1, 2])
        self.assertEqual(ResolveHubShell._set_tree_selection(tree, False), 3)
        self.assertEqual(ResolveHubShell._tree_selected_indices(tree), [])

    def test_marker_state_detects_native_resolve_changes(self):
        before = MarkerRecord("timeline", "timeline", 10, 10, 10, 1, "Blue", "Marker", "")
        after = before.copy(name="Updated")
        self.assertNotEqual(
            ResolveHubShell._marker_state_signature("timeline", [before]),
            ResolveHubShell._marker_state_signature("timeline", [after]),
        )
        self.assertNotEqual(
            ResolveHubShell._marker_state_signature("timeline", [before]),
            ResolveHubShell._marker_state_signature("other-timeline", [before]),
        )

    def test_marker_state_reads_resolve_markers_without_rebuilding_records(self):
        timeline = FakeTimeline(markers={12: {"color": "Green", "name": "Shortcut marker", "note": "", "duration": 2, "customData": "native"}})
        context = type("Context", (), {"timeline": timeline, "timeline_id": "timeline"})()
        state = ResolveHubShell._timeline_marker_state(context)
        self.assertEqual(state, ("timeline", ((12, 13, "Green", "Shortcut marker", "", "native"),)))

    def test_active_marker_survives_stale_tree_current_item(self):
        first = MarkerRecord("timeline", "timeline", 0, 0, 0, 1, "Blue", "New marker", "")
        second = MarkerRecord("timeline", "timeline", 12, 12, 12, 1, "Green", "Previous marker", "")
        tree = FakeMethodTree(2)
        tree.items[1].Selected = True
        shell = ResolveHubShell.__new__(ResolveHubShell)
        shell.window = FakeWindow(tree)
        shell.filtered_markers = [first, second]
        shell._active_marker_frame = first.start_frame
        self.assertIs(shell._current_marker(), first)

    def test_clicked_marker_uses_event_item_over_stale_tree_current_item(self):
        first = MarkerRecord("timeline", "timeline", 0, 0, 0, 1, "Blue", "Clicked marker", "")
        second = MarkerRecord("timeline", "timeline", 12, 12, 12, 1, "Green", "Stale current marker", "")
        tree = FakeMethodTree(2)
        tree.items[1].Selected = True
        shell = ResolveHubShell.__new__(ResolveHubShell)
        shell.window = FakeWindow(tree)
        shell.filtered_markers = [first, second]
        self.assertIs(shell._marker_from_event({"item": tree.items[0]}), first)

    def test_marker_thumbnail_fills_editor_width_at_sixteen_by_nine(self):
        width, height = ResolveHubShell._marker_thumbnail_dimensions(2048, 1183)
        self.assertGreaterEqual(width, 600)
        self.assertEqual(height, round(width * 9 / 16))
        narrow_width, narrow_height = ResolveHubShell._marker_thumbnail_dimensions(800, 768)
        self.assertLessEqual(narrow_height, 120)
        self.assertEqual(narrow_height, round(narrow_width * 9 / 16))

    def test_marker_thumbnail_shrinks_to_keep_editor_actions_visible(self):
        wide, tall = ResolveHubShell._marker_thumbnail_dimensions(2048, 1183)
        short_wide, short_tall = ResolveHubShell._marker_thumbnail_dimensions(2048, 768)
        self.assertLess(short_tall, tall)
        self.assertEqual(short_tall, round(short_wide * 9 / 16))

    def test_geometry_adapter_reads_resolve_one_based_map(self):
        self.assertEqual(
            ResolveHubShell._geometry_values({1: 160, 2: 90, 3: 1440, 4: 900}),
            [160, 90, 1440, 900],
        )
        self.assertEqual(
            ResolveHubShell._geometry_values([160, 90, 1440, 900]),
            [160, 90, 1440, 900],
        )

    def test_missing_marker_thumbnail_is_generated_on_selection(self):
        timeline = FakeTimeline()

        class FakeThumbnails:
            enabled = True

            def __init__(self, destination):
                self.destination = destination
                self.generate_calls = 0

            def cache_key(self, *args):
                return "marker-key"

            def get(self, key):
                return None

            def generate(self, timeline_value, frame, key, fps):
                self.generate_calls += 1
                return OperationResult(True, changed=1, details=[{"path": str(self.destination)}])

        with tempfile.TemporaryDirectory() as folder:
            thumbnails = FakeThumbnails(Path(folder) / "marker.png")
            context = type("Context", (), {"project_id": "project", "timeline_id": "timeline", "timeline": timeline})()
            context_service = type("ContextService", (), {
                "refresh_context": lambda self: context,
                "get_project_fps": lambda self: 24,
            })()
            shell = ResolveHubShell.__new__(ResolveHubShell)
            shell.app = type("App", (), {"context": context_service, "thumbnails": thumbnails})()
            shell._loading_marker_thumbnail = False
            shell._set_marker_thumbnail = lambda *args, **kwargs: None
            marker = MarkerRecord("timeline", "timeline", 10, 10, 10, 1, "Blue", "Marker", "")

            path = shell._get_or_create_marker_thumbnail(marker)

            self.assertEqual(path, thumbnails.destination)
            self.assertEqual(thumbnails.generate_calls, 1)
            self.assertFalse(shell._loading_marker_thumbnail)

    def test_marker_columns_fill_width_without_horizontal_drift(self):
        widths = ResolveHubShell._marker_table_column_widths(659)
        self.assertEqual(len(widths), 7)
        self.assertLessEqual(sum(widths), 659)
        self.assertGreaterEqual(widths[-1], 100)
        self.assertLess(widths[0], widths[1])

    def test_proportional_columns_reserve_scrollbar_space(self):
        widths = ResolveHubShell._proportional_column_widths(390, (0.05, 0.35, 0.14, 0.12, 0.17, 0.17))
        self.assertEqual(len(widths), 6)
        self.assertLessEqual(sum(widths), 366)
        self.assertGreaterEqual(min(widths), 28)
        self.assertGreater(widths[1], widths[0])

    def test_marker_color_cell_is_neutral_read_only_display(self):
        tree = FakeBuildTree()
        shell = ResolveHubShell.__new__(ResolveHubShell)
        shell.window = FakeWindow(tree)

        shell._populate_tree(
            "MarkerTree",
            [
                (0, "First", "●  Blue", "00:00:00:00", "00:00:00:00", "00:00:00:01", ""),
                (1, "Second", "●  Blue", "00:00:01:00", "00:00:01:00", "00:00:00:01", ""),
            ],
        )

        self.assertEqual(tree.items[0].Text[2], "●  Blue")
        self.assertNotIn("⌄", tree.items[0].Text[2])
        self.assertEqual(tree.items[0].Icon, {})

    def test_marker_color_display_colors_dot_and_label_after_selection(self):
        tree = FakeBuildTree()
        shell = ResolveHubShell.__new__(ResolveHubShell)
        shell.window = FakeWindow(tree)
        shell.filtered_markers = [MarkerRecord("timeline", "timeline", 0, 0, 0, 1, "Blue", "Marker", "")]
        shell._selected_marker_frames = {0}
        shell._syncing_marker_selection = False
        shell._populating_marker_tree = False
        shell._populate_tree("MarkerTree", [(0, "Marker", "●  Blue", "", "", "", "")])

        shell._apply_marker_color_swatches()

        self.assertEqual(tree.items[0].Text[2], "●  Blue")
        self.assertEqual(tree.items[0].TextColor[2]["A"], 1.0)
        self.assertFalse(tree.items[0].Selected)
        self.assertEqual(tree.items[0].BackgroundColor[2]["A"], 1.0)
        self.assertFalse(shell._populating_marker_tree)
        self.assertFalse(shell._syncing_marker_selection)

    def test_marker_selection_repaints_only_changed_rows(self):
        tree = FakeBuildTree()
        shell = ResolveHubShell.__new__(ResolveHubShell)
        shell.window = FakeWindow(tree)
        shell.filtered_markers = [
            MarkerRecord("timeline", "timeline", frame, frame, frame, 1, "Blue", "Marker", "")
            for frame in (0, 10, 20)
        ]
        shell._selected_marker_frames = {0}
        shell._active_marker_frame = 0
        shell._syncing_marker_selection = False
        shell._populating_marker_tree = False
        shell._populate_tree("MarkerTree", [(index, "Marker", "●  Blue", "", "", "", "") for index in range(3)])

        shell._set_marker_selection({10}, 10)

        self.assertEqual(len(tree.items[0].background_calls), 7)
        self.assertEqual(len(tree.items[1].background_calls), 7)
        self.assertEqual(len(tree.items[2].background_calls), 0)
        self.assertFalse(tree.items[1].Selected)

    def test_inline_marker_edit_commits_without_rebuilding_tree(self):
        timeline = FakeTimeline()
        context = type("Context", (), {"timeline": timeline, "timeline_id": "timeline"})()
        original = MarkerRecord("timeline", "timeline", 10, 10, 10, 1, "Blue", "Original", "", source_object=timeline)
        tree = FakeBuildTree()
        selection_count = type("Label", (), {"Text": ""})()

        class Window:
            def GetItems(self):
                return {"MarkerTree": tree, "MarkerSelectionCount": selection_count}

        class ContextService:
            def refresh_context(self):
                return context

            def get_project_fps(self):
                return 24

        class Markers:
            def __init__(self):
                self.candidate = None

            def replace_marker(self, old, candidate, label=""):
                self.candidate = candidate
                return OperationResult(True, changed=1)

            @staticmethod
            def edit_range(marker, **changes):
                return MarkerService.edit_range(marker, **changes)

        marker_service = Markers()
        shell = ResolveHubShell.__new__(ResolveHubShell)
        shell.window = Window()
        shell.app = type("App", (), {"context": ContextService(), "markers": marker_service})()
        shell.marker_records = [original]
        shell.filtered_markers = [original]
        shell._marker_state = ResolveHubShell._marker_state_signature("timeline", [original])
        shell._selected_marker_frames = {10}
        shell._active_marker_frame = None
        shell._marker_selection_anchor = 10
        shell._populating_marker_tree = False
        shell._syncing_marker_selection = False
        shell._report_result = lambda *args: None
        shell._refresh_markers = lambda *args, **kwargs: self.fail("single-cell edit rebuilt the marker tree")
        shell._populate_tree("MarkerTree", [shell._marker_row_values(0, original, context, 24)])
        tree.items[0].Text[1] = "Renamed"

        # Resolve can omit the column from ItemChanged; the changed cell is detected.
        shell._marker_tree_item_changed({"item": tree.items[0]})

        self.assertEqual(marker_service.candidate.name, "Renamed")
        self.assertEqual(shell.marker_records[0].name, "Renamed")
        self.assertEqual(shell.filtered_markers[0].name, "Renamed")
        self.assertEqual(tree.items[0].Text[1], "Renamed")

    def test_nudge_updates_marker_in_place(self):
        marker = MarkerRecord("timeline", "timeline", 10, 10, 14, 5, "Blue", "Marker", "")
        shell = ResolveHubShell.__new__(ResolveHubShell)
        shell.app = type("App", (), {"markers": type("Markers", (), {
            "edit_range": staticmethod(MarkerService.edit_range)
        })()})()
        shell._current_marker = lambda: marker
        committed = []
        shell._commit_marker_update = lambda original, candidate, label, success: committed.append((original, candidate, label))

        shell._nudge_marker("end", 5)

        self.assertEqual(committed[0][1].end_frame, 19)
        self.assertEqual(committed[0][1].duration_frames, 10)

    def test_range_commit_marks_thumbnail_dirty_without_generating_it(self):
        original = MarkerRecord("timeline", "timeline", 10, 10, 14, 5, "Blue", "Marker", "")
        candidate = MarkerService.edit_range(original, end=19)
        shell = ResolveHubShell.__new__(ResolveHubShell)
        shell.app = type("App", (), {"markers": type("Markers", (), {
            "replace_marker": lambda self, old, new, label="": OperationResult(True, changed=1)
        })()})()
        shell._marker_thumbnail_dirty = False
        shell._report_result = lambda *args: None
        shell._sync_marker_update = lambda *args: None
        shell._restore_marker_row = lambda *args: None
        shell._refresh_marker_thumb = lambda *args: self.fail("range commit generated a thumbnail before Apply Range")

        shell._commit_marker_update(original, candidate, "Nudge marker end", "Marker nudged")

        self.assertTrue(shell._marker_thumbnail_dirty)


    def test_marker_color_cell_is_read_only_without_disabling_other_columns(self):
        item = FakeBuildTreeItem()
        item.flags = {"ItemIsEditable": True, "ItemIsEnabled": True}

        self.assertTrue(ResolveHubShell._set_marker_item_editable(item, False))
        self.assertFalse(item.flags["ItemIsEditable"])
        self.assertTrue(item.flags["ItemIsEnabled"])

        self.assertTrue(ResolveHubShell._set_marker_item_editable(item, True))
        self.assertTrue(item.flags["ItemIsEditable"])

    def test_close_hides_immediately_and_exits_even_if_cleanup_fails(self):
        shell = ResolveHubShell.__new__(ResolveHubShell)
        shell._running = True
        shell.window = FakeClosableWindow()
        shell.preview_window = FakeClosableWindow()
        shell.still_window = FakeClosableWindow()
        shell.dispatcher = FakeDispatcher()
        shell.app = type("App", (), {"preferences": FakePreferences(), "stills": FakeStills()})()

        self.assertTrue(shell._close())
        self.assertFalse(shell._running)
        self.assertTrue(shell.window.hidden)
        self.assertTrue(shell.dispatcher.exited)
        self.assertTrue(shell.preview_window.hidden)
        self.assertTrue(shell.still_window.hidden)

if __name__ == "__main__":
    unittest.main()
