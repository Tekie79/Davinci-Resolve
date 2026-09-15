"""Current-frame and queued still capture while preserving Resolve context."""

import os
import shutil
import tempfile
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from ..models.operation import OperationResult
from ..models.still import StillQueueItem
from ..timecode import timeline_frame_to_timecode
from ..utils import collect_bins, find_exported_png, png_filename, proxy_id, safe_filename_component


class StillError(RuntimeError):
    pass


def default_output_folder(project_name):
    return Path.home() / "Pictures" / "DaVinci Resolve" / "Meher Flow Resolve Hub" / safe_filename_component(project_name, "Project")


def default_still_name(timeline_name, timecode, captured_at=None):
    captured_at = captured_at or datetime.now()
    timeline = safe_filename_component(timeline_name, "Timeline")
    tc = safe_filename_component(str(timecode or "Frame").replace(":", "-").replace(";", "-"), "Frame")
    return "%s_%s_%s.png" % (timeline, tc, captured_at.strftime("%Y%m%d_%H%M%S"))


def render_still_template(template, values):
    result = str(template or "{Timeline}_{Timecode}_{Index}")
    for key in ("Project", "Timeline", "Timecode", "Marker", "Clip", "Scene", "Shot", "Take", "Index", "Date", "Time"):
        result = result.replace("{%s}" % key, str(values.get(key, "") or ""))
    return png_filename(result)


