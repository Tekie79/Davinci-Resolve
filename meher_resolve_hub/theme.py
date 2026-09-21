"""Meher Flow Amber UIManager styles."""

COLORS = {
    "background": "#0B0B0C", "surface": "#141416", "surface_alt": "#1E1E21",
    "border": "#2C2C32", "border_strong": "#3A3A40", "text": "#FFFFFF",
    "text_secondary": "#A7A7AD", "amber": "#B77924", "amber_highlight": "#C58A35",
    "amber_border": "#5F4525", "success": "#22C55E", "warning": "#F59E0B",
    "error": "#EF4444", "info": "#3B82F6",
}

ROOT = "background-color:#0B0B0C;color:#FFFFFF;"
SURFACE = "background-color:#141416;border:1px solid #2C2C32;border-radius:7px;padding:7px;"
SURFACE_ALT = "background-color:#1E1E21;border:1px solid #2C2C32;border-radius:6px;padding:6px;"
TITLE = "font-size:20px;font-weight:700;color:#FFFFFF;"
SUBTITLE = "font-size:11px;color:#A7A7AD;"
SECTION = "font-size:12px;font-weight:700;color:#C58A35;"
PRIMARY = "background-color:#B77924;color:#0B0B0C;border:1px solid #C58A35;border-radius:6px;padding:7px;font-weight:700;"
SECONDARY = "background-color:#1E1E21;color:#FFFFFF;border:1px solid #3A3A40;border-radius:6px;padding:6px;"
DANGER = "background-color:#2A1517;color:#EF7777;border:1px solid #6B272B;border-radius:6px;padding:6px;font-weight:700;"
NAV = "background-color:#141416;color:#A7A7AD;border:1px solid #2C2C32;border-radius:6px;padding:8px;text-align:left;"
NAV_ACTIVE = "background-color:#1E1E21;color:#C58A35;border:1px solid #5F4525;border-radius:6px;padding:8px;text-align:left;font-weight:700;"
FIELD = "background-color:#1E1E21;color:#FFFFFF;border:1px solid #3A3A40;border-radius:5px;padding:5px;"
COLOR_SELECT = "background-color:#1E1E21;border:1px solid #3A3A40;border-radius:5px;padding:4px 6px;"
COLOR_SELECT_TEXT = "background:transparent;color:#FFFFFF;border:0;padding:2px;text-align:left;"
COLOR_SELECT_ARROW = "background:transparent;color:#A7A7AD;border:0;padding:2px;"
COLOR_PICKER = "background-color:#1E1E21;border:1px solid #3A3A40;border-radius:6px;padding:5px;"
COLOR_OPTION_ROW = "background:transparent;border:0;border-radius:4px;padding:0 5px;"
COLOR_OPTION_ROW_ACTIVE = "background-color:#5F4525;border:0;border-radius:4px;padding:0 5px;"
COLOR_OPTION = "background:transparent;color:#FFFFFF;border:0;padding:3px;text-align:left;"
COLOR_OPTION_ACTIVE = "background:transparent;color:#FFFFFF;border:0;padding:3px;text-align:left;font-weight:700;"
RANGE_SLIDER = "QSlider::groove:horizontal{height:4px;background:#3A3A40;border-radius:2px;}QSlider::sub-page:horizontal{background:#B77924;border-radius:2px;}QSlider::handle:horizontal{background:#C58A35;border:1px solid #E0AD62;width:14px;margin:-6px 0;border-radius:7px;}"
TABS = "QTabBar::tab{background:#141416;color:#A7A7AD;border:1px solid #2C2C32;padding:6px 12px;}QTabBar::tab:selected{background:#1E1E21;color:#C58A35;border-color:#5F4525;}"
# Geometry is identical in normal/hover/selected/focus states. Only paint changes.
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
    "border:2px solid #C58A35;border-radius:0;padding:3px;"
    "selection-background-color:#B77924;selection-color:#FFFFFF;}"
)
SELECTION_ACTIVE = "background-color:#1E1E21;color:#C58A35;border:1px solid #5F4525;border-radius:6px;padding:6px;"

STATUS = "background-color:#141416;color:#A7A7AD;border-top:1px solid #2C2C32;padding:6px;"
WARNING = "background-color:#2A2112;color:#F5B94C;border:1px solid #6B4A18;border-radius:6px;padding:7px;"
ERROR = "background-color:#2A1517;color:#EF7777;border:1px solid #6B272B;border-radius:6px;padding:7px;"
SUCCESS = "background-color:#14251B;color:#55CF7C;border:1px solid #285A38;border-radius:6px;padding:7px;"
