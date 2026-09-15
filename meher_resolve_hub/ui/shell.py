"""Single-window Resolve Hub shell and workspace coordination."""

import json
from pathlib import Path

from .. import theme
from ..constants import APP_NAME, APP_SUBTITLE, APP_VERSION, MAIN_WINDOW_ID, MARKER_COLORS, PREVIEW_WINDOW_ID, SELECTION_MODES, STILL_WINDOW_ID, WORKSPACES
from ..models.operation import Change, OperationResult, PreviewSummary
from ..preferences import user_data_dir, valid_window_geometry
from ..selection import SelectionUnavailable
from ..services.still_service import StillError, default_output_folder
from ..timecode import duration_frames_to_display, timeline_frame_to_timecode, timeline_timecode_to_frame
from ..utils import collect_bins
from . import health_workspace, history_workspace, marker_workspace, metadata_workspace, rename_workspace, settings_workspace, still_workspace
from .components import button, combo, line_edit, tree


class ResolveHubShell:
    def __init__(self, application):
        self.app = application
        self.ui = application.fusion.UIManager
        self.dispatcher = application.bmd.UIDispatcher(self.ui)
        self.selection_mode = application.preferences.get("general", "default_selection_source", "Timeline Selection")
        self.workspace = application.preferences.get("general", "last_workspace", "Markers") if application.preferences.get("general", "restore_last_workspace", True) else "Markers"
        if self.workspace not in WORKSPACES: self.workspace = "Markers"
        self.selection = None
        self.marker_records = []
        self.filtered_markers = []
        self.metadata_records = []
        self.rename_preview = None
        self.marker_preview = None
        self.metadata_preview = None
        self.still_queue = []
        self.health_report = None
        self.health_issues = []
        self.bin_entries = []
        self.capture_context = None
        self.preview_data = None
        self.preview_callback = None
        self._build_windows()
        self._fill_static_controls()
        self._bind_events()

    def _build_windows(self):
        existing = self.ui.FindWindow(MAIN_WINDOW_ID)
        if existing:
            existing.Show(); existing.Raise(); raise SystemExit()
        geometry = valid_window_geometry(self.app.preferences.get("general", "window_geometry"))
        self.window = self.dispatcher.AddWindow(
            {"ID": MAIN_WINDOW_ID, "Geometry": geometry, "WindowTitle": "Resolve Hub"},
            [self.ui.HGroup({"Spacing": 0, "StyleSheet": theme.ROOT}, [
                self.ui.VGroup({"Weight": 0, "MinimumSize": [154, 620], "Spacing": 5, "StyleSheet": theme.SURFACE}, [
                    self.ui.Label({"Text": "MEHER FLOW", "StyleSheet": theme.SECTION}),
                    self.ui.Label({"Text": "RESOLVE HUB", "StyleSheet": theme.TITLE}),
                    self.ui.VGap(8),
                    *[self.ui.Button({"ID": "Nav" + name, "Text": name, "StyleSheet": theme.NAV}) for name in WORKSPACES[:5]],
                    self.ui.VGap(0, 1),
                    self.ui.Label({"Text": "──────────", "StyleSheet": theme.SUBTITLE}),
                    self.ui.Button({"ID": "NavHistory", "Text": "History", "StyleSheet": theme.NAV}),
                    self.ui.Button({"ID": "NavSettings", "Text": "Settings", "StyleSheet": theme.NAV}),
                    self.ui.Label({"Text": "v" + APP_VERSION, "StyleSheet": theme.SUBTITLE}),
                ]),
                self.ui.VGroup({"Weight": 1, "Spacing": 7}, [
                    self.ui.HGroup({"Spacing": 7, "StyleSheet": theme.SURFACE, "Weight": 0}, [
                        self.ui.VGroup({"Weight": 1, "Spacing": 1}, [self.ui.Label({"Text": APP_NAME, "StyleSheet": theme.TITLE}), self.ui.Label({"Text": APP_SUBTITLE, "StyleSheet": theme.SUBTITLE})]),
                        self.ui.Label({"ID": "ContextProject", "Text": "No project", "StyleSheet": theme.SUBTITLE}),
                        self.ui.Label({"ID": "ContextTimeline", "Text": "No timeline", "StyleSheet": theme.SUBTITLE}),
                        self.ui.Label({"ID": "ContextPage", "Text": "—", "StyleSheet": theme.SUBTITLE}),
                        self.ui.Label({"ID": "ContextTimecode", "Text": "—", "StyleSheet": theme.SECTION}),
                        button(self.ui, "ReturnPosition", "Return"),
                        button(self.ui, "RefreshContext", "Refresh"),
                    ]),
                    self.ui.HGroup({"Spacing": 5, "StyleSheet": theme.SURFACE, "Weight": 0}, [
                        self.ui.Label({"Text": "Selection", "StyleSheet": theme.SECTION}),
                        self.ui.Button({"ID": "SelectionMediaPool", "Text": "Media Pool", "StyleSheet": theme.SECONDARY}),
                        self.ui.Button({"ID": "SelectionTimeline", "Text": "Timeline", "StyleSheet": theme.SECONDARY}),
                        self.ui.Button({"ID": "SelectionCurrentBin", "Text": "Current Bin", "StyleSheet": theme.SECONDARY}),
                        self.ui.Button({"ID": "SelectionRecursiveBin", "Text": "Bin + Sub-Bins", "StyleSheet": theme.SECONDARY}),
                        self.ui.Button({"ID": "SelectionCurrentTimeline", "Text": "Current Timeline", "StyleSheet": theme.SECONDARY}),
                        self.ui.HGap(0, 1), self.ui.Label({"ID": "SelectionCount", "Text": "0 items", "StyleSheet": theme.SUBTITLE}),
                    ]),
                    self.ui.Label({"ID": "GlobalMessage", "Text": "", "Visible": False, "WordWrap": True, "StyleSheet": theme.ERROR, "Weight": 0}),
                    self.ui.Stack({"ID": "WorkspaceStack", "Weight": 1}, [
                        marker_workspace.build(self.ui), metadata_workspace.build(self.ui), rename_workspace.build(self.ui), still_workspace.build(self.ui), health_workspace.build(self.ui), history_workspace.build(self.ui), settings_workspace.build(self.ui),
                    ]),
                    self.ui.HGroup({"Spacing": 6, "StyleSheet": theme.STATUS, "Weight": 0}, [self.ui.Label({"ID": "StatusText", "Text": "Ready", "StyleSheet": theme.SUBTITLE, "Weight": 0}), self.ui.HGap(0, 1), self.ui.Label({"ID": "UndoText", "Text": "", "StyleSheet": theme.SUBTITLE, "Weight": 0}), button(self.ui, "UndoLast", "Undo")]),
                ]),
            ])],
        )
        self.preview_window = self.dispatcher.AddWindow(
            {"ID": PREVIEW_WINDOW_ID, "Geometry": [250, 150, 900, 520], "WindowTitle": "Preview Changes"},
            [self.ui.VGroup({"Spacing": 7, "StyleSheet": theme.ROOT}, [
                self.ui.Label({"ID": "PreviewTitle", "Text": "Preview Changes", "StyleSheet": theme.TITLE, "Weight": 0}),
                self.ui.Label({"ID": "PreviewSummary", "Text": "", "StyleSheet": theme.SUBTITLE, "Weight": 0}),
                tree(self.ui, "PreviewTree", ("Object", "Field", "Before", "After", "Status")),
                self.ui.HGroup({"Spacing": 6, "Weight": 0}, [self.ui.HGap(0, 1), button(self.ui, "CancelPreview", "Cancel"), button(self.ui, "ConfirmPreview", "Apply", True)]),
            ])],
        )
        self.still_window = self.dispatcher.AddWindow(
            {"ID": STILL_WINDOW_ID, "Geometry": [260, 140, 820, 540], "WindowTitle": "Save Still"},
            [self.ui.VGroup({"Spacing": 8, "StyleSheet": theme.ROOT}, [
                self.ui.Label({"Text": "Save Still", "StyleSheet": theme.TITLE, "Weight": 0}), self.ui.Label({"Text": "Name and save.", "StyleSheet": theme.SUBTITLE, "Weight": 0}),
                self.ui.HGroup({"Spacing": 5, "StyleSheet": theme.SURFACE, "Weight": 0}, [line_edit(self.ui, "CapturedTimeline", read_only=True), line_edit(self.ui, "CapturedTimecode", read_only=True), line_edit(self.ui, "CapturedPage", read_only=True)]),
                self.ui.VGroup({"Spacing": 6, "StyleSheet": theme.SURFACE, "Weight": 0}, [
                    self.ui.HGroup({"Spacing": 5}, [self.ui.Label({"Text": "Image Name", "StyleSheet": theme.SUBTITLE}), line_edit(self.ui, "StillFilename", "Image name"), self.ui.Label({"Text": ".png", "StyleSheet": theme.SECTION})]),
                    self.ui.HGroup({"Spacing": 5}, [self.ui.Label({"Text": "Project Bin", "StyleSheet": theme.SUBTITLE}), combo(self.ui, "SaveStillBin", 1), button(self.ui, "RefreshSaveStillBins", "Refresh")]),
                    self.ui.HGroup({"Spacing": 5}, [self.ui.Label({"Text": "Folder", "StyleSheet": theme.SUBTITLE}), line_edit(self.ui, "SaveStillFolder", "Folder"), button(self.ui, "BrowseSaveStillFolder", "Browse…")]),
                    self.ui.Label({"Text": "No bin selected: Master.", "StyleSheet": theme.SUBTITLE, "Weight": 0}),
                ]),
                self.ui.Label({"ID": "SaveStillStatus", "Text": "Still captured.", "WordWrap": True, "StyleSheet": theme.STATUS, "Weight": 0}),
                self.ui.VGap(0, 1),
                self.ui.HGroup({"Spacing": 6, "Weight": 0}, [self.ui.HGap(0, 1), button(self.ui, "CancelSaveStill", "Cancel"), button(self.ui, "ConfirmSaveStill", "Save Still", True)]),
            ])],
        )

    def _fill_combo(self, identity, values, current=None, window=None):
        control = (window or self.window).GetItems()[identity]
        control.Clear()
        selected = 0
        for index, value in enumerate(values):
            control.AddItem(str(value))
            if value == current: selected = index
        control.CurrentIndex = selected

    def _fill_static_controls(self):
        self._fill_combo("MarkerColor", ["All"] + list(MARKER_COLORS), "All")
        self._fill_combo("MarkerType", ["All", "Point", "Range", "With Notes", "Without Notes"], "All")
        self._fill_combo("MarkerSort", ["Timecode", "Name", "Color", "Duration"], "Timecode")
        self._fill_combo("MarkerEditColor", MARKER_COLORS, "Blue")
        self._fill_combo("MarkerBatchField", ["Name", "Color", "Notes", "Range", "Position", "Delete"], "Color")
        self._fill_combo("MarkerBatchOperation", ["Set", "Prefix", "Suffix", "Find/Replace", "Append", "Prepend", "Clear", "Set Duration", "Extend Start", "Extend End", "Contract Start", "Contract End", "Move"], "Set")
        presets = [item.get("name", "Preset") for item in self.app.preferences.get("markers", "presets", [])]
        self._fill_combo("MarkerPreset", presets)
        fields = [item.key for item in self.app.metadata.available_fields(type("Empty", (), {"metadata": {}})())]
        self._fill_combo("MetadataMissingField", ["Any"] + fields, "Any")
        self._fill_combo("MetadataField", fields)
        self._fill_combo("MetadataBatchField", fields)
        self._fill_combo("MetadataBatchOperation", ["Set", "Clear", "Append", "Prepend", "Find / Replace", "Copy Field", "Leave unchanged"], "Set")
        self._fill_combo("RenameCase", ["Keep", "Upper", "Lower", "Title"], "Keep")
        self._fill_combo("StillSource", ["Selected Markers", "Visible Markers", "Selected Timeline Clips"], "Selected Markers")
        self._fill_combo("StillClipPosition", ["First", "Middle", "Last"], "First")
        self._fill_combo("HealthCategory", ["All"], "All")
        self._fill_combo("SettingDefaultSelection", list(SELECTION_MODES), self.selection_mode)
        self._fill_combo("PresetColor", MARKER_COLORS, "Blue")
        items = self.window.GetItems(); prefs = self.app.preferences
        for identity, labels in (("MarkerEditorTabs", ("Details", "Range", "Batch")), ("SettingsTabs", ("General", "Marker Presets", "Metadata & Stills"))):
            tab = items[identity]
            if tab.Count() == 0:
                for label in labels: tab.AddTab(label)
        items["RenameTemplate"].Text = "{Original}"
        items["RenameStart"].Text = "1"; items["RenameWidth"].Text = "2"
        items["StillTemplate"].Text = prefs.get("stills", "naming_template", "{Timeline}_{Timecode}_{Index}")
        items["SettingRestoreWorkspace"].Checked = prefs.get("general", "restore_last_workspace", True)
        items["SettingRestoreGeometry"].Checked = prefs.get("general", "restore_window_geometry", True)
        items["SettingConfirmBatch"].Checked = prefs.get("general", "confirm_destructive_batch", True)
        items["SettingThumbnails"].Checked = prefs.get("thumbnails", "enabled", True)
        items["SettingCacheFolder"].Text = prefs.get("thumbnails", "cache_folder", "") or str(self.app.thumbnails.folder)
        items["SettingMarkerDuration"].Text = str(prefs.get("markers", "default_duration", 1))
        items["SettingRequiredMetadata"].Text = ", ".join(prefs.get("metadata", "required_fields", ["Scene", "Take"]))
        items["SettingStillFolder"].Text = prefs.get("stills", "default_output_folder", "")
        items["SettingStillTemplate"].Text = prefs.get("stills", "naming_template", "{Timeline}_{Timecode}_{Index}")

    def _bind(self, identity, event, handler, window=None):
        (window or self.window).On[identity].__setattr__(event, handler)

    def _bind_events(self):
        self.window.On[MAIN_WINDOW_ID].Close = self._close
        self.preview_window.On[PREVIEW_WINDOW_ID].Close = self._cancel_preview
        self.still_window.On[STILL_WINDOW_ID].Close = self._cancel_save_still
        for index, name in enumerate(WORKSPACES):
            self.window.On["Nav" + name].Clicked = lambda event, workspace=name: self._switch_workspace(workspace)
        self.window.On["RefreshContext"].Clicked = self._refresh_context
        self.window.On["ReturnPosition"].Clicked = lambda event: self._report_result(self.app.navigation.return_to_previous_position(), "Returned to previous position")
        selection_ids = {"SelectionMediaPool": "Media Pool Selection", "SelectionTimeline": "Timeline Selection", "SelectionCurrentBin": "Current Bin", "SelectionRecursiveBin": "Current Bin + Sub-Bins", "SelectionCurrentTimeline": "Current Timeline"}
        for identity, mode in selection_ids.items(): self.window.On[identity].Clicked = lambda event, value=mode: self._change_selection(value)
        self.window.On["UndoLast"].Clicked = self._undo
        self.window.On["UndoHistory"].Clicked = self._undo
        self.window.On["MarkerEditorTabs"].CurrentChanged = lambda event: self._sync_stack("MarkerEditorTabs", "MarkerEditorStack")
        self.window.On["SettingsTabs"].CurrentChanged = lambda event: self._sync_stack("SettingsTabs", "SettingsStack")
        self.preview_window.On["CancelPreview"].Clicked = self._cancel_preview
        self.preview_window.On["ConfirmPreview"].Clicked = self._confirm_preview
        # Marker events.
        for identity in ("RefreshMarkers",): self.window.On[identity].Clicked = self._refresh_markers
        self.window.On["MarkerSearch"].TextChanged = self._refresh_markers
        for identity in ("MarkerColor", "MarkerType", "MarkerSort"):
            self.window.On[identity].CurrentIndexChanged = self._refresh_markers
        self.window.On["MarkerTree"].ItemClicked = self._marker_selected
        self.window.On["MarkerTree"].ItemSelectionChanged = self._marker_selected
        self.window.On["MarkerTree"].ItemDoubleClicked = self._go_to_marker
        self.window.On["SelectAllMarkers"].Clicked = self._select_all_markers
        self.window.On["ClearMarkerSelection"].Clicked = self._clear_marker_selection
        self.window.On["PrevMarker"].Clicked = lambda event: self._step_marker(-1)
        self.window.On["NextMarker"].Clicked = lambda event: self._step_marker(1)
        self.window.On["GoToMarker"].Clicked = self._go_to_marker
        self.window.On["GoToMarkerEnd"].Clicked = self._go_to_marker_end
        self.window.On["SaveMarkerDetails"].Clicked = self._save_marker_details
        self.window.On["ClearMarkerNotes"].Clicked = self._clear_marker_notes
        self.window.On["SaveMarkerRange"].Clicked = self._save_marker_range
        self.window.On["SetMarkerStart"].Clicked = lambda event: self._set_marker_edge("start")
        self.window.On["SetMarkerEnd"].Clicked = lambda event: self._set_marker_edge("end")
        self.window.On["MoveMarkerPlayhead"].Clicked = self._move_marker_playhead
        self.window.On["AddMarker"].Clicked = self._add_marker
        self.window.On["ApplyMarkerPreset"].Clicked = self._apply_marker_preset
        self.window.On["PreviewMarkerBatch"].Clicked = self._preview_marker_batch
        self.window.On["ApplyMarkerBatch"].Clicked = self._apply_marker_batch
        self.window.On["MarkerStill"].Clicked = self._marker_still
        self.window.On["MarkerName"].ReturnPressed = self._save_marker_details
        self.window.On["PrevSameColor"].Clicked = lambda event: self._step_same_color(-1)
        self.window.On["NextSameColor"].Clicked = lambda event: self._step_same_color(1)
        self.window.On["RefreshMarkerThumb"].Clicked = self._refresh_marker_thumb
        self.window.On["RefreshVisibleMarkerThumbs"].Clicked = self._refresh_visible_marker_thumbs
        self.window.On["ManageMarkerPresets"].Clicked = lambda event: self._switch_workspace("Settings")
        for edge in ("Start", "End"):
            for amount in (-10, -5, -1, 1, 5, 10):
                suffix = ("Minus" + str(abs(amount))) if amount < 0 else ("Plus" + str(amount))
                self.window.On[edge + suffix].Clicked = lambda event, which=edge.lower(), delta=amount: self._nudge_marker(which, delta)
        # Metadata.
        self.window.On["RefreshMetadata"].Clicked = self._refresh_metadata
        self.window.On["MetadataClipTree"].ItemClicked = self._metadata_selected
        self.window.On["MetadataPrevious"].Clicked = lambda event: self._step_metadata(-1)
        self.window.On["MetadataNext"].Clicked = lambda event: self._step_metadata(1)
        self.window.On["MetadataReveal"].Clicked = self._reveal_metadata
        self.window.On["SaveMetadataField"].Clicked = self._save_metadata_field
        self.window.On["MetadataValue"].ReturnPressed = self._save_metadata_field
        self.window.On["RefreshMetadataThumb"].Clicked = self._refresh_metadata_thumb
        self.window.On["PreviewMetadataBatch"].Clicked = self._preview_metadata_batch
        self.window.On["ApplyMetadataBatch"].Clicked = self._apply_metadata_batch
        self.window.On["ExportMetadataCSV"].Clicked = self._export_metadata_csv
        self.window.On["ImportMetadataCSV"].Clicked = self._import_metadata_csv
        # Rename.
        self.window.On["RefreshRename"].Clicked = self._refresh_rename
        self.window.On["PreviewRename"].Clicked = self._preview_rename
        self.window.On["ApplyRename"].Clicked = self._apply_rename
        self.window.On["SaveRenameTemplate"].Clicked = self._save_rename_template
        # Stills.
        self.window.On["GrabCurrentStill"].Clicked = self._grab_current_still
        self.window.On["BuildStillQueue"].Clicked = self._build_still_queue
        self.window.On["CaptureStillQueue"].Clicked = self._capture_still_queue
        self.window.On["ClearStillQueue"].Clicked = self._clear_still_queue
        self.window.On["RemoveStillQueue"].Clicked = self._remove_still_queue
        self.window.On["NavigateStill"].Clicked = self._navigate_still
        self.window.On["StillTree"].ItemClicked = self._still_selected
        self.window.On["StillTree"].ItemDoubleClicked = self._navigate_still
        self.window.On["RenameQueuedStill"].Clicked = self._rename_queued_still
        self.window.On["ImportCapturedStills"].Clicked = self._import_captured_stills
        self.window.On["RefreshStillBins"].Clicked = self._refresh_still_bins
        self.window.On["BrowseStillFolder"].Clicked = self._browse_still_folder
        self.still_window.On["CancelSaveStill"].Clicked = self._cancel_save_still
        self.still_window.On["ConfirmSaveStill"].Clicked = self._confirm_save_still
        self.still_window.On["RefreshSaveStillBins"].Clicked = self._refresh_save_still_bins
        self.still_window.On["BrowseSaveStillFolder"].Clicked = self._browse_save_still_folder
        # Health/settings.
        self.window.On["ScanHealth"].Clicked = self._scan_health
        self.window.On["HealthCategory"].CurrentIndexChanged = self._refresh_health
        self.window.On["ExportHealthCSV"].Clicked = lambda event: self._export_health("csv")
        self.window.On["ExportHealthJSON"].Clicked = lambda event: self._export_health("json")
        self.window.On["PreviousHealth"].Clicked = lambda event: self._step_health(-1)
        self.window.On["NextHealth"].Clicked = lambda event: self._step_health(1)
        self.window.On["GoToHealth"].Clicked = self._go_to_health
        self.window.On["IgnoreHealth"].Clicked = self._ignore_health
        self.window.On["SaveSettings"].Clicked = self._save_settings
        self.window.On["ClearThumbnailCache"].Clicked = self._clear_thumbnail_cache
        self.window.On["BrowseCacheFolder"].Clicked = self._browse_cache_folder
        self.window.On["PresetTree"].ItemClicked = self._preset_selected
        self.window.On["AddPreset"].Clicked = self._add_preset
        self.window.On["UpdatePreset"].Clicked = self._update_preset
        self.window.On["MovePresetUp"].Clicked = lambda event: self._move_preset(-1)
        self.window.On["MovePresetDown"].Clicked = lambda event: self._move_preset(1)
        self.window.On["DeletePreset"].Clicked = self._delete_preset

    def _combo_text(self, identity, window=None):
        control = (window or self.window).GetItems()[identity]
        try: return str(control.CurrentText)
        except Exception:
            try: return str(control.ItemText(control.CurrentIndex))
            except Exception: return ""

    def _sync_stack(self, tab_id, stack_id):
        items = self.window.GetItems()
        items[stack_id].CurrentIndex = items[tab_id].CurrentIndex

    def _set_status(self, text, serious=False):
        self.window.GetItems()["StatusText"].Text = str(text)
        message = self.window.GetItems()["GlobalMessage"]
        if serious:
            self.app.logger.error(str(text)); message.Text = str(text); message.Visible = True
        else:
            message.Visible = False
        record = self.app.history.peek()
        self.window.GetItems()["UndoText"].Text = ("Undo: " + record.label) if record else ""

    def _warning(self, identity, text=""):
        control = self.window.GetItems()[identity]
        control.Text = str(text); control.Visible = bool(text)

    def _refresh_context(self, event=None):
        context = self.app.context.refresh_context(); items = self.window.GetItems()
        items["ContextProject"].Text = context.project_name or "No project"
        items["ContextTimeline"].Text = context.timeline_name or "No timeline"
        items["ContextPage"].Text = context.current_page or "—"
        items["ContextTimecode"].Text = context.current_timecode or "—"
        capabilities = self.app.capabilities.detect(context)
        for identity, key in (("SelectionMediaPool", "media_pool_selection"), ("SelectionTimeline", "timeline_selection"), ("GrabCurrentStill", "direct_still_export")):
            capability = capabilities[key]; items[identity].Enabled = capability.supported or (key == "direct_still_export" and capabilities["gallery_still_export"].supported)
            try: items[identity].ToolTip = capability.reason if not capability.supported else ""
            except Exception: pass
        marker_supported = capabilities["timeline_markers"].supported
        for identity in ("AddMarker", "SaveMarkerDetails", "SaveMarkerRange", "PreviewMarkerBatch", "ApplyMarkerBatch", "ApplyMarkerPreset"):
            items[identity].Enabled = marker_supported
        items["PlayMarkerRange"].Enabled = False
        try: items["PlayMarkerRange"].ToolTip = "Resolve's scripting API does not expose timeline playback control."
        except Exception: pass
        self._refresh_selection()
        self._set_status("Ready" if context.project else "Open a Resolve project.")

    def _refresh_selection(self):
        try:
            self.selection = self.app.selection.get_selection(self.selection_mode)
            self.window.GetItems()["SelectionCount"].Text = "%d items" % self.selection.count
            self._set_status("%s · %d items" % (self.selection_mode, self.selection.count))
        except SelectionUnavailable as exc:
            self.selection = None; self.window.GetItems()["SelectionCount"].Text = "Unavailable"; self._set_status(str(exc), True)
        style_ids = {"SelectionMediaPool": "Media Pool Selection", "SelectionTimeline": "Timeline Selection", "SelectionCurrentBin": "Current Bin", "SelectionRecursiveBin": "Current Bin + Sub-Bins", "SelectionCurrentTimeline": "Current Timeline"}
        for identity, mode in style_ids.items(): self.window.GetItems()[identity].StyleSheet = theme.NAV_ACTIVE if mode == self.selection_mode else theme.SECONDARY

    def _change_selection(self, mode):
        self.selection_mode = mode; self._refresh_selection(); self._refresh_workspace()

    def _switch_workspace(self, workspace):
        self.workspace = workspace; self.window.GetItems()["WorkspaceStack"].CurrentIndex = WORKSPACES.index(workspace)
        for name in WORKSPACES: self.window.GetItems()["Nav" + name].StyleSheet = theme.NAV_ACTIVE if name == workspace else theme.NAV
        self.app.preferences.set("general", "last_workspace", workspace)
        self._refresh_context(); self._refresh_workspace()

    def _refresh_workspace(self):
        {"Markers": self._refresh_markers, "Metadata": self._refresh_metadata, "Rename": self._refresh_rename, "Stills": self._refresh_stills, "Health": self._refresh_health, "History": self._refresh_history, "Settings": self._refresh_settings}[self.workspace]()

    @staticmethod
    def _tree_current_item(tree):
        """Return the current UIManager tree item across Resolve API variants."""
        try:
            current = tree.CurrentItem
            return current() if callable(current) else current
        except Exception:
            return None

    @classmethod
    def _tree_selected_indices(cls, tree):
        try:
            selected_items = tree.SelectedItems
            selected = list((selected_items() if callable(selected_items) else selected_items) or [])
        except Exception:
            current = cls._tree_current_item(tree)
            selected = [current] if current else []
        result = []
        for item in selected:
            try: result.append(int(item.Text[0]))
            except Exception: pass
        return result

    @classmethod
    def _tree_current_index(cls, tree):
        # A single selected row is more reliable after programmatic navigation.
        selected = cls._tree_selected_indices(tree)
        if len(selected) == 1:
            return selected[0]
        current = cls._tree_current_item(tree)
        try:
            return int(current.Text[0])
        except Exception:
            return selected[0] if selected else -1

    @staticmethod
    def _select_tree_index(tree, index):
        """Select one row using documented TreeItem.Selected semantics."""
        try:
            count_value = tree.TopLevelItemCount
            count = int(count_value() if callable(count_value) else count_value)
        except Exception:
            return False
        target = None
        for row in range(count):
            try:
                item = tree.TopLevelItem(row)
                item.Selected = row == index
                if row == index:
                    target = item
            except Exception:
                continue
        if target is None:
            return False
        try:
            tree.ScrollToItem(target)
        except Exception:
            pass
        return True

    @staticmethod
    def _set_tree_selection(tree, selected):
        try:
            count_value = tree.TopLevelItemCount
            count = int(count_value() if callable(count_value) else count_value)
        except Exception:
            return 0
        changed = 0
        for row in range(count):
            try:
                tree.TopLevelItem(row).Selected = bool(selected)
                changed += 1
            except Exception:
                pass
        return changed

    def _populate_tree(self, identity, rows):
        target = self.window.GetItems()[identity]; target.Clear()
        for row in rows:
            item = target.NewItem()
            for column, value in enumerate(row): item.Text[column] = str(value)
            target.AddTopLevelItem(item)

    def _selected_markers(self):
        indices = self._tree_selected_indices(self.window.GetItems()["MarkerTree"])
        return [self.filtered_markers[index] for index in indices if 0 <= index < len(self.filtered_markers)]

    def _current_marker(self):
        index = self._tree_current_index(self.window.GetItems()["MarkerTree"])
        return self.filtered_markers[index] if 0 <= index < len(self.filtered_markers) else None

    def _marker_timecode(self, marker, end=False):
        context = self.app.context.refresh_context(); fps = self.app.context.get_project_fps()
        frame = marker.end_frame if end else marker.start_frame
        return timeline_frame_to_timecode(context.timeline, int(context.timeline.GetStartFrame()) + frame, fps)

    def _refresh_markers(self, event=None):
        context = self.app.context.refresh_context()
        if not context.timeline:
            self.marker_records = []; self.filtered_markers = []; self._populate_tree("MarkerTree", []); self._warning("MarkerWarning", "Open a timeline to use Marker Manager."); return
        self._warning("MarkerWarning")
        self.marker_records = self.app.markers.list_markers(context.timeline)
        items = self.window.GetItems(); marker_type = self._combo_text("MarkerType")
        with_notes = True if marker_type == "With Notes" else False if marker_type == "Without Notes" else None
        type_filter = marker_type if marker_type in ("Point", "Range") else "All"
        self.filtered_markers = self.app.markers.filter_markers(self.marker_records, items["MarkerSearch"].Text, self._combo_text("MarkerColor"), type_filter, with_notes, self._combo_text("MarkerSort"))
        rows = []
        fps = self.app.context.get_project_fps()
        timeline_start = int(context.timeline.GetStartFrame())
        for index, record in enumerate(self.filtered_markers):
            start_tc = timeline_frame_to_timecode(context.timeline, timeline_start + record.start_frame, fps)
            end_tc = timeline_frame_to_timecode(context.timeline, timeline_start + record.end_frame, fps)
            rows.append((index, record.name or "Untitled", record.color, start_tc, end_tc, duration_frames_to_display(record.duration_frames, fps), record.note.replace("\n", " ")[:80]))
        self._populate_tree("MarkerTree", rows); items["MarkerCount"].Text = "%d markers" % len(rows); items["MarkerSelectionCount"].Text = "0 selected"

    def _marker_selected(self, event=None):
        marker = self._current_marker()
        if not marker: return
        items = self.window.GetItems(); items["MarkerName"].Text = marker.name; items["MarkerNotes"].PlainText = marker.note
        self._fill_combo("MarkerEditColor", MARKER_COLORS, marker.color)
        items["MarkerStart"].Text = self._marker_timecode(marker); items["MarkerEnd"].Text = self._marker_timecode(marker, True); items["MarkerDuration"].Text = str(marker.duration_frames)
        items["MarkerRangeBar"].Text = "────────◀%s▶────────" % ("═" * max(2, min(18, marker.duration_frames)))
        selected = self._selected_markers(); items["MarkerSelectionCount"].Text = "%d selected" % len(selected)
        context = self.app.context.refresh_context(); key = self.app.thumbnails.cache_key(context.project_id, context.timeline_id, marker.stable_key, marker.start_frame, marker.color + marker.name)
        path = self.app.thumbnails.get(key)
        items["MarkerThumb"].Text = str(path) if path else "Thumbnail not cached"
        if path:
            try: items["MarkerThumb"].Pixmap = str(path)
            except Exception: pass

    def _go_to_marker(self, event=None):
        marker = self._current_marker()
        if not marker: self._set_status("Select a marker first."); return
        result = self.app.navigation.go_to(self._marker_timecode(marker), marker.stable_key, self.filtered_markers.index(marker)); self._report_result(result, "Marker selected")

    def _go_to_marker_end(self, event=None):
        marker = self._current_marker()
        if not marker: self._set_status("Select a marker first."); return
        result = self.app.navigation.go_to(self._marker_timecode(marker, True), marker.stable_key, self.filtered_markers.index(marker)); self._report_result(result, "Marker end selected")

    def _step_marker(self, direction):
        tree = self.window.GetItems()["MarkerTree"]; index = self._tree_current_index(tree)
        _item, index = self.app.navigation.adjacent(self.filtered_markers, index, direction)
        if index >= 0:
            self._select_tree_index(tree, index)
            self._marker_selected(); self._go_to_marker()

    def _step_same_color(self, direction):
        current = self._current_marker()
        if not current: self._set_status("Select a marker first."); return
        index = self.filtered_markers.index(current); candidates = range(index + direction, len(self.filtered_markers), direction) if direction > 0 else range(index + direction, -1, direction)
        for target in candidates:
            if self.filtered_markers[target].color == current.color:
                tree = self.window.GetItems()["MarkerTree"]
                self._select_tree_index(tree, target)
                self._marker_selected(); self._go_to_marker(); return
        self._set_status("No more %s markers in this result." % current.color)

    def _refresh_marker_thumb(self, event=None):
        marker = self._current_marker(); context = self.app.context.refresh_context()
        if not marker: self._set_status("Select a marker first."); return
        if not context.timeline: self._set_status("Open a timeline first.", True); return
        key = self.app.thumbnails.cache_key(context.project_id, context.timeline_id, marker.stable_key, marker.start_frame, marker.color + marker.name)
        absolute = int(context.timeline.GetStartFrame()) + marker.start_frame
        result = self.app.thumbnails.generate(context.timeline, absolute, key, self.app.context.get_project_fps())
        if result.success:
            marker.thumbnail_path = result.details[0]["path"]; self.window.GetItems()["MarkerThumb"].Text = marker.thumbnail_path
            try: self.window.GetItems()["MarkerThumb"].Pixmap = marker.thumbnail_path
            except Exception: pass
        self._report_result(result, "Thumbnail refreshed")

    def _refresh_visible_marker_thumbs(self, event=None):
        context = self.app.context.refresh_context()
        if not context.timeline: return
        result = OperationResult(True)
        for marker in self.filtered_markers:
            key = self.app.thumbnails.cache_key(context.project_id, context.timeline_id, marker.stable_key, marker.start_frame, marker.color + marker.name)
            if self.app.thumbnails.get(key): result.unchanged += 1; continue
            item = self.app.thumbnails.generate(context.timeline, int(context.timeline.GetStartFrame()) + marker.start_frame, key, self.app.context.get_project_fps())
            result.changed += item.changed; result.failed += item.failed; result.errors.extend(item.errors)
        result.success = result.failed == 0; self._report_result(result, "Visible thumbnails refreshed")

    def _select_all_markers(self, event=None):
        self._set_tree_selection(self.window.GetItems()["MarkerTree"], True)
        self.window.GetItems()["MarkerSelectionCount"].Text = "%d selected" % len(self.filtered_markers)

    def _clear_marker_selection(self, event=None):
        self._set_tree_selection(self.window.GetItems()["MarkerTree"], False)
        self.window.GetItems()["MarkerSelectionCount"].Text = "0 selected"

    def _save_marker_details(self, event=None):
        marker = self._current_marker()
        if not marker: self._set_status("Select a marker first."); return
        items = self.window.GetItems(); candidate = marker.copy(name=str(items["MarkerName"].Text), note=str(items["MarkerNotes"].PlainText), color=self._combo_text("MarkerEditColor"))
        result = self.app.markers.replace_marker(marker, candidate, label="Edit marker details"); self._report_result(result, "Marker updated"); self._refresh_markers()

    def _clear_marker_notes(self, event=None):
        self.window.GetItems()["MarkerNotes"].PlainText = ""

    def _save_marker_range(self, event=None):
        marker = self._current_marker()
        if not marker: self._set_status("Select a marker first."); return
        items = self.window.GetItems(); context = self.app.context.refresh_context(); fps = self.app.context.get_project_fps()
        try:
            absolute_start = timeline_timecode_to_frame(context.timeline, items["MarkerStart"].Text, fps); absolute_end = timeline_timecode_to_frame(context.timeline, items["MarkerEnd"].Text, fps)
            relative_start = absolute_start - int(context.timeline.GetStartFrame()); relative_end = absolute_end - int(context.timeline.GetStartFrame()); duration = int(items["MarkerDuration"].Text or relative_end - relative_start + 1)
            start_changed = relative_start != marker.start_frame
            end_changed = relative_end != marker.end_frame
            duration_changed = duration != marker.duration_frames
            if duration_changed and end_changed and relative_end != relative_start + duration - 1:
                raise ValueError("End and duration conflict. Change one, or enter matching values.")
            if duration_changed:
                candidate = self.app.markers.edit_range(marker, start=relative_start if start_changed else None, duration=duration)
            elif end_changed:
                candidate = self.app.markers.edit_range(marker, start=relative_start if start_changed else None, end=relative_end)
            elif start_changed:
                candidate = self.app.markers.edit_range(marker, start=relative_start)
            else:
                candidate = marker
            result = self.app.markers.replace_marker(marker, candidate, label="Edit marker range")
        except Exception as exc: result = type("Result", (), {"success": False, "changed": 0, "unchanged": 0, "failed": 1, "warnings": [], "errors": [str(exc)]})()
        self._report_result(result, "Marker range updated"); self._refresh_markers()

    def _nudge_marker(self, edge, delta):
        marker = self._current_marker()
        if not marker: self._set_status("Select a marker first."); return
        if edge == "start": candidate = self.app.markers.edit_range(marker, start=marker.start_frame + delta)
        else: candidate = self.app.markers.edit_range(marker, end=marker.end_frame + delta)
        result = self.app.markers.replace_marker(marker, candidate, label="Nudge marker %s" % edge); self._report_result(result, "Marker nudged"); self._refresh_markers()

    def _set_marker_edge(self, edge):
        marker = self._current_marker(); context = self.app.context.refresh_context()
        if not marker: self._set_status("Select a marker first."); return
        if not context.timeline: self._set_status("Open a timeline first.", True); return
        frame = timeline_timecode_to_frame(context.timeline, context.current_timecode, self.app.context.get_project_fps()) - int(context.timeline.GetStartFrame())
        candidate = self.app.markers.edit_range(marker, start=frame) if edge == "start" else self.app.markers.edit_range(marker, end=frame)
        result = self.app.markers.replace_marker(marker, candidate, label="Set marker %s" % edge); self._report_result(result, "Marker updated"); self._refresh_markers()

    def _move_marker_playhead(self, event=None):
        marker = self._current_marker(); context = self.app.context.refresh_context()
        if not marker: self._set_status("Select a marker first."); return
        if not context.timeline: self._set_status("Open a timeline first.", True); return
        frame = timeline_timecode_to_frame(context.timeline, context.current_timecode, self.app.context.get_project_fps()) - int(context.timeline.GetStartFrame())
        candidate = self.app.markers.edit_range(marker, move=frame - marker.start_frame)
        result = self.app.markers.replace_marker(marker, candidate, label="Move marker"); self._report_result(result, "Marker moved"); self._refresh_markers()

    def _add_marker(self, event=None):
        context = self.app.context.refresh_context()
        if not context.timeline: self._set_status("Open a timeline first.", True); return
        presets = self.app.preferences.get("markers", "presets", []); preset = presets[0] if presets else {"color": "Blue", "default_marker_name": "Marker", "default_duration_frames": 1, "note_template": "", "custom_data": {}}
        frame = timeline_timecode_to_frame(context.timeline, context.current_timecode, self.app.context.get_project_fps()) - int(context.timeline.GetStartFrame())
        custom = json.dumps(preset.get("custom_data", {}), sort_keys=True) if preset.get("custom_data") else ""
        result = self.app.markers.add_marker(context.timeline, frame, preset.get("color", "Blue"), preset.get("default_marker_name", "Marker"), preset.get("note_template", ""), int(preset.get("default_duration_frames", 1)), custom)
        self._report_result(result, "Marker added"); self._refresh_markers()

    def _apply_marker_preset(self, event=None):
        marker = self._current_marker()
        if not marker: self._set_status("Select a marker first."); return
        presets = self.app.preferences.get("markers", "presets", []); index = self.window.GetItems()["MarkerPreset"].CurrentIndex
        if not (0 <= index < len(presets)): return
        preset = presets[index]; custom = json.dumps(preset.get("custom_data", {}), sort_keys=True) if preset.get("custom_data") else marker.custom_data
        candidate = self.app.markers.edit_range(marker.copy(color=preset.get("color", marker.color), name=preset.get("default_marker_name", marker.name), note=preset.get("note_template", marker.note), custom_data=custom), duration=int(preset.get("default_duration_frames", marker.duration_frames)))
        result = self.app.markers.replace_marker(marker, candidate, label="Apply marker preset"); self._report_result(result, "Preset applied"); self._refresh_markers()

    def _marker_batch_args(self):
        field_label = self._combo_text("MarkerBatchField"); field = {"Name": "name", "Color": "color", "Notes": "note", "Range": "range", "Position": "start_frame", "Delete": "delete"}[field_label]
        return self._selected_markers(), field, self._combo_text("MarkerBatchOperation"), self.window.GetItems()["MarkerBatchValue"].Text

    def _preview_marker_batch(self, event=None):
        records, field, operation, value = self._marker_batch_args()
        if not records: self._set_status("Select one or more markers first."); return
        self.marker_preview = self.app.markers.preview_batch(records, field, operation, value); self._show_preview("Marker Batch", self.marker_preview, self._apply_marker_preview)

    def _apply_marker_batch(self, event=None):
        records, field, operation, value = self._marker_batch_args()
        if not records: self._set_status("Select one or more markers first."); return
        self.marker_preview = self.app.markers.preview_batch(records, field, operation, value); self._show_preview("Marker Batch", self.marker_preview, self._apply_marker_preview)

    def _apply_marker_preview(self):
        result = self.app.markers.apply_preview(self.marker_preview); self._report_result(result, "Marker batch complete"); self._refresh_markers(); return result

    def _marker_still(self, event=None):
        selected = self._selected_markers() or ([self._current_marker()] if self._current_marker() else [])
        if not selected: self._set_status("Select one or more markers first."); return
        self._switch_workspace("Stills"); self._fill_combo("StillSource", ["Selected Markers", "Visible Markers", "Selected Timeline Clips"], "Selected Markers"); self.filtered_markers = selected; self._build_still_queue()

    def _refresh_metadata(self, event=None):
        self._refresh_selection()
        if not self.selection:
            self.metadata_records = []; self._populate_tree("MetadataClipTree", []); self._warning("MetadataWarning", "Choose an available clip selection source."); return
        self._warning("MetadataWarning")
        all_records = self.app.metadata.build_records(self.selection.clips, self.selection.timeline_items)
        missing = self._combo_text("MetadataMissingField"); missing = "" if missing == "Any" else missing
        self.metadata_records = self.app.metadata.search(all_records, self.window.GetItems()["MetadataSearch"].Text, missing)
        rows = [(index, record.name, record.metadata.get("Scene", ""), record.metadata.get("Take", ""), record.metadata.get("Camera #", record.metadata.get("Camera ID", "")), record.metadata.get("Reel Name", "")) for index, record in enumerate(self.metadata_records)]
        self._populate_tree("MetadataClipTree", rows); self.window.GetItems()["MetadataCount"].Text = "%d clips" % len(rows)

    def _current_metadata(self):
        index = self._tree_current_index(self.window.GetItems()["MetadataClipTree"]); return self.metadata_records[index] if 0 <= index < len(self.metadata_records) else None

    def _selected_metadata(self):
        indices = self._tree_selected_indices(self.window.GetItems()["MetadataClipTree"]); return [self.metadata_records[index] for index in indices if 0 <= index < len(self.metadata_records)]

    def _metadata_selected(self, event=None):
        record = self._current_metadata()
        if not record: return
        items = self.window.GetItems(); items["MetadataClipName"].Text = record.name
        field = self._combo_text("MetadataField"); items["MetadataValue"].Text = str(record.metadata.get(field, ""))
        if record.thumbnail_path:
            try: items["MetadataLargeThumb"].Pixmap = record.thumbnail_path
            except Exception: items["MetadataLargeThumb"].Text = record.thumbnail_path

    def _refresh_metadata_thumb(self, event=None):
        record = self._current_metadata(); context = self.app.context.refresh_context()
        if not record or not record.timeline_items or not context.timeline:
            self._set_status("This clip has no current-timeline position for a thumbnail."); return
        timeline_item = record.timeline_items[0]; frame = int(timeline_item.GetStart())
        key = self.app.thumbnails.cache_key(context.project_id, context.timeline_id, record.unique_id, frame, record.name)
        result = self.app.thumbnails.generate(context.timeline, frame, key, self.app.context.get_project_fps())
        if result.success:
            record.thumbnail_path = result.details[0]["path"]; self.window.GetItems()["MetadataLargeThumb"].Text = record.thumbnail_path
            try: self.window.GetItems()["MetadataLargeThumb"].Pixmap = record.thumbnail_path
            except Exception: pass
        self._report_result(result, "Thumbnail refreshed")

    def _step_metadata(self, direction):
        tree = self.window.GetItems()["MetadataClipTree"]; index = self._tree_current_index(tree); _record, index = self.app.navigation.adjacent(self.metadata_records, index, direction)
        if index >= 0:
            self._select_tree_index(tree, index)
            self._metadata_selected()

    def _reveal_metadata(self, event=None):
        record = self._current_metadata(); context = self.app.context.refresh_context()
        if not record or not context.media_pool: return
        try: success = bool(context.media_pool.SetSelectedClip(record.media_pool_item))
        except Exception: success = False
        self._set_status("Clip revealed" if success else "Resolve could not reveal this clip.", not success)

    def _save_metadata_field(self, event=None):
        record = self._current_metadata()
        if not record: return
        result = self.app.metadata.set_field(record, self._combo_text("MetadataField"), self.window.GetItems()["MetadataValue"].Text); self._report_result(result, "Metadata saved"); self._refresh_metadata()

    def _metadata_batch(self):
        records = self._selected_metadata() or self.metadata_records
        return self.app.metadata.preview_batch(records, self._combo_text("MetadataBatchField"), self._combo_text("MetadataBatchOperation"), self.window.GetItems()["MetadataBatchValue"].Text, self.window.GetItems()["MetadataBatchReplacement"].Text, bool(self.window.GetItems()["MetadataBlanksOnly"].Checked), self.window.GetItems()["MetadataBatchReplacement"].Text)

    def _preview_metadata_batch(self, event=None):
        self.metadata_preview = self._metadata_batch(); self._show_preview("Metadata Batch", self.metadata_preview, self._apply_metadata_preview)

    def _apply_metadata_batch(self, event=None):
        self._preview_metadata_batch()

    def _apply_metadata_preview(self):
        result = self.app.metadata.apply_preview(self.metadata_preview); self._report_result(result, "Metadata batch complete"); self._refresh_metadata(); return result

    def _request_file(self, initial, save=True):
        try: return self.app.fusion.RequestFile(str(initial), "", {"FReqB_Saving": bool(save)})
        except Exception:
            try: return self.app.fusion.RequestFile(str(initial))
            except Exception: return None

    def _export_metadata_csv(self, event=None):
        path = self._request_file(user_data_dir() / "metadata.csv")
        if path:
            self.app.metadata.export_csv(self.metadata_records, path); self._set_status("Metadata CSV exported")

    def _import_metadata_csv(self, event=None):
        path = self._request_file(user_data_dir(), save=False)
        if path:
            try: self.metadata_preview = self.app.metadata.preview_csv_import(self.metadata_records, path); self._show_preview("Import Metadata CSV", self.metadata_preview, self._apply_metadata_preview)
            except Exception as exc: self._set_status("Could not read CSV: %s" % exc, True)

    def _refresh_rename(self, event=None):
        self._refresh_selection()
        if not self.selection:
            self._warning("RenameWarning", "Choose an available clip selection source."); self._populate_tree("RenameTree", []); return
        self._warning("RenameWarning"); self.metadata_records = self.app.metadata.build_records(self.selection.clips, self.selection.timeline_items); self._preview_rename(pop_window=False)

    def _preview_rename(self, event=None, pop_window=True):
        items = self.window.GetItems()
        try: start, width = int(items["RenameStart"].Text or 1), int(items["RenameWidth"].Text or 0)
        except ValueError: start, width = 1, 0
        indices = self._tree_selected_indices(items["RenameTree"]) if pop_window else []
        records = [self.metadata_records[index] for index in indices if 0 <= index < len(self.metadata_records)] or self.metadata_records
        self.rename_preview = self.app.rename.preview(records, items["RenameTemplate"].Text, items["RenamePrefix"].Text, items["RenameSuffix"].Text, items["RenameFind"].Text, items["RenameReplace"].Text, bool(items["RenameRegex"].Checked), bool(items["RenameWhitespace"].Checked), True, self._combo_text("RenameCase"), start, width)
        rows = [(index, change.before, change.after, change.status) for index, change in enumerate(self.rename_preview.changes)]; self._populate_tree("RenameTree", rows); items["RenameCount"].Text = "%d clips · %d safe" % (len(rows), self.rename_preview.changed)
        if pop_window: self._show_preview("Rename Clips", self.rename_preview, self._apply_rename_preview)

    def _apply_rename(self, event=None):
        self._preview_rename(pop_window=True)

    def _apply_rename_preview(self):
        result = self.app.rename.apply_preview(self.rename_preview); self._report_result(result, "Rename complete"); self._refresh_rename(); return result

    def _save_rename_template(self, event=None):
        self.app.preferences.set("rename", "template", str(self.window.GetItems()["RenameTemplate"].Text)); self._set_status("Rename template saved")

    def _refresh_stills(self, event=None):
        context = self.app.context.refresh_context(); items = self.window.GetItems()
        folder = self.app.preferences.get("stills", "default_output_folder", "") or str(default_output_folder(context.project_name or "Project")); items["StillFolder"].Text = items["StillFolder"].Text or folder
        self._refresh_still_bins(); self._populate_still_tree()

    def _refresh_still_bins(self, event=None):
        context = self.app.context.refresh_context(); self.bin_entries = collect_bins(context.media_pool.GetRootFolder()) if context.media_pool else []
        self._fill_combo("StillBin", [path for path, _folder in self.bin_entries])

    def _populate_still_tree(self):
        rows = [(index, item.source_label, item.timecode, item.filename, item.status) for index, item in enumerate(self.still_queue)]; self._populate_tree("StillTree", rows); self.window.GetItems()["StillCount"].Text = "%d queued / captured" % len(rows)
        if not rows:
            self.window.GetItems()["StillPreview"].Text = "Select a queued still"; self.window.GetItems()["StillPreviewSource"].Text = ""

    def _still_selected(self, event=None):
        item = self._current_still(); items = self.window.GetItems()
        if not item:
            items["StillPreview"].Text = "Select a queued still"; items["StillPreviewSource"].Text = ""; return
        items["StillPreviewSource"].Text = "%s · %s · %s" % (item.source_label, item.timecode, item.status)
        path = Path(item.thumbnail_path) if item.thumbnail_path else None
        if not path or not path.is_file():
            context = self.app.context.refresh_context()
            if context.timeline_id != item.timeline_id:
                items["StillPreview"].Text = "Source timeline is not active"; return
            key = self.app.thumbnails.cache_key(context.project_id, item.timeline_id, item.source_id, item.frame, "still-queue")
            cached = self.app.thumbnails.get(key)
            if not cached:
                result = self.app.thumbnails.generate(context.timeline, item.frame, key, self.app.context.get_project_fps())
                if not result.success:
                    items["StillPreview"].Text = "Preview unavailable"; self._report_result(result, "Still preview"); return
                cached = Path(result.details[0]["path"])
            item.thumbnail_path = str(cached); path = cached
        items["StillPreview"].Text = ""
        try: items["StillPreview"].Pixmap = str(path)
        except Exception: items["StillPreview"].Text = str(path)

    def _build_still_queue(self, event=None):
        context = self.app.context.refresh_context()
        if not context.timeline: self._warning("StillWarning", "Open a timeline first."); return
        template = self.window.GetItems()["StillTemplate"].Text; fps = self.app.context.get_project_fps(); source = self._combo_text("StillSource")
        if source == "Selected Markers": markers = self._selected_markers() or self.filtered_markers
        elif source == "Visible Markers": markers = self.filtered_markers or self.app.markers.list_markers(context.timeline)
        else: markers = None
        if markers is not None:
            self.still_queue = self.app.stills.queue_from_markers(markers, template, fps, context.project_name, context.timeline_name, context.timeline)
        else:
            self._refresh_selection(); timeline_items = self.selection.timeline_items if self.selection else []
            self.still_queue = self.app.stills.queue_from_timeline_items(timeline_items, self._combo_text("StillClipPosition"), template, fps, context.project_name, context.timeline_name, context.timeline)
        self.app.stills.detect_conflicts(self.still_queue, self.window.GetItems()["StillFolder"].Text); self._populate_still_tree(); self._set_status("Still queue built · %d items" % len(self.still_queue))

    def _capture_still_queue(self, event=None):
        if not self.still_queue: self._set_status("Build a still queue first."); return
        index = self.window.GetItems()["StillBin"].CurrentIndex; target = self.bin_entries[index][1] if 0 <= index < len(self.bin_entries) else None
        result = self.app.stills.execute_queue(self.still_queue, self.window.GetItems()["StillFolder"].Text, target, False); self._report_result(result, "Still queue complete"); self._populate_still_tree()

    def _clear_still_queue(self, event=None): self.still_queue = []; self._populate_still_tree(); self._set_status("Still queue cleared")

    def _remove_still_queue(self, event=None):
        indices = set(self._tree_selected_indices(self.window.GetItems()["StillTree"])); self.still_queue = [item for index, item in enumerate(self.still_queue) if index not in indices]; self._populate_still_tree()

    def _current_still(self):
        index = self._tree_current_index(self.window.GetItems()["StillTree"]); return self.still_queue[index] if 0 <= index < len(self.still_queue) else None

    def _navigate_still(self, event=None):
        item = self._current_still()
        if not item: return
        result = self.app.stills.navigate_to_source(item); self._report_result(result, "Navigated to still source")
        if not result.success: return
        if item.source_type == "marker":
            self._switch_workspace("Markers")
            for index, marker in enumerate(self.filtered_markers):
                if marker.stable_key == item.source_id:
                    self._select_tree_index(self.window.GetItems()["MarkerTree"], index)
                    self._marker_selected(); break
        elif item.source_type == "timeline_clip":
            try: clip_id = str(item.source_object.GetMediaPoolItem().GetUniqueId())
            except Exception: clip_id = ""
            self._switch_workspace("Metadata")
            for index, record in enumerate(self.metadata_records):
                if record.unique_id == clip_id:
                    self._select_tree_index(self.window.GetItems()["MetadataClipTree"], index)
                    self._metadata_selected(); break

    def _rename_queued_still(self, event=None):
        item = self._current_still(); name = str(self.window.GetItems()["QueuedStillName"].Text or "").strip()
        if not item or not name: self._set_status("Select a still and enter a name."); return
        from ..utils import png_filename
        if item.status == "Imported":
            self._set_status("Rename imported stills in Resolve; changing the source file would break the Media Pool link.", True); return
        if item.output_path:
            old = Path(item.output_path); new = old.with_name(png_filename(name))
            if new.exists(): self._set_status("That output name already exists.", True); return
            try: old.rename(new); item.output_path = str(new); item.thumbnail_path = str(new)
            except Exception as exc: self._set_status("Could not rename still: %s" % exc, True); return
        item.filename = png_filename(name); self._populate_still_tree(); self._set_status("Still renamed")

    def _import_captured_stills(self, event=None):
        context = self.app.context.refresh_context(); paths = [Path(item.output_path) for item in self.still_queue if item.output_path]
        if not context.project or not paths: self._set_status("No captured stills are available to import."); return
        index = self.window.GetItems()["StillBin"].CurrentIndex; target = self.bin_entries[index][1] if 0 <= index < len(self.bin_entries) else None
        result = self.app.stills._import_paths(context.project, target, paths)
        if result.success:
            for item in self.still_queue:
                if item.output_path: item.status = "Imported"
            self._populate_still_tree()
        self._report_result(result, "Stills imported")

    def _browse_still_folder(self, event=None):
        selected = self.app.fusion.RequestDir(str(self.window.GetItems()["StillFolder"].Text))
        if selected: self.window.GetItems()["StillFolder"].Text = str(selected)

    def _grab_current_still(self, event=None):
        try: context = self.app.stills.capture_current_frame()
        except StillError as exc: self._warning("StillWarning", str(exc)); return
        self.capture_context = context; self._refresh_save_still_bins(); items = self.still_window.GetItems()
        items["CapturedTimeline"].Text = context["timeline_name"]; items["CapturedTimecode"].Text = context["timecode"]; items["CapturedPage"].Text = context["page"]
        items["StillFilename"].Text = Path(context["filename"]).stem; items["SaveStillFolder"].Text = str(context["folder"]); items["SaveStillStatus"].Text = "Still captured."
        self.window.Hide(); self.still_window.Show(); self.still_window.Raise()
        try: items["StillFilename"].SetFocus(); items["StillFilename"].SelectAll()
        except Exception: pass

    def _refresh_save_still_bins(self, event=None):
        if not self.capture_context: return
        project = self.capture_context["project"]; pool = project.GetMediaPool(); self.bin_entries = collect_bins(pool.GetRootFolder()); current = pool.GetCurrentFolder(); selected = 0
        names = []
        for index, (path, folder) in enumerate(self.bin_entries):
            names.append(path)
            try:
                if folder.GetUniqueId() == current.GetUniqueId(): selected = index
            except Exception: pass
        self._fill_combo("SaveStillBin", names, names[selected] if names else None, self.still_window)

    def _confirm_save_still(self, event=None):
        items = self.still_window.GetItems(); index = items["SaveStillBin"].CurrentIndex; target = self.bin_entries[index][1] if 0 <= index < len(self.bin_entries) else None
        try:
            destination = self.app.stills.save_and_import(self.capture_context["project"], target, items["SaveStillFolder"].Text, items["StillFilename"].Text)
            self.capture_context = None; self.still_window.Hide(); self.window.Show(); self.window.Raise(); self._switch_workspace("Stills"); self._set_status("Saved · %s" % destination.name)
        except StillError as exc: items["SaveStillStatus"].Text = str(exc)

    def _cancel_save_still(self, event=None):
        self.app.stills.cleanup_preview(); self.capture_context = None; self.still_window.Hide(); self.window.Show(); self.window.Raise(); self._set_status("Cancelled")

    def _browse_save_still_folder(self, event=None):
        items = self.still_window.GetItems(); selected = self.app.fusion.RequestDir(str(items["SaveStillFolder"].Text))
        if selected: items["SaveStillFolder"].Text = str(selected)

    def _refresh_health(self, event=None):
        if self.health_report:
            self._populate_health_tree()

    def _scan_health(self, event=None):
        self._refresh_selection()
        if not self.selection: self._warning("HealthWarning", "Choose an available selection source."); return
        records = self.app.metadata.build_records(self.selection.clips, self.selection.timeline_items); fps = self.app.context.get_project_fps(); prefs = self.app.preferences
        used_ids = set()
        try:
            current_timeline = self.app.selection.get_current_timeline_items(); used_ids = {record.unique_id for record in self.app.metadata.build_records(current_timeline.clips, current_timeline.timeline_items)}
        except Exception: pass
        self.health_report = self.app.health.scan(records, fps, prefs.get("health", "expected_resolutions", []), prefs.get("metadata", "required_fields", []), prefs.get("health", "expected_codecs", []), prefs.get("health", "short_clip_frames", 12), used_ids, self.selection_mode)
        categories = ["All"] + sorted({item.category for item in self.health_report.issues}); self._fill_combo("HealthCategory", categories, "All"); self._populate_health_tree(); self._set_status("Health scan complete · %d issues" % len(self.health_report.issues))

    def _populate_health_tree(self):
        category = self._combo_text("HealthCategory"); self.health_issues = self.app.health.filter_issues(self.health_report, category)
        rows = [(index, item.category, item.severity, item.clip_name, item.message, item.expected, item.actual) for index, item in enumerate(self.health_issues)]; self._populate_tree("HealthTree", rows)
        summary = self.health_report.summary(); self.window.GetItems()["HealthSummary"].Text = "  ".join("%s %s" % pair for pair in summary.items()); self.window.GetItems()["HealthCount"].Text = "%d issues" % len(self.health_issues)
        skipped = "; ".join("%s: %s" % item for item in self.health_report.skipped_checks.items()); self._warning("HealthWarning", skipped)

    def _export_health(self, suffix):
        if not self.health_report: self._set_status("Run a health scan first."); return
        path = self._request_file(user_data_dir() / ("media-health." + suffix))
        if path:
            path = str(path)
            if not path.lower().endswith("." + suffix): path += "." + suffix
            self.app.health.export(self.health_report, path); self._set_status("Health report exported")

    def _step_health(self, direction):
        tree = self.window.GetItems()["HealthTree"]; index = self._tree_current_index(tree); _issue, index = self.app.navigation.adjacent(self.health_issues, index, direction)
        if index >= 0:
            self._select_tree_index(tree, index)

    def _go_to_health(self, event=None):
        index = self._tree_current_index(self.window.GetItems()["HealthTree"])
        if not (0 <= index < len(self.health_issues)): return
        identity = self.health_issues[index].clip_id; record = self.app.metadata._clips.get(identity); context = self.app.context.refresh_context()
        try: success = bool(context.media_pool.SetSelectedClip(record.media_pool_item)) if record and context.media_pool else False
        except Exception: success = False
        self._set_status("Problem clip revealed" if success else "Resolve could not reveal this clip.", not success)

    def _ignore_health(self, event=None):
        index = self._tree_current_index(self.window.GetItems()["HealthTree"])
        if 0 <= index < len(self.health_issues):
            issue = self.health_issues[index]; self.health_report.issues.remove(issue); self._populate_health_tree(); self._set_status("Ignored for this session")

    def _refresh_history(self, event=None):
        rows = [(index, record.timestamp.strftime("%H:%M:%S"), record.label, len(record.object_ids), "Available" if record.reversible else "—") for index, record in enumerate(reversed(self.app.history.records))]; self._populate_tree("HistoryTree", rows); self.window.GetItems()["HistoryCount"].Text = "%d operations" % len(rows)

    def _undo(self, event=None):
        result = self.app.history.undo(); self._report_result(result, "Undo complete"); self._refresh_history(); self._refresh_workspace()

    def _refresh_settings(self, event=None):
        presets = self.app.preferences.get("markers", "presets", [])
        rows = [(index, value.get("name", ""), value.get("color", ""), value.get("default_marker_name", ""), value.get("default_duration_frames", 1)) for index, value in enumerate(presets)]
        self._populate_tree("PresetTree", rows)

    def _preset_selected(self, event=None):
        index = self._tree_current_index(self.window.GetItems()["PresetTree"]); presets = self.app.preferences.get("markers", "presets", [])
        if not (0 <= index < len(presets)): return
        value = presets[index]; items = self.window.GetItems(); items["PresetName"].Text = value.get("name", ""); items["PresetDefaultName"].Text = value.get("default_marker_name", ""); items["PresetDuration"].Text = str(value.get("default_duration_frames", 1)); self._fill_combo("PresetColor", MARKER_COLORS, value.get("color", "Blue"))

    def _preset_value(self):
        items = self.window.GetItems()
        try: duration = max(1, int(items["PresetDuration"].Text or 1))
        except ValueError: duration = 1
        name = str(items["PresetName"].Text or "Preset").strip() or "Preset"
        return {"name": name, "color": self._combo_text("PresetColor"), "default_marker_name": str(items["PresetDefaultName"].Text or name), "default_duration_frames": duration, "note_template": "", "custom_data": {"type": name.lower().replace(" ", "_")}}

    def _save_presets(self, presets):
        self.app.preferences.set("markers", "presets", presets); self._fill_combo("MarkerPreset", [item["name"] for item in presets]); self._refresh_settings()

    def _add_preset(self, event=None):
        presets = list(self.app.preferences.get("markers", "presets", [])); presets.append(self._preset_value()); self._save_presets(presets); self._set_status("Preset added")

    def _update_preset(self, event=None):
        index = self._tree_current_index(self.window.GetItems()["PresetTree"]); presets = list(self.app.preferences.get("markers", "presets", []))
        if 0 <= index < len(presets): presets[index] = self._preset_value(); self._save_presets(presets); self._set_status("Preset updated")

    def _move_preset(self, direction):
        index = self._tree_current_index(self.window.GetItems()["PresetTree"]); presets = list(self.app.preferences.get("markers", "presets", [])); target = index + direction
        if 0 <= index < len(presets) and 0 <= target < len(presets): presets[index], presets[target] = presets[target], presets[index]; self._save_presets(presets); self._set_status("Preset reordered")

    def _delete_preset(self, event=None):
        index = self._tree_current_index(self.window.GetItems()["PresetTree"]); presets = list(self.app.preferences.get("markers", "presets", []))
        if 0 <= index < len(presets): presets.pop(index); self._save_presets(presets); self._set_status("Preset deleted")

    def _save_settings(self, event=None):
        items = self.window.GetItems(); prefs = self.app.preferences
        prefs.data["general"].update({"restore_last_workspace": bool(items["SettingRestoreWorkspace"].Checked), "restore_window_geometry": bool(items["SettingRestoreGeometry"].Checked), "confirm_destructive_batch": bool(items["SettingConfirmBatch"].Checked), "default_selection_source": self._combo_text("SettingDefaultSelection")})
        prefs.data["thumbnails"].update({"enabled": bool(items["SettingThumbnails"].Checked), "cache_folder": str(items["SettingCacheFolder"].Text)})
        try: prefs.data["markers"]["default_duration"] = max(1, int(items["SettingMarkerDuration"].Text))
        except ValueError: pass
        prefs.data["metadata"]["required_fields"] = [value.strip() for value in str(items["SettingRequiredMetadata"].Text).split(",") if value.strip()]
        prefs.data["stills"].update({"default_output_folder": str(items["SettingStillFolder"].Text), "naming_template": str(items["SettingStillTemplate"].Text)})
        prefs.save(); self.app.thumbnails.enabled = prefs.data["thumbnails"]["enabled"]; self.app.thumbnails.folder = Path(prefs.data["thumbnails"]["cache_folder"]); items["SettingsStatus"].Text = "Saved"; self._set_status("Settings saved")

    def _browse_cache_folder(self, event=None):
        selected = self.app.fusion.RequestDir(str(self.window.GetItems()["SettingCacheFolder"].Text))
        if selected: self.window.GetItems()["SettingCacheFolder"].Text = str(selected)

    def _clear_thumbnail_cache(self, event=None): self._set_status("Cleared %d cached thumbnails" % self.app.thumbnails.clear())

    def _show_preview(self, title, preview, callback):
        self.preview_data, self.preview_callback = preview, callback; items = self.preview_window.GetItems(); items["PreviewTitle"].Text = title; items["PreviewSummary"].Text = "%d will change · %d unchanged · %d conflicts" % (preview.changed, preview.unchanged, preview.conflicts)
        target = items["PreviewTree"]; target.Clear()
        for change in preview.changes:
            row = target.NewItem()
            for column, value in enumerate((change.label, change.field, change.before, change.after, change.status)): row.Text[column] = str(value)
            target.AddTopLevelItem(row)
        self.preview_window.Show(); self.preview_window.Raise()

    def _cancel_preview(self, event=None): self.preview_window.Hide(); self.preview_data = None; self.preview_callback = None; self._set_status("Preview cancelled")

    def _confirm_preview(self, event=None):
        callback = self.preview_callback; self.preview_window.Hide(); self.preview_data = None; self.preview_callback = None
        if callback: callback()

    def _report_result(self, result, success_text):
        if result.success:
            self._set_status("%s · %d changed · %d unchanged%s" % (success_text, result.changed, result.unchanged, (" · %d warnings" % len(result.warnings)) if result.warnings else ""))
        else:
            message = "; ".join(result.errors or ["Operation failed."]); self._set_status(message, True)

    def _close(self, event=None):
        if self.app.preferences.get("general", "restore_window_geometry", True):
            try:
                geometry = list(self.window.Geometry)
                if valid_window_geometry(geometry) == geometry:
                    self.app.preferences.set("general", "window_geometry", geometry)
            except Exception:
                pass
        self.app.stills.cleanup_preview(); self.preview_window.Hide(); self.still_window.Hide(); self.dispatcher.ExitLoop()

    def run(self):
        self.preview_window.Hide(); self.still_window.Hide(); self.window.GetItems()["WorkspaceStack"].CurrentIndex = WORKSPACES.index(self.workspace)
        for name in WORKSPACES: self.window.GetItems()["Nav" + name].StyleSheet = theme.NAV_ACTIVE if name == self.workspace else theme.NAV
        self._refresh_context(); self._refresh_workspace(); self.window.Show(); self.window.Raise(); self.dispatcher.RunLoop(); self.window.Hide(); self.preview_window.Hide(); self.still_window.Hide()
