"""Application constants and Resolve-facing enumerations."""

APP_NAME = "Meher Flow Resolve Hub"
SHORT_NAME = "Resolve Hub"
APP_VERSION = "0.5.0"
APP_SUBTITLE = "Advanced media, marker, and review tools for DaVinci Resolve"
MAIN_WINDOW_ID = "com.meher-flow.resolve-hub.v0400"
PREVIEW_WINDOW_ID = MAIN_WINDOW_ID + ".preview"
STILL_WINDOW_ID = MAIN_WINDOW_ID + ".save-still"
COLOR_PICKER_WINDOW_ID = MAIN_WINDOW_ID + ".color-picker"

WORKSPACES = ("Markers", "Metadata", "Rename", "Stills", "Health", "History", "Settings")
SELECTION_MODES = (
    "Media Pool Selection",
    "Timeline Selection",
    "Current Bin",
    "Current Bin + Sub-Bins",
    "Current Timeline",
)

MARKER_COLORS = (
    "Blue", "Cyan", "Green", "Yellow", "Red", "Pink", "Purple", "Fuchsia",
    "Rose", "Lavender", "Sky", "Mint", "Lemon", "Sand", "Cocoa", "Cream",
)

# Resolve exposes marker colors by name, but UIManager does not provide their
# swatches.  Keep one palette for every marker control so the editor and list
# always communicate the same color visually.
MARKER_COLOR_HEX = {
    "Blue": "#3C78D8",
    "Cyan": "#35C7D0",
    "Green": "#59B957",
    "Yellow": "#EACB42",
    "Red": "#E45151",
    "Pink": "#EF77A8",
    "Purple": "#8969D3",
    "Fuchsia": "#D754C5",
    "Rose": "#D86A7F",
    "Lavender": "#B8A5E3",
    "Sky": "#72B7E8",
    "Mint": "#75CBA8",
    "Lemon": "#DDE26A",
    "Sand": "#CDA96A",
    "Cocoa": "#8C674F",
    "Cream": "#E8DDBB",
}

DEFAULT_MARKER_PRESETS = [
    {"name": "Best Take", "color": "Green", "default_marker_name": "Best Take", "default_duration_frames": 1, "note_template": "", "custom_data": {"type": "best_take"}},
    {"name": "Strong Moment", "color": "Yellow", "default_marker_name": "Strong Moment", "default_duration_frames": 1, "note_template": "", "custom_data": {"type": "strong_moment"}},
    {"name": "Insert", "color": "Cyan", "default_marker_name": "Insert", "default_duration_frames": 1, "note_template": "", "custom_data": {"type": "insert"}},
    {"name": "VFX", "color": "Purple", "default_marker_name": "VFX", "default_duration_frames": 1, "note_template": "", "custom_data": {"type": "vfx"}},
    {"name": "Sound", "color": "Blue", "default_marker_name": "Sound", "default_duration_frames": 1, "note_template": "", "custom_data": {"type": "sound"}},
    {"name": "Continuity", "color": "Rose", "default_marker_name": "Continuity", "default_duration_frames": 1, "note_template": "", "custom_data": {"type": "continuity"}},
    {"name": "Review", "color": "Sand", "default_marker_name": "Review", "default_duration_frames": 1, "note_template": "", "custom_data": {"type": "review"}},
    {"name": "Problem", "color": "Red", "default_marker_name": "Problem", "default_duration_frames": 1, "note_template": "", "custom_data": {"type": "problem"}},
]
