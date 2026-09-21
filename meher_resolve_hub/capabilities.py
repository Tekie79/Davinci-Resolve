"""Resolve capability probing with explicit reasons for unsupported actions."""

from dataclasses import dataclass
import importlib.util
import os


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


def first_timeline_item(timeline, track_type="video"):
    if timeline is None:
        return None
    try:
        count = int(timeline.GetTrackCount(track_type) or 0)
    except Exception:
        count = 0
    for index in range(1, count + 1):
        try:
            items = list(timeline.GetItemListInTrack(track_type, index) or [])
        except Exception:
            items = []
        if items:
            return items[0]
    return None


class CapabilityDetector:
    def __init__(self, resolve):
        self.resolve = resolve

    def detect(self, context):
        timeline = context.timeline
        pool = context.media_pool
        project = context.project
        item = first_timeline_item(timeline, "video")
        clip_marker_supported = bool(
            item
            and callable_api(item, "GetMarkers")
            and callable_api(item, "AddMarker")
            and callable_api(item, "DeleteMarkerAtFrame")
        )
        return {
            "timeline_selection": Capability(callable_api(timeline, "GetSelectedClips"), "Resolve does not expose selected timeline clips."),
            "media_pool_selection": Capability(callable_api(pool, "GetSelectedClips"), "Resolve does not expose selected Media Pool clips."),
            "direct_still_export": Capability(callable_api(project, "ExportCurrentFrameAsStill"), "Direct current-frame export is unavailable."),
            "gallery_still_export": Capability(callable_api(timeline, "GrabStill"), "Gallery still capture is unavailable."),
            "timeline_markers": Capability(callable_api(timeline, "GetMarkers") and callable_api(timeline, "AddMarker") and callable_api(timeline, "DeleteMarkerAtFrame"), "Timeline marker mutation APIs are incomplete."),
            "clip_markers": Capability(clip_marker_supported, "Open a timeline with a video clip whose TimelineItem marker APIs are available."),
            "speaker_marker_write": Capability(clip_marker_supported, "Speaker dialogue markers require TimelineItem marker APIs."),
            "speaker_segment_read": Capability(False, "Resolve's documented scripting API does not expose transcription speaker segments; use OpenAI audio diarization or inject precomputed segments."),
            "timeline_audio_export": Capability(
                bool(project)
                and callable_api(project, "SetRenderSettings")
                and callable_api(project, "AddRenderJob")
                and callable_api(project, "StartRendering")
                and callable_api(project, "GetRenderJobStatus"),
                "Temporary Select audio export requires Resolve render APIs.",
            ),
            "openai_audio_diarization": Capability(
                bool(os.environ.get("OPENAI_API_KEY"))
                and importlib.util.find_spec("openai") is not None,
                "Set OPENAI_API_KEY and install the openai Python package in the analysis runtime.",
            ),
            "marker_custom_data": Capability(callable_api(timeline, "GetMarkerCustomData") and callable_api(timeline, "UpdateMarkerCustomData"), "Marker custom data is unavailable."),
            "metadata": Capability(bool(pool), "Open a project to use metadata tools."),
            "clip_rename": Capability(bool(pool), "Open a project to rename Resolve clips."),
        }
