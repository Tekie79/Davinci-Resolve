"""Public facade for Codex/MCP speaker dialogue marker automation."""

from pathlib import Path

from .resolve_context import ResolveContextService
from .services.openai_diarization_service import OpenAIDiarizationAnalyzer
from .services.elevenlabs_diarization_service import ElevenLabsDiarizationAnalyzer
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


def export_select_timeline_audio(resolve, timeline=None, **kwargs):
    """Export Select audio using Codex_Mp3 first, with WAV as fallback."""
    context = ResolveContextService(resolve)
    return TimelineAudioExportService(context).export_select_timeline_audio(
        timeline=timeline, **kwargs
    )


def analyze_audio_with_openai(
    audio_path,
    known_speaker_references=None,
    openai_api_key=None,
    openai_model="gpt-4o-transcribe-diarize",
    include_transcript=False,
):
    """Analyze an audio file outside Resolve with OpenAI diarization."""
    analyzer = OpenAIDiarizationAnalyzer(
        audio_path=audio_path,
        api_key=openai_api_key,
        known_speaker_references=known_speaker_references,
        model=openai_model,
        include_transcript=include_transcript,
    )
    segments = analyzer.analyze(None, 24.0)
    return {
        "segments": segments,
        "warnings": list(analyzer.last_warnings),
        "model": openai_model,
        "provider": "openai",
    }
def analyze_audio_with_elevenlabs(
    audio_path,
    elevenlabs_api_key=None,
    elevenlabs_model="scribe_v2",
    include_transcript=False,
    language_code=None,
    num_speakers=None,
    use_speaker_library=False,
    keyterms=None,
):
    """Analyze an audio file with ElevenLabs Scribe v2."""
    analyzer = ElevenLabsDiarizationAnalyzer(
        audio_path=audio_path,
        api_key=elevenlabs_api_key,
        model=elevenlabs_model,
        include_transcript=include_transcript,
        language_code=language_code,
        num_speakers=num_speakers,
        use_speaker_library=use_speaker_library,
        keyterms=keyterms,
    )
    segments = analyzer.analyze(None, 24.0)
    return {
        "segments": segments,
        "warnings": list(analyzer.last_warnings),
        "model": elevenlabs_model,
        "provider": "elevenlabs",
        "language_detected": analyzer.language_detected,
        "language_probability": analyzer.language_probability,
    }


def apply_select_speaker_markers(
    resolve,
    segments,
    timeline=None,
    speaker_map=None,
    speaker_colors=None,
    mode="apply",
    **kwargs
):
    """Apply already-analyzed speaker ranges to Resolve clip markers."""
    context = ResolveContextService(resolve)
    return SpeakerMarkerService(context).analyze_select_speakers_and_mark(
        segments=segments,
        timeline=timeline,
        speaker_map=speaker_map,
        speaker_colors=speaker_colors,
        mode=mode,
        **kwargs
    )


def analyze_select_speakers_and_mark(
    resolve,
    segments=None,
    analyzer=None,
    timeline=None,
    audio_path=None,
    known_speaker_references=None,
    openai_api_key=None,
    openai_model="gpt-4o-transcribe-diarize",
    elevenlabs_api_key=None,
    elevenlabs_model="scribe_v2",
    analysis_provider="openai",
    include_transcript=False,
    elevenlabs_language_code=None,
    elevenlabs_num_speakers=None,
    elevenlabs_use_speaker_library=False,
    elevenlabs_keyterms=None,
    speaker_map=None,
    speaker_colors=None,
    mode="apply",
    auto_export_audio=True,
    keep_analysis_audio=False,
    audio_export_options=None,
    **kwargs
):
    """Analyze a Select timeline audio and add speaker range clip markers.

    Normal one-call path for Codex:
      Resolve Select timeline
        -> Codex_Mp3 preset to persistent reference MP3
        -> WAV fallback only when needed
        -> selected provider: OpenAI or ElevenLabs speaker diarization
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
                timeline=timeline,
                **dict(audio_export_options or {})
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

        provider = str(analysis_provider or "openai").strip().casefold()
        if provider == "openai":
            created_analyzer = OpenAIDiarizationAnalyzer(
                audio_path=audio_path,
                api_key=openai_api_key,
                known_speaker_references=known_speaker_references,
                model=openai_model,
                include_transcript=include_transcript,
            )
        elif provider == "elevenlabs":
            created_analyzer = ElevenLabsDiarizationAnalyzer(
                audio_path=audio_path,
                api_key=elevenlabs_api_key,
                model=elevenlabs_model,
                include_transcript=include_transcript,
                language_code=elevenlabs_language_code,
                num_speakers=elevenlabs_num_speakers,
                use_speaker_library=elevenlabs_use_speaker_library,
                keyterms=elevenlabs_keyterms,
            )
        else:
            from .models.operation import OperationResult
            return OperationResult(
                False,
                failed=1,
                errors=["analysis_provider must be openai or elevenlabs."],
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
                "analysis_format": export_result.details.get("analysis_format", ""),
                "render_preset": export_result.details.get("render_preset", ""),
                "export_directory": export_result.details.get("export_directory", ""),
                "directory_role": export_result.details.get("directory_role", ""),
                "used_wav_fallback": export_result.details.get("used_wav_fallback", False),
                "persistent_audio": export_result.details.get("persistent", False),
                "render_status": export_result.details.get("status", {}),
            })
        if created_analyzer and hasattr(created_analyzer, "last_warnings"):
            result.warnings.extend(list(created_analyzer.last_warnings))
        if created_analyzer:
            result.details.insert(0, {
                "analysis_provider": str(analysis_provider or "openai").casefold(),
                "analysis_model": (
                    elevenlabs_model
                    if str(analysis_provider or "openai").casefold() == "elevenlabs"
                    else openai_model
                ),
                "language_detected": getattr(created_analyzer, "language_detected", ""),
                "language_probability": getattr(created_analyzer, "language_probability", None),
            })
        return result
    finally:
        if export_result and not keep_analysis_audio:
            _cleanup_temporary_export(export_result)
