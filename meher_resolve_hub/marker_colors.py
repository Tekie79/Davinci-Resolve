"""Shared Resolve marker colors for CSS controls."""

from .constants import MARKER_COLOR_HEX


def hex_color_rgba(value):
    """Return a Fusion UIManager color value for a CSS hex color."""
    normalized = str(value or "#737A84").lstrip("#")
    red, green, blue = (int(normalized[index:index + 2], 16) for index in (0, 2, 4))
    return {"R": red / 255.0, "G": green / 255.0, "B": blue / 255.0, "A": 1.0}


def marker_color_dot_style(color):
    """Return CSS for a circular color indicator beside a color control."""
    fill = MARKER_COLOR_HEX.get(color, "#737A84")
    return (
        "background-color:%s;"
        "border:0;"
        "border-radius:4px;"
        "padding:0;"
        "margin:0;" % fill
    )


def marker_color_rgba(color):
    """Return a Fusion UIManager color value for a named marker color."""
    return hex_color_rgba(MARKER_COLOR_HEX.get(color, "#737A84"))
