"""Marker workspace layout."""

from .. import theme
from .components import button, color_selector, combo, line_edit, section, tree, warning_panel


def build(ui):
    return ui.VGroup({"ID": "MarkersWorkspace", "Spacing": 5, "Weight": 1}, [
        section(ui, "Markers", "MarkerCount"),
        ui.HGroup({"Spacing": 6, "Weight": 0}, [line_edit(ui, "MarkerSearch", "Search markers…"), color_selector(ui, "MarkerColor", "All"), combo(ui, "MarkerType"), combo(ui, "MarkerSort"), button(ui, "RefreshMarkers", "Refresh"), button(ui, "AddMarker", "+ Marker", True)]),
        warning_panel(ui, "MarkerWarning"),
        ui.HGroup({"Spacing": 8, "Weight": 1}, [
            ui.VGroup({"Weight": 5, "Spacing": 6, "StyleSheet": theme.SURFACE}, [
                tree(ui, "MarkerTree", ("#", "Name", "Color", "Start", "End", "Duration", "Notes"), style_sheet=theme.MARKER_TREE),
                ui.HGroup({"Spacing": 6, "Weight": 0}, [button(ui, "SelectAllMarkers", "Select All"), button(ui, "ClearMarkerSelection", "Clear"), ui.Label({"ID": "MarkerSelectionCount", "Text": "0 selected", "StyleSheet": theme.SUBTITLE, "Weight": 0}), ui.HGap(0, 1), button(ui, "PrevMarker", "Previous"), button(ui, "GoToMarker", "Go To"), button(ui, "NextMarker", "Next")]),
            ]),
            ui.VGroup({"Weight": 3, "Spacing": 6, "StyleSheet": theme.SURFACE}, [
                ui.Label({"Text": "MARKER EDITOR", "StyleSheet": theme.SECTION, "Weight": 0}),
                ui.Button({"ID": "MarkerThumb", "Text": "Select a marker", "Flat": True, "IconSize": [480, 270], "MinimumSize": [160, 90], "MaximumSize": [10000, 360], "StyleSheet": theme.SURFACE_ALT, "Weight": 0}),
                ui.HGroup({"Spacing": 5, "Weight": 0}, [button(ui, "RefreshMarkerThumb", "Refresh Thumb"), button(ui, "RefreshVisibleMarkerThumbs", "Refresh Visible"), ui.HGap(0, 1), button(ui, "PrevSameColor", "Prev Color"), button(ui, "NextSameColor", "Next Color")]),
                ui.TabBar({"ID": "MarkerEditorTabs", "Expanding": False, "DrawBase": True, "StyleSheet": theme.TABS, "Weight": 0}),
                ui.Stack({"ID": "MarkerEditorStack", "Weight": 1}, [
                    ui.VGroup({"Spacing": 5}, [
                        ui.HGroup({"Spacing": 6, "Weight": 0}, [ui.Label({"Text": "Name", "MinimumSize": [42, 0], "StyleSheet": theme.SUBTITLE, "Weight": 0}), line_edit(ui, "MarkerName", "Marker name")]),
                        ui.HGroup({"Spacing": 6, "Weight": 0}, [ui.Label({"Text": "Color", "MinimumSize": [42, 0], "StyleSheet": theme.SUBTITLE, "Weight": 0}), color_selector(ui, "MarkerEditColor", "Blue", 1)]),
                        ui.Label({"Text": "Notes", "StyleSheet": theme.SUBTITLE, "Weight": 0}), ui.TextEdit({"ID": "MarkerNotes", "StyleSheet": theme.FIELD, "Weight": 1}),
                        ui.HGroup({"Spacing": 5, "Weight": 0}, [button(ui, "SaveMarkerDetails", "Save", True), button(ui, "ClearMarkerNotes", "Clear"), ui.HGap(0, 1), button(ui, "DeleteMarker", "Delete", style_sheet=theme.DANGER), button(ui, "MarkerStill", "Grab Still")]),
                    ]),
                    ui.VGroup({"Spacing": 5}, [
                        ui.HGroup({"Spacing": 3, "Weight": 0}, [ui.Label({"Text": "Start", "MinimumSize": [34, 0], "StyleSheet": theme.SUBTITLE, "Weight": 0}), button(ui, "StartMinus10", "−10"), button(ui, "StartMinus5", "−5"), button(ui, "StartMinus1", "−1"), line_edit(ui, "MarkerStart", "HH:MM:SS:FF"), button(ui, "StartPlus1", "+1"), button(ui, "StartPlus5", "+5"), button(ui, "StartPlus10", "+10")]),
                        ui.HGroup({"Spacing": 3, "Weight": 0}, [ui.Label({"Text": "End", "MinimumSize": [34, 0], "StyleSheet": theme.SUBTITLE, "Weight": 0}), button(ui, "EndMinus10", "−10"), button(ui, "EndMinus5", "−5"), button(ui, "EndMinus1", "−1"), line_edit(ui, "MarkerEnd", "HH:MM:SS:FF"), button(ui, "EndPlus1", "+1"), button(ui, "EndPlus5", "+5"), button(ui, "EndPlus10", "+10")]),
                        ui.HGroup({"Spacing": 6, "Weight": 0}, [
                            ui.Label({"Text": "Start", "StyleSheet": theme.SUBTITLE, "Weight": 0}),
                            ui.Slider({"ID": "MarkerRangeStartSlider", "Orientation": "Horizontal", "Minimum": 0, "Maximum": 1, "Value": 0, "Tracking": True, "StyleSheet": theme.RANGE_SLIDER, "Weight": 1}),
                        ]),
                        ui.HGroup({"Spacing": 6, "Weight": 0}, [
                            ui.Label({"Text": "End", "StyleSheet": theme.SUBTITLE, "Weight": 0}),
                            ui.Slider({"ID": "MarkerRangeEndSlider", "Orientation": "Horizontal", "Minimum": 0, "Maximum": 1, "Value": 1, "Tracking": True, "StyleSheet": theme.RANGE_SLIDER, "Weight": 1}),
                        ]),
                        ui.HGroup({"Spacing": 5, "Weight": 0}, [ui.Label({"Text": "Duration", "StyleSheet": theme.SUBTITLE}), line_edit(ui, "MarkerDuration", "frames"), button(ui, "SaveMarkerRange", "Apply Range", True)]),
                        ui.HGroup({"Spacing": 5, "Weight": 0}, [button(ui, "SetMarkerStart", "Set Start"), button(ui, "SetMarkerEnd", "Set End"), button(ui, "MoveMarkerPlayhead", "Move Here"), button(ui, "GoToMarkerEnd", "Go To End")]),
                        ui.HGroup({"Spacing": 5, "Weight": 0}, [button(ui, "PlayMarkerRange", "Play Range")]),
                        ui.VGap(0, 1),
                    ]),
                    ui.VGroup({"Spacing": 6}, [
                        ui.Label({"Text": "BATCH EDIT", "StyleSheet": theme.SECTION, "Weight": 0}),
                        ui.HGroup({"Spacing": 5, "Weight": 0}, [combo(ui, "MarkerBatchField"), combo(ui, "MarkerBatchOperation"), line_edit(ui, "MarkerBatchValue", "Value")]),
                        ui.HGroup({"Spacing": 5, "Weight": 0}, [button(ui, "PreviewMarkerBatch", "Preview"), button(ui, "ApplyMarkerBatch", "Apply", True)]),
                        ui.Label({"Text": "PRESETS", "StyleSheet": theme.SECTION, "Weight": 0}),
                        ui.HGroup({"Spacing": 5, "Weight": 0}, [combo(ui, "MarkerPreset", 1), button(ui, "ApplyMarkerPreset", "Apply"), button(ui, "ManageMarkerPresets", "Manage")]),
                        ui.VGap(0, 1),
                    ]),
                ]),
            ]),
        ]),
    ])
