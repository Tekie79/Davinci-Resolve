"""History workspace layout."""

from .. import theme
from .components import button, section, tree


def build(ui):
    return ui.VGroup({"ID": "HistoryWorkspace", "Spacing": 7}, [section(ui, "History", "HistoryCount"), tree(ui, "HistoryTree", ("#", "Time", "Operation", "Objects", "Undo")), ui.HGroup({"Spacing": 5, "Weight": 0}, [ui.Label({"Text": "Undo validates current values and reports partial failures.", "StyleSheet": theme.SUBTITLE, "Weight": 0}), ui.HGap(0, 1), button(ui, "UndoHistory", "Undo Last", True)])])
