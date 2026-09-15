"""Media health workspace layout."""

from .. import theme
from .components import button, combo, section, tree, warning_panel


def build(ui):
    return ui.VGroup({"ID": "HealthWorkspace", "Spacing": 7}, [
        section(ui, "Media Health", "HealthCount"),
        ui.HGroup({"Spacing": 5, "Weight": 0}, [ui.Label({"Text": "Scope uses current Selection source", "StyleSheet": theme.SUBTITLE, "Weight": 0}), ui.HGap(0, 1), combo(ui, "HealthCategory"), button(ui, "ScanHealth", "Scan", True), button(ui, "ExportHealthCSV", "Export CSV"), button(ui, "ExportHealthJSON", "Export JSON")]),
        warning_panel(ui, "HealthWarning"),
        ui.Label({"ID": "HealthSummary", "Text": "Run a read-only scan.", "StyleSheet": theme.SURFACE, "Weight": 0}),
        tree(ui, "HealthTree", ("#", "Category", "Severity", "Clip", "Problem", "Expected", "Actual")),
        ui.HGroup({"Spacing": 5, "Weight": 0}, [button(ui, "PreviousHealth", "Previous Problem"), button(ui, "GoToHealth", "Go To"), button(ui, "IgnoreHealth", "Ignore for Session"), button(ui, "NextHealth", "Next Problem")]),
    ])
