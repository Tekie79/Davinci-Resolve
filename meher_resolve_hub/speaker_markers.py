"""Public facade for Codex/MCP speaker dialogue marker automation."""

from .resolve_context import ResolveContextService
from .services.speaker_marker_service import SpeakerMarkerService


def analyze_select_speakers_and_mark(
    resolve,
    segments=None,
    analyzer=None,
    timeline=None,
    speaker_map=None,
    speaker_colors=None,
    mode="apply",
    **kwargs
):
    """Run the high-level Select-timeline speaker marker operation.

    This function is intentionally small so an MCP server or Codex-invoked
    Resolve script can expose it directly as one operation.
    """
    service = SpeakerMarkerService(ResolveContextService(resolve), analyzer=analyzer)
    return service.analyze_select_speakers_and_mark(
        segments=segments,
        analyzer=analyzer,
        timeline=timeline,
        speaker_map=speaker_map,
        speaker_colors=speaker_colors,
        mode=mode,
        **kwargs
    )
