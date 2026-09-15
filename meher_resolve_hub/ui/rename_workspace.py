"""Rename workspace layout."""

from .. import theme
from .components import button, combo, line_edit, section, tree, warning_panel


def build(ui):
    return ui.VGroup({"ID": "RenameWorkspace", "Spacing": 7}, [
        section(ui, "Rename", "RenameCount"),
        warning_panel(ui, "RenameWarning"),
        ui.VGroup({"Spacing": 6, "StyleSheet": theme.SURFACE, "Weight": 0}, [
            ui.HGroup({"Spacing": 5}, [ui.Label({"Text": "Template", "StyleSheet": theme.SUBTITLE}), line_edit(ui, "RenameTemplate", "{Scene}_{Shot}_T{Take}"), button(ui, "SaveRenameTemplate", "Save Template")]),
            ui.HGroup({"Spacing": 5}, [line_edit(ui, "RenamePrefix", "Prefix"), line_edit(ui, "RenameSuffix", "Suffix"), line_edit(ui, "RenameFind", "Find"), line_edit(ui, "RenameReplace", "Replace"), ui.CheckBox({"ID": "RenameRegex", "Text": "Regex"}), ui.CheckBox({"ID": "RenameWhitespace", "Text": "Spaces → _"}), combo(ui, "RenameCase")]),
            ui.HGroup({"Spacing": 5}, [ui.Label({"Text": "Numbering", "StyleSheet": theme.SUBTITLE}), line_edit(ui, "RenameStart", "Start"), line_edit(ui, "RenameWidth", "Width"), ui.Label({"Text": "Tokens: {Original} {Scene} {Shot} {Take} {Camera} {Reel} {Index}", "StyleSheet": theme.SUBTITLE}), ui.HGap(0, 1), button(ui, "RefreshRename", "Refresh"), button(ui, "PreviewRename", "Preview"), button(ui, "ApplyRename", "Apply Safe", True)]),
        ]),
        tree(ui, "RenameTree", ("#", "Current Name", "New Name", "Status")),
    ])
