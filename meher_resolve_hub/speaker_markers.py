"""Public facade for Codex/MCP speaker dialogue marker automation."""

from pathlib import Path

from .resolve_context import ResolveContextService
from .services.openai_diarization_service import OpenAIDiarizationAnalyzer
from .services.speaker_marker_service import SpeakerMarkerService
from .services.timeline_audio_export_service import TimelineAudioExportService


def _cleanup_temporary_export(export_result):
    if not export_result or not export_result.success:
        return
    if not export_result.details.get("temporary"):
        return
    path = Path(export_result.path)
    parent = path.parent
    try:
        path.unlink()
    except Exception:
        return
    try:
        parent.rmdir()
    except Exception:
        pass


def analyze_select_speakers_and_mark(
    resolve,
    segments=None,
    analyzer=None,
    timeline=None,
    audio_path=None,
    known_speaker_references=None,
    openai_api_key=None,
    openai_model="gpt-4o-transcribe-diarize",
    include_transcript=False,
    speaker_map=None,
    speaker_colors=None,
    mode="apply",
    auto_export_audio=True,
    keep_analysis_audio=False,
    **kwargs
):
    """Analyze a Select timeline audio and add speaker range clip markers.

    Normal one-call path for Codex:
      Resolve Select timeline
        -> temporary audio-only WAV export
        -> OpenAI speaker diarization
        -> speaker/color mapping
        -> verified TimelineItem duration markers

    Resolve transcription/caption generation is not used.

    Advanced/test callers may bypass audio analysis with precomputed segments
    or inject a custom analyzer adapter.
    """
    context = ResolveContextService(resolve)
    export_result = None
    created_analyzer = analyzer

    if segments is None and created_analyzer is None:
        if not audio_path:
            if not auto_export_audio:
                return SpeakerMarkerService(context).analyze_select_speakers_and_mark(
                    segments=None, analyzer=None, timeline=timeline,
                    speaker_map=speaker_map, speaker_colors=speaker_colors,
                    mode=mode, **kwargs
                )
            export_result = TimelineAudioExportService(context).export_select_timeline_audio(
                timeline=timeline
            )
            if not export_result.success:
                from .models.operation import OperationResult
                return OperationResult(
                    False,
                    failed=1,
                    warnings=list(export_result.warnings),
                    errors=list(export_result.errors),
                    details=[dict(export_result.details or {})],
                )
            audio_path = export_result.path

        created_analyzer = OpenAIDiarizationAnalyzer(
            audio_path=audio_path,
            api_key=openai_api_key,
            known_speaker_references=known_speaker_references,
            model=openai_model,
            include_transcript=include_transcript,
        )

    service = SpeakerMarkerService(context, analyzer=created_analyzer)
    try:
        result = service.analyze_select_speakers_and_mark(
            segments=segments,
            analyzer=created_analyzer,
            timeline=timeline,
            speaker_map=speaker_map,
            speaker_colors=speaker_colors,
            mode=mode,
            **kwargs
        )
        if export_result:
            result.warnings = list(export_result.warnings) + list(result.warnings)
            result.details.insert(0, {
                "audio_export": export_result.path,
                "temporary_audio": export_result.details.get("temporary", False),
                "render_status": export_result.details.get("status", {}),
            })
        if created_analyzer and hasattr(created_analyzer, "last_warnings"):
            result.warnings.extend(list(created_analyzer.last_warnings))
        return result
    finally:
        if export_result and not keep_analysis_audio:
            _cleanup_temporary_export(export_result)