class StillService:
    def __init__(self, resolve, context_service, navigation=None):
        self.resolve = resolve
        self.context_service = context_service
        self.navigation = navigation
        self.preview_dir = None
        self.preview_path = None
        self.gallery = []

    def cleanup_preview(self):
        if self.preview_dir:
            shutil.rmtree(str(self.preview_dir), ignore_errors=True)
        self.preview_dir = None
        self.preview_path = None

    def _export_current(self, project, timeline, destination):
        exported = False
        method = getattr(project, "ExportCurrentFrameAsStill", None)
        if callable(method):
            try: exported = bool(method(str(destination)))
            except Exception: exported = False
        if not exported:
            try:
                still = timeline.GrabStill()
                album = project.GetGallery().GetCurrentStillAlbum()
                exported = bool(still and album and album.ExportStills([still], str(destination.parent), destination.stem, "png"))
            except Exception:
                exported = False
        actual = find_exported_png(destination.parent, destination)
        return actual if exported and actual else None

    @staticmethod
    def _wait_for_timecode(timeline, target, timeout=0.75):
        """Wait until Resolve has actually displayed the requested frame."""
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

    def capture_current_frame(self):
        self.cleanup_preview()
        context = self.context_service.refresh_context()
        if not context.project:
            raise StillError("Open a Resolve project first.")
        if not context.timeline:
            raise StillError("Open a timeline and place the playhead over visible video.")
        folder = Path(tempfile.mkdtemp(prefix="meher_resolve_hub_still_"))
        requested = folder / "grabbed_still.png"
        actual = self._export_current(context.project, context.timeline, requested)
        if not actual:
            shutil.rmtree(str(folder), ignore_errors=True)
            raise StillError("Resolve could not export the current frame. Place the playhead over visible video.")
        self.preview_dir, self.preview_path = folder, actual
        return {
            "project": context.project, "timeline": context.timeline,
            "project_name": context.project_name, "timeline_name": context.timeline_name,
            "timecode": context.current_timecode, "page": context.current_page or "Unknown",
            "filename": default_still_name(context.timeline_name, context.current_timecode),
            "folder": default_output_folder(context.project_name),
        }

    def save_and_import(self, project, target_bin, folder_path, filename):
        if not self.preview_path or not Path(self.preview_path).is_file():
            raise StillError("The captured frame is no longer available. Grab it again.")
        raw = os.path.expandvars(os.path.expanduser(str(folder_path or "").strip()))
        if not raw: raise StillError("Choose a folder location on the computer.")
        folder = Path(raw)
        if folder.exists() and not folder.is_dir(): raise StillError("The selected location is not a folder.")
        try: folder.mkdir(parents=True, exist_ok=True)
        except Exception as exc: raise StillError("Could not create the output folder: %s" % exc)
        destination = folder / png_filename(filename)
        if destination.exists(): raise StillError("A file named '%s' already exists." % destination.name)
        try: shutil.copy2(str(self.preview_path), str(destination))
        except Exception as exc: raise StillError("Could not save the PNG: %s" % exc)
        imported = self._import_paths(project, target_bin, [destination])
        if not imported.success:
            raise StillError("The PNG was saved to '%s', but Resolve could not import it into the bin." % destination)
        self.cleanup_preview()
        return destination

    def _import_paths(self, project, target_bin, paths):
        pool = project.GetMediaPool()
        target_bin = target_bin or pool.GetRootFolder()
        previous = pool.GetCurrentFolder()
        imported = []
        errors = []
        try:
            if not pool.SetCurrentFolder(target_bin):
                return OperationResult(False, failed=len(paths), errors=["Resolve could not select the target bin."])
            for path in paths:
                result = None
                for payload in ([{"FilePath": str(path)}], [str(path)]):
                    try: result = pool.ImportMedia(payload)
                    except Exception: result = None
                    if result: break
                if not result and self.resolve:
                    storage = self.resolve.GetMediaStorage()
                    for payload in ([{"media": str(path)}], [str(path)]):
                        try: result = storage.AddItemListToMediaPool(payload)
                        except Exception: result = None
                        if result: break
                if result: imported.extend(list(result))
                else: errors.append(str(path))
        finally:
            if previous is not None:
                try: pool.SetCurrentFolder(previous)
                except Exception: pass
        return OperationResult(not errors, changed=len(imported), failed=len(errors), errors=["Could not import: %s" % path for path in errors], details=[{"clips": imported}])

    def queue_from_markers(self, markers, template, fps, project_name, timeline_name, timeline):
        now = datetime.now()
        result = []
        for index, marker in enumerate(markers, 1):
            absolute = int(timeline.GetStartFrame()) + marker.start_frame
            tc = timeline_frame_to_timecode(timeline, absolute, fps)
            values = {"Project": project_name, "Timeline": timeline_name, "Timecode": tc.replace(":", "-").replace(";", "-"), "Marker": marker.name, "Clip": "", "Scene": "", "Shot": "", "Take": "", "Index": index, "Date": now.strftime("%Y%m%d"), "Time": now.strftime("%H%M%S")}
            result.append(StillQueueItem(str(uuid4()), marker.name or "Marker", absolute, tc, render_still_template(template, values), proxy_id(timeline), timeline_name, "marker", marker.stable_key, timeline=timeline, source_object=marker, thumbnail_path=marker.thumbnail_path))
        return result

    def queue_from_timeline_items(self, items, position, template, fps, project_name, timeline_name, timeline):
        now, result = datetime.now(), []
        for index, item in enumerate(items, 1):
            start, end = int(item.GetStart()), int(item.GetEnd()) - 1
            frame = start if position == "First" else end if position == "Last" else start + max(0, end - start) // 2
            tc = timeline_frame_to_timecode(timeline, frame, fps)
            try: clip = item.GetMediaPoolItem(); metadata = dict(clip.GetMetadata() or {}); name = str(clip.GetName() or item.GetName() or "Clip")
            except Exception: clip, metadata, name = None, {}, str(item.GetName() or "Clip")
            values = {"Project": project_name, "Timeline": timeline_name, "Timecode": tc.replace(":", "-").replace(";", "-"), "Marker": "", "Clip": name, "Scene": metadata.get("Scene", ""), "Shot": metadata.get("Shot", ""), "Take": metadata.get("Take", ""), "Index": index, "Date": now.strftime("%Y%m%d"), "Time": now.strftime("%H%M%S")}
            result.append(StillQueueItem(str(uuid4()), name, frame, tc, render_still_template(template, values), proxy_id(timeline), timeline_name, "timeline_clip", proxy_id(item), timeline=timeline, source_object=item, metadata=metadata))
        return result

    @staticmethod
    def detect_conflicts(queue, output_folder):
        folder, seen = Path(output_folder), set()
        for item in queue:
            key = item.filename.casefold()
            if key in seen or (folder / item.filename).exists(): item.status = "Conflict"
            else: item.status = "Queued"
            seen.add(key)
        return queue

    def execute_queue(self, queue, output_folder, target_bin=None, import_to_bin=True):
        context = self.context_service.refresh_context()
        if not context.project or not context.timeline:
            return OperationResult(False, errors=["Open the source project and timeline first."])
        if any(item.timeline_id != context.timeline_id for item in queue):
            return OperationResult(False, errors=["The capture queue belongs to another timeline."])
        folder = Path(output_folder)
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            return OperationResult(False, failed=len(queue), errors=["Could not create the output folder: %s" % exc])
        previous = context.current_timecode
        result, paths = OperationResult(True), []
        try:
            for item in queue:
                if item.status == "Conflict": result.unchanged += 1; result.warnings.append("Skipped conflict: %s" % item.filename); continue
                try:
                    context.timeline.SetCurrentTimecode(item.timecode)
                except Exception:
                    item.status = "Failed"; result.failed += 1; result.errors.append("Could not navigate to %s." % item.timecode); continue
                if not self._wait_for_timecode(context.timeline, item.timecode):
                    item.status = "Failed"; result.failed += 1; result.errors.append("Resolve did not reach %s before capture." % item.timecode); continue
                destination = folder / item.filename
                actual = self._export_current(context.project, context.timeline, destination)
                if not actual:
                    item.status = "Failed"; result.failed += 1; result.errors.append("Capture failed: %s" % item.source_label); continue
                if actual != destination:
                    shutil.move(str(actual), str(destination))
                item.output_path = str(destination); item.thumbnail_path = str(destination); item.status = "Captured"; paths.append(destination); self.gallery.append(item); result.changed += 1
        finally:
            try: context.timeline.SetCurrentTimecode(previous)
            except Exception: result.warnings.append("Resolve could not restore the previous playhead position.")
        if import_to_bin and paths:
            result.absorb(self._import_paths(context.project, target_bin, paths))
        result.success = result.failed == 0
        return result

    def navigate_to_source(self, item):
        context = self.context_service.refresh_context()
        if context.timeline_id != item.timeline_id:
            return OperationResult(False, errors=["This still belongs to another timeline."])
        try:
            previous = context.current_timecode
            context.timeline.SetCurrentTimecode(item.timecode)
            success = self._wait_for_timecode(context.timeline, item.timecode)
        except Exception as exc: return OperationResult(False, failed=1, errors=[str(exc)])
        if self.navigation and success:
            self.navigation.state.timeline_id = context.timeline_id; self.navigation.state.previous_timecode = previous; self.navigation.state.selected_key = item.source_id
        return OperationResult(bool(success), changed=1 if success else 0, failed=0 if success else 1)
