"""Shared lazy thumbnail cache with playhead restoration."""

import hashlib
import re
import json
import shutil
import subprocess
import time
from pathlib import Path

from .models.operation import OperationResult
from .preferences import user_data_dir


class ThumbnailCache:
    # Version 4 invalidates old undersized frames and captures made before
    # playhead-settle verification was added.
    CACHE_VERSION = "5"

    def __init__(self, context_service, folder=None, enabled=True, size=(960, 540), settle_delay=0.12, export_timeout=1.5):
        self.context_service = context_service
        self.folder = Path(folder) if folder else user_data_dir() / ".cache" / "thumbnails"
        self.enabled = bool(enabled)
        self.size = tuple(size)
        self.settle_delay = max(0.0, float(settle_delay))
        self.export_timeout = max(0.0, float(export_timeout))

    def cache_key(self, project_id, timeline_id, item_id, frame, relevant_state=""):
        raw = "%s|%s|%s|%s|%s|%s" % (self.CACHE_VERSION, project_id, timeline_id, item_id, int(frame), relevant_state)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def path_for(self, key):
        return self.folder / (str(key) + ".png")

    def get(self, key):
        path = self.path_for(key)
        try:
            return path if path.is_file() and path.stat().st_size > 0 else None
        except OSError:
            return None

    @staticmethod
    def _wait_for_timecode(timeline, target, timeout=0.75):
        deadline = time.monotonic() + max(0.0, float(timeout))
        while True:
            try:
                if str(timeline.GetCurrentTimecode() or "") == str(target):
                    return True
            except Exception:
                return False
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.02)

    @staticmethod
    def _wait_for_file(path, timeout=1.5):
        """Wait for Resolve's asynchronous still export to finish writing."""
        deadline = time.monotonic() + max(0.0, float(timeout))
        while True:
            try:
                if path.is_file() and path.stat().st_size > 0:
                    return True
            except OSError:
                pass
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.03)

    def generate(self, timeline, frame, key, fps):
        if not self.enabled:
            return OperationResult(False, warnings=["Thumbnails are disabled."])
        from .timecode import timeline_frame_to_timecode
        try:
            context = self.context_service.refresh_context()
            if not context.project or not timeline:
                return OperationResult(False, errors=["Open a project and timeline first."])
            previous = str(timeline.GetCurrentTimecode() or "")
            self.folder.mkdir(parents=True, exist_ok=True)
            destination = self.path_for(key)
        except Exception as exc:
            return OperationResult(False, failed=1, errors=["Could not prepare the thumbnail: %s" % exc])
        try:
            target = timeline_frame_to_timecode(timeline, frame, fps)
            timeline.SetCurrentTimecode(target)
            if not self._wait_for_timecode(timeline, target):
                return OperationResult(False, failed=1, errors=["Resolve did not reach the thumbnail frame."])
            if self.settle_delay:
                time.sleep(self.settle_delay)
            try:
                destination.unlink()
            except FileNotFoundError:
                pass
            exporter = getattr(context.project, "ExportCurrentFrameAsStill", None)
            if not callable(exporter):
                return OperationResult(False, failed=1, errors=["Resolve could not export the thumbnail."])
            # Resolve builds differ here: some return True, others return None,
            # and the PNG may be committed shortly after the API call returns.
            exporter(str(destination))
            if not self._wait_for_file(destination, self.export_timeout):
                return OperationResult(False, failed=1, errors=["Resolve could not export the thumbnail."])
            self._resize_if_available(destination)
            return OperationResult(True, changed=1, details=[{"path": str(destination)}])
        except Exception as exc:
            return OperationResult(False, failed=1, errors=["Could not generate the thumbnail: %s" % exc])
        finally:
            try:
                timeline.SetCurrentTimecode(previous)
                self._wait_for_timecode(timeline, previous)
            except Exception:
                pass

    def _resize_if_available(self, path):
        try:
            from PIL import Image
            with Image.open(str(path)) as image:
                image.thumbnail(self.size)
                image.save(str(path), "PNG", optimize=True)
            return
        except Exception:
            pass
        # Resolve's bundled Python does not normally include Pillow. macOS ships
        # sips, which gives the installed plugin a dependency-free resize path.
        executable = shutil.which("sips")
        if executable:
            try:
                subprocess.run(
                    [executable, "-Z", str(max(self.size)), str(path)],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=20,
                )
            except Exception:
                pass

    def clear(self):
        removed = 0
        if self.folder.is_dir():
            for path in self.folder.glob("*.png"):
                if not re.fullmatch(r"[0-9a-f]{40}\.png", path.name):
                    continue
                try:
                    path.unlink()
                    removed += 1
                except OSError:
                    pass
        return removed

    def delete_stale(self, valid_keys):
        valid = {str(item) + ".png" for item in valid_keys}
        removed = 0
        if self.folder.is_dir():
            for path in self.folder.glob("*.png"):
                if not re.fullmatch(r"[0-9a-f]{40}\.png", path.name):
                    continue
                if path.name not in valid:
                    try:
                        path.unlink()
                        removed += 1
                    except OSError:
                        pass
        return removed
