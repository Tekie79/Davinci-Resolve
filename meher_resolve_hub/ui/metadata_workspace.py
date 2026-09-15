"""Metadata workspace layout."""

from .. import theme
from .components import button, combo, line_edit, section, tree, warning_panel


def build(ui):
    return ui.VGroup({"ID": "MetadataWorkspace", "Spacing": 7}, [
        section(ui, "Metadata", "MetadataCount"),
        ui.HGroup({"Spacing": 6, "Weight": 0}, [line_edit(ui, "MetadataSearch", "Search clips…"), combo(ui, "MetadataMissingField"), button(ui, "RefreshMetadata", "Refresh")]),
        warning_panel(ui, "MetadataWarning"),
        ui.HGroup({"Spacing": 8}, [
            ui.VGroup({"Weight": 3, "Spacing": 6, "StyleSheet": theme.SURFACE}, [tree(ui, "MetadataClipTree", ("#", "Clip", "Scene", "Take", "Camera", "Reel")), ui.HGroup({"Spacing": 5, "Weight": 0}, [button(ui, "MetadataPrevious", "Previous"), button(ui, "MetadataReveal", "Reveal"), button(ui, "MetadataNext", "Next")])]),
            ui.VGroup({"Weight": 4, "Spacing": 6, "StyleSheet": theme.SURFACE}, [
                ui.Label({"ID": "MetadataLargeThumb", "Text": "Thumbnail not cached", "MinimumSize": [320, 150], "Alignment": {"AlignHCenter": True, "AlignVCenter": True}, "StyleSheet": theme.SURFACE_ALT}),
                button(ui, "RefreshMetadataThumb", "Refresh Thumbnail"),
                ui.Label({"ID": "MetadataClipName", "Text": "Select a clip", "StyleSheet": theme.SECTION, "Weight": 0}),
                ui.HGroup({"Spacing": 5, "Weight": 0}, [combo(ui, "MetadataField", 1), line_edit(ui, "MetadataValue", "Value"), button(ui, "SaveMetadataField", "Save", True)]),
                ui.Label({"Text": "BATCH EDIT", "StyleSheet": theme.SECTION, "Weight": 0}),
                ui.HGroup({"Spacing": 5, "Weight": 0}, [combo(ui, "MetadataBatchField", 1), combo(ui, "MetadataBatchOperation"), line_edit(ui, "MetadataBatchValue", "Value"), line_edit(ui, "MetadataBatchReplacement", "Replace / field")]),
                ui.CheckBox({"ID": "MetadataBlanksOnly", "Text": "Fill blanks only", "Checked": False, "Weight": 0}),
                ui.HGroup({"Spacing": 5, "Weight": 0}, [button(ui, "PreviewMetadataBatch", "Preview"), button(ui, "ApplyMetadataBatch", "Apply", True), ui.HGap(0, 1), button(ui, "ExportMetadataCSV", "Export CSV"), button(ui, "ImportMetadataCSV", "Import CSV")]),
            ]),
        ]),
    ])
