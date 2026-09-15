"""Fresh Resolve context snapshots for long-running Hub sessions."""

from dataclasses import dataclass
from typing import Any, Optional


class ResolveContextError(RuntimeError):
    pass


@dataclass
class ResolveContext:
    project: Optional[Any] = None
    project_name: str = ""
    project_id: str = ""
    timeline: Optional[Any] = None
    timeline_name: str = ""
    timeline_id: str = ""
    media_pool: Optional[Any] = None
    current_bin: Optional[Any] = None
    current_page: str = ""
    current_timecode: str = ""


def safe_call(proxy, name, default=None, *args):
    if proxy is None:
        return default
    try:
        method = getattr(proxy, name)
        if not callable(method):
            return default
        value = method(*args)
        return default if value is None else value
    except Exception:
        return default


class ResolveContextService:
    def __init__(self, resolve):
        self.resolve = resolve
        self.context = ResolveContext()

    def get_context(self):
        return self.refresh_context()

    def refresh_context(self):
        manager = safe_call(self.resolve, "GetProjectManager")
        project = safe_call(manager, "GetCurrentProject")
        media_pool = safe_call(project, "GetMediaPool")
        timeline = safe_call(project, "GetCurrentTimeline")
        self.context = ResolveContext(
            project=project,
            project_name=str(safe_call(project, "GetName", "") or ""),
            project_id=str(safe_call(project, "GetUniqueId", "") or ""),
            timeline=timeline,
            timeline_name=str(safe_call(timeline, "GetName", "") or ""),
            timeline_id=str(safe_call(timeline, "GetUniqueId", "") or ""),
            media_pool=media_pool,
            current_bin=safe_call(media_pool, "GetCurrentFolder"),
            current_page=str(safe_call(self.resolve, "GetCurrentPage", "") or "").title(),
            current_timecode=str(safe_call(timeline, "GetCurrentTimecode", "") or ""),
        )
        return self.context

    def require_project(self):
        context = self.refresh_context()
        if not context.project:
            raise ResolveContextError("Open a Resolve project first.")
        return context.project

    def require_timeline(self):
        context = self.refresh_context()
        if not context.timeline:
            raise ResolveContextError("Open a timeline first.")
        return context.timeline

    def get_current_bin(self):
        context = self.refresh_context()
        if not context.current_bin:
            raise ResolveContextError("Select a Media Pool bin first.")
        return context.current_bin

    def get_project_fps(self):
        context = self.refresh_context()
        project = context.project
        timeline = context.timeline
        for proxy, names in (
            (timeline, ("timelineFrameRate", "timelinePlaybackFrameRate")),
            (project, ("timelineFrameRate", "timelinePlaybackFrameRate")),
        ):
            settings = safe_call(proxy, "GetSettings", {}) or {}
            for name in names:
                value = settings.get(name)
                if value not in (None, ""):
                    try:
                        return float(value)
                    except (TypeError, ValueError):
                        pass
        return 24.0

