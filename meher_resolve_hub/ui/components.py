"""Small predictable UIManager component factories."""

from .. import theme


def button(ui, identity, text, primary=False, weight=0):
    return ui.Button({"ID": identity, "Text": text, "StyleSheet": theme.PRIMARY if primary else theme.SECONDARY, "Weight": weight})


def line_edit(ui, identity, placeholder="", read_only=False, weight=1):
    return ui.LineEdit({"ID": identity, "PlaceholderText": placeholder, "ReadOnly": read_only, "StyleSheet": theme.FIELD, "Weight": weight})


def combo(ui, identity, weight=0):
    return ui.ComboBox({"ID": identity, "StyleSheet": theme.FIELD, "Weight": weight})


def section(ui, title, count_id=None):
    children = [ui.Label({"Text": title.upper(), "StyleSheet": theme.SECTION, "Weight": 0})]
    if count_id:
        children.extend([ui.HGap(0, 1), ui.Label({"ID": count_id, "Text": "0", "StyleSheet": theme.SUBTITLE, "Weight": 0})])
    return ui.HGroup({"Spacing": 6, "Weight": 0}, children)


def tree(ui, identity, headers, weight=1):
    return ui.Tree({"ID": identity, "ColumnCount": len(headers), "HeaderLabels": list(headers), "AlternatingRowColors": True, "SelectionMode": "ExtendedSelection", "Weight": weight})


def warning_panel(ui, identity):
    return ui.Label({"ID": identity, "Text": "", "WordWrap": True, "Visible": False, "StyleSheet": theme.WARNING, "Weight": 0})


def empty_state(ui, identity, text):
    return ui.Label({"ID": identity, "Text": text, "Alignment": {"AlignHCenter": True, "AlignVCenter": True}, "StyleSheet": theme.SUBTITLE})
