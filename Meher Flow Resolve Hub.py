#!/usr/bin/env python3
"""DaVinci Resolve menu entry for Meher Flow Resolve Hub v0.3.20."""

import sys
import os
import platform
from pathlib import Path


def _script_directory():
    file_name = globals().get("__file__")
    if file_name:
        return Path(file_name).resolve().parent
    fusion_app = globals().get("fusion")
    if fusion_app:
        try:
            return Path(str(fusion_app.MapPath("Scripts:Utility")))
        except Exception:
            pass
    return Path.cwd()


def _runtime_directory():
    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Meher Flow" / "Resolve Hub" / "runtime"
    if platform.system() == "Windows":
        return Path(os.environ.get("APPDATA", str(Path.home()))) / "Meher Flow" / "Resolve Hub" / "runtime"
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))) / "meher-flow" / "resolve-hub" / "runtime"


for location in (_script_directory(), _runtime_directory()):
    if str(location) not in sys.path:
        sys.path.insert(0, str(location))

WINDOW_ID = "com.meher-flow.resolve-hub.v0320"


def _raise_existing(namespace):
    fusion_app = namespace.get("fusion")
    try:
        existing = fusion_app.UIManager.FindWindow(WINDOW_ID)
    except Exception:
        existing = None
    if existing:
        # Resolve's UIManager can report Visible=True after Hide(), so checking
        # that property turns subsequent menu launches into repeated hides.
        # A Scripts-menu launch should reliably reveal the existing Hub; the
        # window's own close control remains the explicit way to hide it.
        try:
            existing.Show()
            existing.Raise()
        except Exception:
            pass
        return existing
    return None


def main(namespace=None):
    namespace = namespace or globals()
    existing = _raise_existing(namespace)
    if existing:
        return existing
    # Resolve keeps Python modules cached between script-menu launches. Reload the
    # runtime so an installed update does not require restarting Resolve.
    for module_name in list(sys.modules):
        if module_name == "meher_resolve_hub" or module_name.startswith("meher_resolve_hub."):
            sys.modules.pop(module_name, None)
    from meher_resolve_hub.app import main as hub_main
    return hub_main(namespace)


if __name__ == "__main__":
    main(globals())
