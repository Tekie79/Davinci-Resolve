#!/usr/bin/env python3
"""Compatibility launcher for the renamed Meher Flow Resolve Hub.

Existing helper imports remain available so the v0.2.2 Grab Still regression
suite and third-party launch shortcuts continue to work during migration.
"""

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

from meher_resolve_hub.app import get_bmd_module, get_fusion_app, get_resolve_app
from meher_resolve_hub.resolve_context import ResolveContextService
from meher_resolve_hub.services.still_service import StillError as MediaManagerError
from meher_resolve_hub.services.still_service import StillService, default_output_folder, default_still_name
from meher_resolve_hub.utils import collect_bins, find_exported_png, png_filename, safe_filename_component, same_proxy as same_bin

APP_TITLE = "Meher Flow Resolve Hub"
APP_VERSION = "0.3.22"


class MediaManagerController:
    """Backward-compatible façade over the modular StillService."""

    def __init__(self, resolve_app):
        self.context_service = ResolveContextService(resolve_app)
        self.service = StillService(resolve_app, self.context_service)

    @property
    def resolve(self):
        return self.service.resolve

    @property
    def preview_dir(self):
        return self.service.preview_dir

    @preview_dir.setter
    def preview_dir(self, value):
        self.service.preview_dir = value

    @property
    def preview_path(self):
        return self.service.preview_path

    @preview_path.setter
    def preview_path(self, value):
        self.service.preview_path = value

    def project_and_timeline(self):
        context = self.context_service.refresh_context()
        if not context.project:
            raise MediaManagerError("Open a Resolve project first.")
        if not context.timeline:
            raise MediaManagerError("Open a timeline and place the playhead over visible video.")
        return context.project, context.timeline

    def current_context(self):
        context = self.context_service.refresh_context()
        if not context.project:
            raise MediaManagerError("Open a Resolve project first.")
        if not context.timeline:
            raise MediaManagerError("Open a timeline and place the playhead over visible video.")
        return {"project": context.project_name, "timeline": context.timeline_name, "timecode": context.current_timecode, "page": context.current_page or "Unknown"}

    def cleanup_preview(self):
        return self.service.cleanup_preview()

    def capture_current_frame(self):
        return self.service.capture_current_frame()

    def save_and_import(self, project, target_bin, folder_path, filename):
        return self.service.save_and_import(project, target_bin, folder_path, filename)


def main():
    existing = None
    try:
        existing = globals().get("fusion").UIManager.FindWindow("com.meher-flow.resolve-hub.v0322")
    except Exception:
        pass
    if existing:
        existing.Show(); existing.Raise(); return existing
    for module_name in list(sys.modules):
        if module_name == "meher_resolve_hub" or module_name.startswith("meher_resolve_hub."):
            sys.modules.pop(module_name, None)
    from meher_resolve_hub.app import main as hub_main
    return hub_main(globals())


if __name__ == "__main__":
    main()
