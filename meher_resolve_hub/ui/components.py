"""Small predictable UIManager component factories."""

from .. import theme
from ..marker_colors import marker_color_dot_style


def button(ui, identity, text, primary=False, weight=0, style_sheet=None):
    return ui.Button({"ID": identity, "Text": text, "StyleSheet": style_sheet or (theme.PRIMARY if primary else theme.SECONDARY), "Weight": weight})


def line_edit(ui, identity, placeholder="", read_only=False, weight=1):
    return ui.LineEdit({"ID": identity, "PlaceholderText": placeholder, "ReadOnly": read_only, "StyleSheet": theme.FIELD, "Weight": weight})


def combo(ui, identity, weight=0):
    return ui.ComboBox({"ID": identity, "StyleSheet": theme.FIELD, "Weight": weight})


def color_dot(ui, identity, color="Blue"):
    return ui.Button({
        "ID": identity,
        "Text": "",
        "MinimumSize": [8, 8],
        "MaximumSize": [8, 8],
        "StyleSheet": marker_color_dot_style(color),
        "Weight": 0,
    })


def centered_color_dot(ui, identity, color="Blue"):
    return ui.VGroup({"ID": identity + "Wrap", "Spacing": 0, "Weight": 0}, [
        ui.VGap(0, 1),
        color_dot(ui, identity, color),
        ui.VGap(0, 1),
    ])


def color_selector(ui, identity, color="Blue", weight=0):
    """A compact CSS-only color field whose popup is managed by the shell."""
    return ui.HGroup({"ID": identity + "Field", "Spacing": 7, "MinimumSize": [88, 30], "MaximumSize": [10000, 30], "Weight": weight, "StyleSheet": theme.COLOR_SELECT}, [
        centered_color_dot(ui, identity + "Dot", color),
        ui.Button({"ID": identity, "Text": color, "Flat": True, "StyleSheet": theme.COLOR_SELECT_TEXT, "Weight": 1}),
        ui.Button({"ID": identity + "Arrow", "Text": "⌄", "Flat": True, "StyleSheet": theme.COLOR_SELECT_ARROW, "Weight": 0}),
    ])


def color_option(ui, color):
    token = color.replace(" ", "")
    return ui.HGroup({"ID": "ColorChoice" + token + "Row", "Spacing": 7, "MinimumSize": [0, 27], "MaximumSize": [10000, 27], "Weight": 0, "StyleSheet": theme.COLOR_OPTION_ROW}, [
        centered_color_dot(ui, "ColorChoice" + token + "Dot", color),
        ui.Button({"ID": "ColorChoice" + token, "Text": color, "Flat": True, "StyleSheet": theme.COLOR_OPTION, "Weight": 1}),
    ])


def section(ui, title, count_id=None):
    children = [ui.Label({"Text": title.upper(), "StyleSheet": theme.SECTION, "Weight": 0})]
    if count_id:
        children.extend([ui.HGap(0, 1), ui.Label({"ID": count_id, "Text": "0", "StyleSheet": theme.SUBTITLE, "Weight": 0})])
    return ui.HGroup({"Spacing": 6, "Weight": 0}, children)


def tree(ui, identity, headers, weight=1, style_sheet=None):
    properties = {"ID": identity, "ColumnCount": len(headers), "HeaderLabels": list(headers), "AlternatingRowColors": True, "SelectionMode": "ExtendedSelection", "Weight": weight}
    properties["StyleSheet"] = style_sheet or theme.TREE
    return ui.Tree(properties)


def warning_panel(ui, identity):
    return ui.Label({"ID": identity, "Text": "", "WordWrap": True, "Visible": False, "StyleSheet": theme.WARNING, "Weight": 0})


def empty_state(ui, identity, text):
    return ui.Label({"ID": identity, "Text": text, "Alignment": {"AlignHCenter": True, "AlignVCenter": True}, "StyleSheet": theme.SUBTITLE})
