"""Cross-platform persistent Resolve Hub settings."""

import json
import os
import platform
from copy import deepcopy
from pathlib import Path

from .constants import DEFAULT_MARKER_PRESETS


DEFAULTS = {
    "general": {"restore_last_workspace": True, "restore_window_geometry": True, "default_selection_source": "Timeline Selection", "confirm_destructive_batch": True, "last_workspace": "Markers", "window_geometry": [120, 80, 1240, 780]},
    "thumbnails": {"enabled": True, "cache_folder": "", "width": 960, "height": 540},
    "markers": {"default_duration": 1, "nudge_steps": [1, 5, 10], "presets": DEFAULT_MARKER_PRESETS},
    "metadata": {"required_fields": ["Scene", "Take"]},
    "stills": {"default_output_folder": "", "default_target_bin": "current", "naming_template": "{Timeline}_{Timecode}_{Index}"},
    "health": {"expected_resolutions": [], "short_clip_frames": 12, "expected_codecs": []},
}


def valid_window_geometry(value):
    """Return a safe Resolve UIManager geometry or the application default.

    Some Resolve builds expose ``window.Geometry`` as a four-item placeholder
    (commonly ``[1, 2, 3, 4]``) instead of the real window rectangle.  Persisting
    that value makes the next launch look blank because the restored window is
    only a few pixels wide and high.
    """
    fallback = list(DEFAULTS["general"]["window_geometry"])
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return fallback
    try:
        geometry = [int(part) for part in value]
    except (TypeError, ValueError):
        return fallback
    _x, _y, width, height = geometry
    if width < 720 or height < 480 or width > 10000 or height > 10000:
        return fallback
    return geometry


def user_data_dir():
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Meher Flow" / "Resolve Hub"
    if system == "Windows":
        return Path(os.environ.get("APPDATA", str(Path.home()))) / "Meher Flow" / "Resolve Hub"
    return Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "meher-flow" / "resolve-hub"


def _merge(base, override):
    result = deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


class Preferences:
    def __init__(self, path=None):
        self.path = Path(path) if path else user_data_dir() / "settings.json"
        self.data = deepcopy(DEFAULTS)

    def load(self):
        if self.path.is_file():
            try:
                self.data = _merge(DEFAULTS, json.loads(self.path.read_text(encoding="utf-8")))
            except Exception:
                self.data = deepcopy(DEFAULTS)
        self.data.setdefault("general", {})["window_geometry"] = valid_window_geometry(
            self.data.get("general", {}).get("window_geometry")
        )
        return self.data

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.data, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(self.path)
        return self.path

    def get(self, section, key, default=None):
        return self.data.get(section, {}).get(key, default)

    def set(self, section, key, value, persist=True):
        self.data.setdefault(section, {})[key] = value
        if persist:
            self.save()
