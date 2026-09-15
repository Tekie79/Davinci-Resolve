"""Resolve proxy fakes shared by Resolve Hub tests."""

from pathlib import Path


class FakeClip:
    def __init__(self, identity, name, metadata=None, properties=None, set_name=True, set_metadata=True):
        self.identity = identity; self.name = name; self.metadata = dict(metadata or {}); self.properties = dict(properties or {}); self.set_name_result = set_name; self.set_metadata_result = set_metadata; self.markers = {}
    def GetUniqueId(self): return self.identity
    def GetMediaId(self): return self.identity
    def GetName(self): return self.name
    def SetName(self, value):
        if self.set_name_result: self.name = value
        return self.set_name_result
    def GetMetadata(self, key=None): return self.metadata.get(key, "") if key else dict(self.metadata)
    def SetMetadata(self, values):
        if self.set_metadata_result: self.metadata.update(values)
        return self.set_metadata_result
    def GetClipProperty(self, key=None): return self.properties.get(key, "") if key else dict(self.properties)
    def GetMarkers(self): return dict(self.markers)
    def AddMarker(self, frame, color, name, note, duration, custom_data=""):
        if frame in self.markers: return False
        self.markers[frame] = {"color": color, "name": name, "note": note, "duration": duration, "customData": custom_data}; return True
    def DeleteMarkerAtFrame(self, frame):
        if frame not in self.markers: return False
        del self.markers[frame]; return True
    def GetMarkerCustomData(self, frame): return self.markers.get(frame, {}).get("customData", "")


class FailingMarkerTimeline(FakeClip):
    def __init__(self, fail_new=True, fail_rollback=False):
        super().__init__("timeline", "Timeline"); self.fail_new = fail_new; self.fail_rollback = fail_rollback; self.original_frame = 10; self.add_calls = 0; self.markers[10] = {"color": "Blue", "name": "Old", "note": "Note", "duration": 2, "customData": "x"}
    def GetStartFrame(self): return 100
    def GetEndFrame(self): return 1000
    def GetStartTimecode(self): return "01:00:00:00"
    def GetCurrentTimecode(self): return "01:00:00:00"
    def AddMarker(self, frame, color, name, note, duration, custom_data=""):
        self.add_calls += 1
        if frame != self.original_frame and self.fail_new: return False
        if frame == self.original_frame and self.fail_rollback: return False
        return super().AddMarker(frame, color, name, note, duration, custom_data)


class FakeTimeline:
    def __init__(self, items=None, markers=None):
        self.items = list(items or []); self.markers = dict(markers or {}); self.timecode = "01:00:00:00"; self.set_calls = []
    def GetName(self): return "Timeline"
    def GetUniqueId(self): return "timeline"
    def GetStartFrame(self): return 100
    def GetEndFrame(self): return 1000
    def GetStartTimecode(self): return "01:00:00:00"
    def GetCurrentTimecode(self): return self.timecode
    def SetCurrentTimecode(self, value): self.timecode = value; self.set_calls.append(value); return True
    def GetSettings(self): return {"timelineFrameRate": "24"}
    def GetMarkers(self): return dict(self.markers)
    def GetMarkerCustomData(self, frame): return self.markers.get(frame, {}).get("customData", "")
    def AddMarker(self, frame, color, name, note, duration, custom_data=""):
        if frame in self.markers: return False
        self.markers[frame] = {"color": color, "name": name, "note": note, "duration": duration, "customData": custom_data}; return True
    def DeleteMarkerAtFrame(self, frame):
        if frame not in self.markers: return False
        del self.markers[frame]; return True
    def GetSelectedClips(self): return self.items
    def GetTrackCount(self, track_type): return 1 if track_type == "video" else 0
    def GetItemListInTrack(self, track_type, index): return self.items if track_type == "video" else []


class FakeTimelineItem:
    def __init__(self, clip, start=100, end=124): self.clip = clip; self.start = start; self.end = end
    def GetUniqueId(self): return "item-" + self.clip.identity
    def GetMediaPoolItem(self): return self.clip
    def GetStart(self): return self.start
    def GetEnd(self): return self.end
    def GetName(self): return self.clip.name


class FakeFolder:
    def __init__(self, name="Master", clips=None, children=None): self.name = name; self.clips = list(clips or []); self.children = list(children or [])
    def GetName(self): return self.name
    def GetUniqueId(self): return self.name
    def GetClipList(self): return list(self.clips)
    def GetSubFolderList(self): return list(self.children)


class FakeMediaPool:
    def __init__(self, root, selected=None): self.root = root; self.current = root; self.selected = list(selected or [])
    def GetRootFolder(self): return self.root
    def GetCurrentFolder(self): return self.current
    def SetCurrentFolder(self, folder): self.current = folder; return True
    def GetSelectedClips(self): return list(self.selected)
    def SetSelectedClip(self, clip): self.selected = [clip]; return True
    def ImportMedia(self, values): return [object()]


class FakeProject:
    def __init__(self, timeline=None, pool=None, export=True): self.timeline = timeline; self.pool = pool or FakeMediaPool(FakeFolder()); self.export = export
    def GetName(self): return "Project"
    def GetUniqueId(self): return "project"
    def GetCurrentTimeline(self): return self.timeline
    def GetMediaPool(self): return self.pool
    def GetSettings(self): return {"timelineFrameRate": "24"}
    def ExportCurrentFrameAsStill(self, path):
        if self.export: Path(path).write_bytes(b"png")
        return self.export


class FakeProjectManager:
    def __init__(self, project): self.project = project
    def GetCurrentProject(self): return self.project


class FakeStorage:
    def AddItemListToMediaPool(self, values): return [object()]


class FakeResolve:
    def __init__(self, project): self.project = project
    def GetProjectManager(self): return FakeProjectManager(self.project)
    def GetCurrentPage(self): return "edit"
    def GetMediaStorage(self): return FakeStorage()

