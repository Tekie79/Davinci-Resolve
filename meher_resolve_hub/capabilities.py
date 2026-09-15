"""Resolve capability probing with explicit reasons for unsupported actions."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Capability:
    supported: bool
    reason: str = ""


def callable_api(proxy, name):
    if proxy is None:
        return False
    try:
        value = getattr(proxy, name)
    except Exception:
        return False
    return callable(value)


class CapabilityDetector:
    def __init__(self, resolve):
        self.resolve = resolve

    def detect(self, context):
        timeline = context.timeline
        pool = context.media_pool
        project = context.project
        return {
            "timeline_selection": Capability(callable_api(timeline, "GetSelectedClips"), "Resolve does not expose selected timeline clips."),
            "media_pool_selection": Capability(callable_api(pool, "GetSelectedClips"), "Resolve does not expose selected Media Pool clips."),
            "direct_still_export": Capability(callable_api(project, "ExportCurrentFrameAsStill"), "Direct current-frame export is unavailable."),
            "gallery_still_export": Capability(callable_api(timeline, "GrabStill"), "Gallery still capture is unavailable."),
            "timeline_markers": Capability(callable_api(timeline, "GetMarkers") and callable_api(timeline, "AddMarker") and callable_api(timeline, "DeleteMarkerAtFrame"), "Timeline marker mutation APIs are incomplete."),
            "marker_custom_data": Capability(callable_api(timeline, "GetMarkerCustomData") and callable_api(timeline, "UpdateMarkerCustomData"), "Marker custom data is unavailable."),
            "metadata": Capability(bool(pool), "Open a project to use metadata tools."),
            "clip_rename": Capability(bool(pool), "Open a project to rename Resolve clips."),
        }

