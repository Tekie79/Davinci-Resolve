"""Shared lazy thumbnail cache with playhead restoration."""

import hashlib
import json
from pathlib import Path

from .models.operation import OperationResult
from .preferences import user_data_dir


class ThumbnailCache:
    def __init__(self, context_service, folder=None, enabled=True, size=(160, 90)):
        self.context_service = context_service
        self.folder = Path(folder) if folder else user_data_dir() / ".cache" / "thumbnails"
        self.enabled = bool(enabled)
        self.size = tuple(size)

    def cache_key(self, project_id, timeline_id, item_id, frame, relevant_state=""):
        raw = "%s|%s|%s|%s|%s" % (project_id, timeline_id, item_id, int(frame), relevant_state)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def path_for(self, key):
        return self.folder / (str(key) + ".png")

    def get(self, key):
        path = self.path_for(key)
        return path if path.is_file() else None

    def generate(self, timeline, frame, key, fps):
        if not self.enabled:
            return OperationResult(False, warnings=["Thumbnails are disabled."])
        context = self.context_service.refresh_context()
        if not context.project or not timeline:
            return OperationResult(False, errors=["Open a project and timeline first."])
        from .timecode import timeline_frame_to_timecode
        previous = str(timeline.GetCurrentTimecode() or "")
        self.folder.mkdir(parents=True, exist_ok=True)
        destination = self.path_for(key)
        try:
            target = timeline_frame_to_timecode(timeline, frame, fps)
            if not timeline.SetCurrentTimecode(target):
                return OperationResult(False, failed=1, errors=["Resolve could not move to thumbnail frame."])
            exporter = getattr(context.project, "ExportCurrentFrameAsStill", None)
            if not callable(exporter) or not exporter(str(destination)) or not destination.is_file():
                return OperationResult(False, failed=1, errors=["Resolve could not export the thumbnail."])
            self._resize_if_available(destination)
            return OperationResult(True, changed=1, details=[{"path": str(destination)}])
        finally:
            try:
                timeline.SetCurrentTimecode(previous)
            except Exception:
                pass

    def _resize_if_available(self, path):
        try:
            from PIL import Image
            with Image.open(str(path)) as image:
                image.thumbnail(self.size)
                image.save(str(path), "PNG", optimize=True)
        except Exception:
            pass

    def clear(self):
        removed = 0
        if self.folder.is_dir():
            for path in self.folder.glob("*.png"):
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
                if path.name not in valid:
                    try:
                        path.unlink()
                        removed += 1
                    except OSError:
                        pass
        return removed

