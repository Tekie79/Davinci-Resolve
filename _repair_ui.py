"""One-shot UI migration, removed once the repaired source passes tests."""
from _repair_backend import ROOT, put_method, replace_once, transform_method

SHELL = "meher_resolve_hub/ui/shell.py"


def apply():
    theme = "meher_resolve_hub/theme.py"
    path = ROOT / theme
    text = path.read_text(encoding="utf-8")
    start = text.index('TREE = ')
    end = text.index('\nSTATUS = ', start)
    text = text[:start] + '''# Geometry is identical in normal/hover/selected/focus states. Only paint changes.
TREE = (
    "QTreeWidget{background:#141416;color:#FFFFFF;border:1px solid #2C2C32;"
    "alternate-background-color:#18181B;outline:0;}"
    "QTreeWidget QHeaderView::section{background:#1E1E21;color:#A7A7AD;border:0;"
    "border-bottom:1px solid #2C2C32;padding:7px 5px;min-height:28px;font-weight:700;}"
    "QTreeWidget::item,QTreeWidget::item:hover,QTreeWidget::item:selected,"
    "QTreeWidget::item:selected:!active,QTreeWidget::item:focus{"
    "padding:5px;border:0;margin:0;font-weight:400;}"
    "QTreeWidget::item:selected,QTreeWidget::item:selected:!active{background:#3A3A40;}"
)
MARKER_TREE = TREE + (
    "QTreeWidget::item{height:64px;}"
    "QTreeWidget QLineEdit{background:#0B0B0C;color:#FFFFFF;"
    "border:1px solid #C58A35;border-radius:0;padding:4px;"
    "selection-background-color:#B77924;selection-color:#FFFFFF;}"
)
SELECTION_ACTIVE = "background-color:#1E1E21;color:#C58A35;border:1px solid #5F4525;border-radius:6px;padding:6px;"
''' + text[end:]
    path.write_text(text, encoding="utf-8")
    components = "meher_resolve_hub/ui/components.py"
    replace_once(components, 'properties["StyleSheet"] = style_sheet or theme.TREE', '''properties.update({"UniformRowHeights": True, "RootIsDecorated": False, "Indentation": 0, "WordWrap": False})
    if identity == "MarkerTree":
        # Logical selection is painted by the Hub. No native select/deselect
        # oscillation, and native highlight cannot hide marker colors.
        properties.update({"SelectionMode": "NoSelection", "IconSize": [96, 54]})
    properties["StyleSheet"] = style_sheet or theme.TREE''')
    marker_ui = "meher_resolve_hub/ui/marker_workspace.py"
    replace_once(marker_ui, '("#", "Name", "Color", "Start", "End", "Duration", "Notes")', '("Preview", "Name", "Color", "Start", "End", "Duration", "Notes")')
    replace_once(SHELL, '"MarkerTree": ("#", "Name", "Color", "Start", "End", "Duration", "Notes"),', '"MarkerTree": ("Preview", "Name", "Color", "Start", "End", "Duration", "Notes"),')
    replace_once(SHELL, 'from ..services.still_service import StillError, default_output_folder', 'from ..services.still_service import StillError, default_output_folder\nfrom ..services.marker_service import MarkerService')
    transform_method(SHELL, "ResolveHubShell", "__init__", 'self._marker_thumbnail_dirty = False', '''self._marker_thumbnail_dirty = False
        self._thumbnail_jobs = {}
        self._thumbnail_failures = set()
        self._thumbnail_idle_until = 0.0
        self._thumbnail_geometry = None
        self._displayed_thumbnail_token = None''')
    transform_method(SHELL, "ResolveHubShell", "_refresh_selection", 'theme.NAV_ACTIVE if mode == self.selection_mode else theme.SECONDARY', 'theme.SELECTION_ACTIVE if mode == self.selection_mode else theme.SECONDARY')
    # Context/status text is bounded so a long message or changing timecode cannot
    # force the root layout wider when a marker is clicked.
    replace_once(SHELL, '{"ID": "ContextTimecode", "Text": "—", "StyleSheet": theme.SECTION}', '{"ID": "ContextTimecode", "Text": "—", "StyleSheet": theme.SECTION, "MinimumSize": [105, 22], "MaximumSize": [105, 22], "Weight": 0}')
    replace_once(SHELL, '{"ID": "StatusText", "Text": "Ready", "StyleSheet": theme.SUBTITLE, "Weight": 0}', '{"ID": "StatusText", "Text": "Ready", "StyleSheet": theme.SUBTITLE, "MinimumSize": [120, 20], "MaximumSize": [520, 20], "Weight": 1}')
    replace_once(SHELL, '{"ID": "UndoText", "Text": "", "StyleSheet": theme.SUBTITLE, "Weight": 0}', '{"ID": "UndoText", "Text": "", "StyleSheet": theme.SUBTITLE, "MinimumSize": [100, 20], "MaximumSize": [280, 20], "Weight": 0}')
    transform_method(SHELL, "ResolveHubShell", "_populate_tree", 'item.SizeHint[column] = [0, 34]', 'item.SizeHint[column] = [0, 64]')
    transform_method(SHELL, "ResolveHubShell", "_populate_tree", 'if identity == "MarkerTree":', 'if identity == "MarkerTree":\n                item.Selected = False')
    # Remove native selection writes from BOTH paint paths. It is initialized
    # once above; clicking only paints fixed-size rows.
    transform_method(SHELL, "ResolveHubShell", "_apply_marker_color_swatches", 'item.Selected = False\n', '')
    transform_method(SHELL, "ResolveHubShell", "_paint_marker_rows", 'item.Selected = False\n', '')
    put_method(SHELL, "ResolveHubShell", "_paint_marker_rows", '''
def _paint_marker_rows(self, frames):
    if not frames:
        return
    tree = self.window.GetItems()["MarkerTree"]
    was_syncing = self._syncing_marker_selection
    was_populating = self._populating_marker_tree
    self._syncing_marker_selection = self._populating_marker_tree = True
    try:
        for index, marker in enumerate(self.filtered_markers):
            if marker.start_frame not in frames:
                continue
            item = tree.TopLevelItem(index)
            item.SetTextColor(2, marker_color_rgba(marker.color))
            selected = marker.start_frame in self._selected_marker_frames
            background = theme.COLORS["border_strong"] if selected else theme.COLORS["surface" if index % 2 == 0 else "surface_alt"]
            self._set_marker_row_background(item, background)
    finally:
        self._syncing_marker_selection = was_syncing
        self._populating_marker_tree = was_populating
''')
    put_method(SHELL, "ResolveHubShell", "_marker_table_column_widths", '''
@staticmethod
def _marker_table_column_widths(total_width):
    # Reserve scrollbar space at EVERY width; do not enforce an oversized table.
    usable = max(140, int(total_width) - 24)
    ratios = (0.18, 0.20, 0.09, 0.12, 0.12, 0.11, 0.18)
    widths = [int(usable * ratio) for ratio in ratios]
    widths[-1] += usable - sum(widths)
    return tuple(widths)
''')
    put_method(SHELL, "ResolveHubShell", "_resize_marker_thumbnail", '''
def _resize_marker_thumbnail(self, event=None):
    _x, _y, window_width, window_height = self._geometry_values(self.window.Geometry)
    geometry = (window_width, window_height)
    if getattr(self, "_thumbnail_geometry", None) == geometry:
        return
    self._thumbnail_geometry = geometry
    width, height = self._marker_thumbnail_dimensions(window_width, window_height)
    preview = self.window.GetItems()["MarkerThumb"]
    preview.IconSize = [width, height]
    preview.MinimumSize = [160, height + 12]
    preview.MaximumSize = [10000, height + 12]
    self._resize_marker_table_columns()
    self._resize_other_tree_columns()
''')
    put_method(SHELL, "ResolveHubShell", "_set_marker_thumbnail", '''
def _set_marker_thumbnail(self, path=None, empty_text="Thumbnail not available"):
    preview = self.window.GetItems()["MarkerThumb"]
    resolved, stamp = "", None
    if path:
        resolved = str(Path(path).resolve())
        try:
            stat = Path(resolved).stat()
            stamp = (stat.st_mtime_ns, stat.st_size)
        except OSError:
            pass
    token = (resolved, stamp, empty_text if not resolved else "")
    if token == getattr(self, "_displayed_thumbnail_token", None):
        return
    self._displayed_thumbnail_token = token
    # One icon assignment and one repaint. Never blank/repopulate or resize
    # the table during a click; geometry changes belong only to Resize.
    preview.Text = "" if resolved else "No preview"
    preview.ToolTip = resolved or empty_text
    preview.Icon = self.ui.Icon({"File": resolved})
    preview.Update()
''')
    put_method(SHELL, "ResolveHubShell", "_marker_click_modifiers", '''
@staticmethod
def _marker_click_modifiers(event):
    if not isinstance(event, dict):
        return ""
    value = event.get("modifiers", event.get("Modifiers", ""))
    if isinstance(value, dict):
        return " ".join(str(key) for key, enabled in value.items() if enabled).lower()
    if isinstance(value, int):
        return " ".join(name for mask, name in ((0x02000000, "shift"), (0x04000000, "control"), (0x08000000, "alt"), (0x10000000, "meta")) if value & mask)
    return str(value or "").lower()
''')
    put_method(SHELL, "ResolveHubShell", "_set_marker_item_editable", '''
@staticmethod
def _set_marker_item_editable(item, editable):
    try:
        flags = dict(item.GetFlags())
        if bool(flags.get("ItemIsEditable", False)) != bool(editable):
            flags["ItemIsEditable"] = bool(editable)
            item.SetFlags(flags)
        return True
    except Exception:
        return False
''')
    transform_method(SHELL, "ResolveHubShell", "_handle_marker_clicked", 'column not in (0, 2)', 'column not in (0, 2, 6)')
    transform_method(SHELL, "ResolveHubShell", "_handle_marker_clicked", 'marker = self._marker_from_event(event)', 'self._thumbnail_idle_until = time.monotonic() + 0.25\n        marker = self._marker_from_event(event)')
    put_method(SHELL, "ResolveHubShell", "_marker_double_clicked", '''
def _marker_double_clicked(self, event=None):
    item, column = self._marker_event_cell(event)
    if column in (0, 2, 6):
        if item is not None:
            self._set_marker_item_editable(item, False)
        if column == 6:
            # The list contains a shortened display value, not editable storage.
            items = self.window.GetItems()
            items["MarkerEditorTabs"].CurrentIndex = 0
            items["MarkerEditorStack"].CurrentIndex = 0
            items["MarkerNotes"].SetFocus()
        elif column == 0:
            self._go_to_marker(event)
        return
    self._go_to_marker(event)
''')
    transform_method(SHELL, "ResolveHubShell", "_marker_tree_item_changed", 'editable_columns = (1, 3, 4, 5, 6)', 'editable_columns = (1, 3, 4, 5)\n        if column == 6:\n            self._restore_marker_row(marker)\n            return')
    # A current TreeItem may remain after Clear Selection. Never treat it as an
    # active logical selection and accidentally mutate it.
    put_method(SHELL, "ResolveHubShell", "_current_marker", '''
def _current_marker(self):
    if self._active_marker_frame is not None:
        active = next((marker for marker in self.filtered_markers if marker.start_frame == self._active_marker_frame), None)
        if active:
            return active
    if hasattr(self, "_selected_marker_frames"):
        return next((marker for marker in self.filtered_markers if marker.start_frame in self._selected_marker_frames), None)
    return self._tree_marker()
''')
    put_method(SHELL, "ResolveHubShell", "_query_marker_records", '''
def _query_marker_records(self, records):
    items = self.window.GetItems()
    def value(identity, default):
        control = items.get(identity)
        if control is None:
            return default
        try:
            return str(control.CurrentText or default)
        except Exception:
            return default
    search = str(getattr(items.get("MarkerSearch"), "Text", "") or "")
    color = getattr(self, "_color_selection", {}).get("MarkerColor", "All")
    marker_type = value("MarkerType", "All")
    with_notes = True if marker_type == "With Notes" else False if marker_type == "Without Notes" else None
    return MarkerService.filter_markers(records, search, color, marker_type if marker_type in ("Point", "Range") else "All", with_notes, value("MarkerSort", "Timecode"))
''')
    put_method(SHELL, "ResolveHubShell", "_sync_marker_update", '''
def _sync_marker_update(self, original, candidate):
    filtered_index = self._replace_marker_in_collection(self.filtered_markers, original, candidate)
    self._replace_marker_in_collection(self.marker_records, original, candidate)
    if original.start_frame in self._selected_marker_frames:
        self._selected_marker_frames.discard(original.start_frame)
        self._selected_marker_frames.add(candidate.start_frame)
    if self._active_marker_frame == original.start_frame:
        self._active_marker_frame = candidate.start_frame
    if self._marker_selection_anchor == original.start_frame:
        self._marker_selection_anchor = candidate.start_frame
    recomputed = self._query_marker_records(self.marker_records)
    signature = lambda records: [(marker.scope_id, marker.start_frame) for marker in records]
    if signature(recomputed) != signature(self.filtered_markers):
        # Rebuild ONLY when filter membership/order actually changes.
        self._refresh_markers(records=self.marker_records)
        return
    self.filtered_markers = recomputed
    timeline_id = self._marker_state[0] if self._marker_state else candidate.scope_id
    self._marker_state = self._marker_state_signature(timeline_id, self.marker_records)
    if filtered_index >= 0:
        item = self.window.GetItems()["MarkerTree"].TopLevelItem(filtered_index)
        values = self._marker_row_values(filtered_index, candidate)
        was_populating = self._populating_marker_tree
        self._populating_marker_tree = True
        try:
            for column, value in enumerate(values):
                if str(item.Text[column]) != str(value):
                    item.Text[column] = str(value)
            item.SetTextColor(2, marker_color_rgba(candidate.color))
            selected = candidate.start_frame in self._selected_marker_frames
            background = theme.COLORS["border_strong"] if selected else theme.COLORS["surface" if filtered_index % 2 == 0 else "surface_alt"]
            self._set_marker_row_background(item, background)
        finally:
            self._populating_marker_tree = was_populating
    if self._active_marker_frame == candidate.start_frame:
        self._sync_marker_editor_fields(candidate)
    self.window.GetItems()["MarkerSelectionCount"].Text = "%d selected" % len(self._selected_marker_frames)
''')
    put_method(SHELL, "ResolveHubShell", "_commit_marker_update", '''
def _commit_marker_update(self, original, candidate, label, success_text):
    try:
        result = self.app.markers.replace_marker(original, candidate, label=label)
    except Exception as exc:
        result = OperationResult(False, failed=1, errors=[str(exc)])
    self._report_result(result, success_text)
    if result.success:
        range_changed = (original.start_frame, original.end_frame, original.duration_frames) != (candidate.start_frame, candidate.end_frame, candidate.duration_frames)
        if original.start_frame != candidate.start_frame:
            candidate.thumbnail_path = None
        if range_changed:
            self._marker_thumbnail_dirty = True
        self._sync_marker_update(original, candidate)
        if range_changed and hasattr(self, "window"):
            # End-only changes reuse the same start-frame image; moves invalidate it.
            if original.start_frame != candidate.start_frame:
                self._set_marker_thumbnail(None, "Marker moved; preview refresh queued")
                self._paint_marker_thumbnail(candidate, None)
            self._queue_marker_thumbnail(candidate, delay=0.25)
    else:
        self._restore_marker_row(original)
    return result
''')
    put_method(SHELL, "ResolveHubShell", "_marker_thumbnail_key", '''
def _marker_thumbnail_key(self, marker, context=None):
    context = context or self.app.context.refresh_context()
    # Names, notes, and marker color do not alter the rendered image.
    return self.app.thumbnails.cache_key(context.project_id, context.timeline_id, "timeline-frame", marker.start_frame, "marker-start-v1")
''')
    transform_method(SHELL, "ResolveHubShell", "_get_or_create_marker_thumbnail", 'key = self.app.thumbnails.cache_key(context.project_id, context.timeline_id, marker.stable_key, marker.start_frame, marker.color + marker.name)', 'key = self._marker_thumbnail_key(marker, context)')
    transform_method(SHELL, "ResolveHubShell", "_get_or_create_marker_thumbnail", 'self._set_marker_thumbnail(None, "Loading thumbnail…")', '# Keep any current image visible until its replacement is ready.')
    put_method(SHELL, "ResolveHubShell", "_populate_marker_editor", '''
def _populate_marker_editor(self, marker):
    self._sync_marker_editor_fields(marker)
    self.window.GetItems()["MarkerSelectionCount"].Text = "%d selected" % len(self._selected_markers())
    context = self.app.context.refresh_context()
    path = self.app.thumbnails.get(self._marker_thumbnail_key(marker, context))
    marker.thumbnail_path = str(path) if path else None
    self._set_marker_thumbnail(path, "Preview queued" if self.app.thumbnails.enabled else "Thumbnails are disabled")
    self._marker_thumbnail_dirty = not bool(path)
    self._paint_marker_thumbnail(marker, path)
    if not path:
        self._queue_marker_thumbnail(marker, delay=0.25)
''')
    put_method(SHELL, "ResolveHubShell", "_paint_marker_thumbnail", '''
def _paint_marker_thumbnail(self, marker, path):
    index = next((index for index, value in enumerate(self.filtered_markers) if value.scope_id == marker.scope_id and value.start_frame == marker.start_frame), None)
    if index is None:
        return
    was_populating = self._populating_marker_tree
    self._populating_marker_tree = True
    try:
        row = self.window.GetItems()["MarkerTree"].TopLevelItem(index)
        row.Icon[0] = self.ui.Icon({"File": str(path) if path else ""})
    except Exception:
        # Image support varies; editing and navigation remain available.
        pass
    finally:
        self._populating_marker_tree = was_populating
''')
    put_method(SHELL, "ResolveHubShell", "_queue_marker_thumbnail", '''
def _queue_marker_thumbnail(self, marker, delay=0.0, force=False):
    if not self.app.thumbnails.enabled:
        return
    context = self.app.context.refresh_context()
    if not context.timeline or marker.scope_id != context.timeline_id:
        return
    if not hasattr(self, "_thumbnail_jobs"):
        self._thumbnail_jobs, self._thumbnail_failures = {}, set()
    key = self._marker_thumbnail_key(marker, context)
    if force:
        self._thumbnail_failures.discard(key)
    elif key in self._thumbnail_failures:
        return
    if key not in self._thumbnail_jobs or force:
        self._thumbnail_jobs[key] = (marker, context.project_id, context.timeline_id, time.monotonic() + delay, force)
    self._thumbnail_idle_until = max(getattr(self, "_thumbnail_idle_until", 0.0), time.monotonic() + delay)
''')
    put_method(SHELL, "ResolveHubShell", "_visible_markers", '''
def _visible_markers(self):
    tree = self.window.GetItems()["MarkerTree"]
    visible = []
    try:
        height = int(tree.Height())
        for index, marker in enumerate(self.filtered_markers):
            rect = tree.VisualItemRect(tree.TopLevelItem(index))
            _left, top, _width, row_height = self._geometry_values(rect, (0, -1, 0, 0))
            if row_height > 0 and top + row_height > 0 and top < height:
                visible.append(marker)
        return visible[:24]
    except Exception:
        # Older UIManager builds may not expose viewport rectangles.
        current = self._current_marker()
        return [current] if current else self.filtered_markers[:8]
''')
    put_method(SHELL, "ResolveHubShell", "_queue_visible_marker_thumbnails", '''
def _queue_visible_marker_thumbnails(self, force=False):
    if self.workspace != "Markers" or not self.app.thumbnails.enabled:
        return
    context = self.app.context.refresh_context()
    for marker in self._visible_markers():
        if marker.scope_id != context.timeline_id:
            continue
        path = self.app.thumbnails.get(self._marker_thumbnail_key(marker, context))
        if path and not force:
            if marker.thumbnail_path != str(path):
                marker.thumbnail_path = str(path)
                self._paint_marker_thumbnail(marker, path)
        else:
            self._queue_marker_thumbnail(marker, force=force)
''')
    put_method(SHELL, "ResolveHubShell", "_process_thumbnail_jobs", '''
def _process_thumbnail_jobs(self):
    jobs = getattr(self, "_thumbnail_jobs", {})
    if not jobs or self.workspace != "Markers" or self._loading_marker_thumbnail:
        return
    if time.monotonic() < getattr(self, "_thumbnail_idle_until", 0.0):
        return
    if getattr(self, "preview_callback", None) or getattr(self, "capture_context", None) or getattr(self, "_active_color_selector", None):
        return
    context = self.app.context.refresh_context()
    # Prefer the selected marker, then other visible rows. One job per loop.
    entries = sorted(jobs.items(), key=lambda pair: pair[1][0].start_frame != self._active_marker_frame)
    key, (marker, project_id, timeline_id, due, force) = entries[0]
    if time.monotonic() < due:
        return
    del jobs[key]
    if context.project_id != project_id or context.timeline_id != timeline_id:
        return
    current = next((value for value in self.marker_records if value.scope_id == marker.scope_id and value.start_frame == marker.start_frame), None)
    if current is None:
        return
    path = None if force else self.app.thumbnails.get(key)
    self._loading_marker_thumbnail = True
    try:
        if not path:
            absolute = int(context.timeline.GetStartFrame()) + current.start_frame
            result = self.app.thumbnails.generate(context.timeline, absolute, key, self.app.context.get_project_fps())
            if result.success and result.details:
                path = result.details[0]["path"]
            else:
                self._thumbnail_failures.add(key)
        current.thumbnail_path = str(path) if path else None
        self._paint_marker_thumbnail(current, path)
        if current.start_frame == self._active_marker_frame:
            self._set_marker_thumbnail(path, "Preview unavailable; use Refresh Thumb to retry")
            self._marker_thumbnail_dirty = not bool(path)
    finally:
        self._loading_marker_thumbnail = False
        self._thumbnail_idle_until = time.monotonic() + 0.05
''')
    put_method(SHELL, "ResolveHubShell", "_refresh_marker_thumb", '''
def _refresh_marker_thumb(self, event=None):
    marker = self._current_marker()
    if not marker:
        self._set_status("Select a marker first.")
        return
    self._queue_marker_thumbnail(marker, force=True)
    self._set_status("Thumbnail refresh queued")
''')
    put_method(SHELL, "ResolveHubShell", "_refresh_visible_marker_thumbs", '''
def _refresh_visible_marker_thumbs(self, event=None):
    self._queue_visible_marker_thumbnails(force=True)
    self._set_status("Visible thumbnail refresh queued")
''')
    transform_method(SHELL, "ResolveHubShell", "_marker_range_slider_changed", 'if self._syncing_marker_range_controls:', 'self._thumbnail_idle_until = time.monotonic() + 0.25\n        if self._syncing_marker_range_controls:')
    put_method(SHELL, "ResolveHubShell", "_marker_editor_has_draft", '''
def _marker_editor_has_draft(self):
    marker = self._current_marker()
    if not marker:
        return False
    items = self.window.GetItems()
    expected = {"MarkerName": marker.name, "MarkerStart": self._marker_timecode(marker), "MarkerEnd": self._marker_timecode(marker, True), "MarkerDuration": str(marker.duration_frames)}
    if any(str(items[key].Text) != value for key, value in expected.items()):
        return True
    return str(items["MarkerNotes"].PlainText) != marker.note
''')
    put_method(SHELL, "ResolveHubShell", "_sync_markers_if_changed", '''
def _sync_markers_if_changed(self, event=None):
    if self.workspace != "Markers" or self._loading_marker_thumbnail:
        return
    context = self.app.context.refresh_context()
    state = self._timeline_marker_state(context)
    if state is None or state == self._marker_state:
        return
    same_scope = self._marker_state and self._marker_state[0] == context.timeline_id
    if same_scope and self._marker_editor_has_draft():
        self._warning("MarkerWarning", "Markers changed in Resolve. Save or refresh your pending edit before synchronizing.")
        return
    records = self.app.markers.list_markers(context.timeline) if context.timeline else []
    if not same_scope:
        self._selected_marker_frames.clear()
        self._active_marker_frame = self._marker_selection_anchor = None
        self._thumbnail_jobs.clear()
    self._refresh_markers(context=context, records=records)
''')
    # Rebuilding the list is exceptional (filter/order/native changes). Preserve
    # the first visible row instead of jumping to the active row unconditionally.
    transform_method(SHELL, "ResolveHubShell", "_refresh_markers", 'current = self._current_marker()', 'visible_before = self._visible_markers() if self.filtered_markers else []\n        anchor_frame = visible_before[0].start_frame if visible_before else None\n        current = self._current_marker()')
    transform_method(SHELL, "ResolveHubShell", "_refresh_markers", 'else:\n            self._clear_marker_editor()', '''else:
            self._clear_marker_editor()
        if anchor_frame is not None:
            anchor_index = next((index for index, marker in enumerate(self.filtered_markers) if marker.start_frame == anchor_frame), None)
            if anchor_index is not None:
                try:
                    tree.ScrollToItem(tree.TopLevelItem(anchor_index))
                except Exception:
                    pass
        for marker in self.filtered_markers:
            if marker.thumbnail_path:
                self._paint_marker_thumbnail(marker, marker.thumbnail_path)
        self._queue_visible_marker_thumbnails()''')
    # A row edited at the same frame may be a new record after native refresh;
    # cache lookup repaints visible rows even if a record already has a path.
    transform_method(SHELL, "ResolveHubShell", "_clear_thumbnail_cache", 'removed = self.app.thumbnails.clear()', 'removed = self.app.thumbnails.clear()\n        self._thumbnail_jobs.clear()\n        self._thumbnail_failures.clear()\n        for value in self.marker_records:\n            value.thumbnail_path = None\n            self._paint_marker_thumbnail(value, None)')
    put_method(SHELL, "ResolveHubShell", "run", '''
def run(self):
    self.color_window.Hide(); self.preview_window.Hide(); self.still_window.Hide()
    self.window.GetItems()["WorkspaceStack"].CurrentIndex = WORKSPACES.index(self.workspace)
    for name in WORKSPACES:
        self.window.GetItems()["Nav" + name].StyleSheet = theme.NAV_ACTIVE if name == self.workspace else theme.NAV
    self._refresh_context(); self._refresh_workspace(); self.window.Show(); self.window.Raise()
    self._resize_marker_thumbnail()
    self._running = True
    next_marker_sync = time.monotonic() + 0.75
    next_visible_scan = time.monotonic() + 0.5
    while self._running:
        self.dispatcher.StepLoop()
        now = time.monotonic()
        try:
            if now >= next_marker_sync:
                self._sync_markers_if_changed()
                next_marker_sync = now + 0.75
            if now >= next_visible_scan:
                self._queue_visible_marker_thumbnails()
                next_visible_scan = now + 0.5
            self._process_thumbnail_jobs()
        except Exception as exc:
            self.app.logger.exception("Deferred marker refresh failed")
            self._set_status("Marker refresh failed: %s" % exc, True)
            self._thumbnail_jobs.clear()
        time.sleep(0.01)
    self.window.Hide(); self.color_window.Hide(); self.preview_window.Hide(); self.still_window.Hide()
''')


if __name__ == "__main__":
    apply()
