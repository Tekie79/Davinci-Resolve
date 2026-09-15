"""Still workspace layout."""

from .. import theme
from .components import button, combo, line_edit, section, tree, warning_panel


def build(ui):
    return ui.VGroup({"ID": "StillsWorkspace", "Spacing": 7}, [
        section(ui, "Stills", "StillCount"),
        warning_panel(ui, "StillWarning"),
        ui.VGroup({"Spacing": 6, "StyleSheet": theme.SURFACE, "Weight": 0}, [
            ui.HGroup({"Spacing": 5}, [ui.Label({"Text": "Source", "StyleSheet": theme.SUBTITLE}), combo(ui, "StillSource"), combo(ui, "StillClipPosition"), ui.Label({"Text": "Naming", "StyleSheet": theme.SUBTITLE}), line_edit(ui, "StillTemplate", "{Timeline}_{Timecode}_{Index}"), button(ui, "BuildStillQueue", "Build Queue")]),
            ui.HGroup({"Spacing": 5}, [ui.Label({"Text": "Folder", "StyleSheet": theme.SUBTITLE}), line_edit(ui, "StillFolder", "Output folder"), button(ui, "BrowseStillFolder", "Browse…"), ui.Label({"Text": "Bin", "StyleSheet": theme.SUBTITLE}), combo(ui, "StillBin"), button(ui, "RefreshStillBins", "Refresh")]),
            ui.HGroup({"Spacing": 5}, [button(ui, "GrabCurrentStill", "Grab Current Frame", True), button(ui, "CaptureStillQueue", "Capture Queue", True), button(ui, "RemoveStillQueue", "Remove"), button(ui, "ClearStillQueue", "Clear")]),
        ]),
        ui.HGroup({"Spacing": 8}, [
            tree(ui, "StillTree", ("#", "Source", "Frame", "Output", "Status"), 3),
            ui.VGroup({"Weight": 1, "Spacing": 5, "StyleSheet": theme.SURFACE}, [
                ui.Label({"Text": "STILL PREVIEW", "StyleSheet": theme.SECTION, "Weight": 0}),
                ui.Label({"ID": "StillPreview", "Text": "Select a queued still", "Alignment": {"AlignHCenter": True, "AlignVCenter": True}, "MinimumSize": [200, 120], "StyleSheet": theme.SURFACE_ALT, "Weight": 1}),
                ui.Label({"ID": "StillPreviewSource", "Text": "", "WordWrap": True, "StyleSheet": theme.SUBTITLE, "Weight": 0}),
            ]),
        ]),
        ui.HGroup({"Spacing": 5, "Weight": 0}, [ui.Label({"ID": "StillSelectionCount", "Text": "0 selected", "StyleSheet": theme.SUBTITLE, "Weight": 0}), line_edit(ui, "QueuedStillName", "New queue name"), button(ui, "RenameQueuedStill", "Rename"), ui.HGap(0, 1), button(ui, "NavigateStill", "Go To Source"), button(ui, "ImportCapturedStills", "Import to Bin")]),
    ])
