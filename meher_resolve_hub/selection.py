"""Shared selection engine; unsupported sources never silently fall back."""

from dataclasses import dataclass, field
from typing import Any, List

from .constants import SELECTION_MODES
from .resolve_context import ResolveContextError


class SelectionUnavailable(RuntimeError):
    pass


@dataclass
class SelectionContext:
    mode: str
    clips: List[Any] = field(default_factory=list)
    timeline_items: List[Any] = field(default_factory=list)
    markers: List[Any] = field(default_factory=list)
    count: int = 0
    available: bool = True
    reason: str = ""


def _call_list(proxy, name):
    try:
        method = getattr(proxy, name)
    except Exception:
        raise SelectionUnavailable("This Resolve version does not expose %s." % name)
    if not callable(method):
        raise SelectionUnavailable("This Resolve version does not expose %s." % name)
    try:
        return list(method() or [])
    except Exception as exc:
        raise SelectionUnavailable("Resolve could not read this selection: %s" % exc)


def _folder_items(folder, recursive=False, visited=None):
    visited = visited or set()
    try:
        identity = str(folder.GetUniqueId())
    except Exception:
        identity = str(id(folder))
    if identity in visited:
        return []
    visited.add(identity)
    try:
        result = list(folder.GetClipList() or [])
    except Exception:
        result = []
    if recursive:
        try:
            children = list(folder.GetSubFolderList() or [])
        except Exception:
            children = []
        for child in children:
            result.extend(_folder_items(child, True, visited))
    return result


def _unique_clips(items):
    result, seen = [], set()
    for item in items:
        try:
            media_item = item.GetMediaPoolItem()
        except Exception:
            media_item = None
        if not media_item:
            continue
        try:
            identity = str(media_item.GetUniqueId())
        except Exception:
            identity = str(id(media_item))
        if identity not in seen:
            seen.add(identity)
            result.append(media_item)
    return result


class SelectionEngine:
    def __init__(self, context_service):
        self.context_service = context_service

    def get_media_pool_selection(self):
        context = self.context_service.refresh_context()
        if not context.media_pool:
            raise SelectionUnavailable("Open a project to use Media Pool Selection.")
        clips = _call_list(context.media_pool, "GetSelectedClips")
        return SelectionContext("Media Pool Selection", clips=clips, count=len(clips))

    def get_timeline_selection(self):
        context = self.context_service.refresh_context()
        if not context.timeline:
            raise SelectionUnavailable("Open a timeline to use Timeline Selection.")
        items = _call_list(context.timeline, "GetSelectedClips")
        clips = _unique_clips(items)
        return SelectionContext("Timeline Selection", clips=clips, timeline_items=items, count=len(items))

    def get_current_bin_items(self, recursive=False):
        context = self.context_service.refresh_context()
        if not context.current_bin:
            raise SelectionUnavailable("Select a Media Pool bin first.")
        clips = _folder_items(context.current_bin, recursive)
        mode = "Current Bin + Sub-Bins" if recursive else "Current Bin"
        return SelectionContext(mode, clips=clips, count=len(clips))

    def get_current_timeline_items(self):
        context = self.context_service.refresh_context()
        timeline = context.timeline
        if not timeline:
            raise SelectionUnavailable("Open a timeline first.")
        items = []
        for track_type in ("video", "audio"):
            try:
                count = int(timeline.GetTrackCount(track_type) or 0)
            except Exception:
                count = 0
            for index in range(1, count + 1):
                try:
                    items.extend(list(timeline.GetItemListInTrack(track_type, index) or []))
                except Exception:
                    continue
        clips = _unique_clips(items)
        return SelectionContext("Current Timeline", clips=clips, timeline_items=items, count=len(items))

    def get_selection(self, mode):
        if mode not in SELECTION_MODES:
            raise SelectionUnavailable("Unknown selection source: %s" % mode)
        if mode == "Media Pool Selection":
            return self.get_media_pool_selection()
        if mode == "Timeline Selection":
            return self.get_timeline_selection()
        if mode == "Current Bin":
            return self.get_current_bin_items(False)
        if mode == "Current Bin + Sub-Bins":
            return self.get_current_bin_items(True)
        return self.get_current_timeline_items()

