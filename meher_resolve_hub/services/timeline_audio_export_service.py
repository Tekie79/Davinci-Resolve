"""Temporary Select-timeline audio export for speaker analysis.

This service renders an audio-only WAV from the current Select timeline so an
external/OpenAI analyzer can inspect the actual edited/synced audio. It restores
the previous render format/codec and render mode when possible. Resolve does not
expose a complete GetRenderSettings snapshot, so TargetDir/CustomName/export
flags may remain changed in the Deliver settings after the temporary render.
"""

from dataclasses import dataclass, field
from pathlib import Path
import tempfile
import time


def _call(proxy, name, default=None, *args):
    if proxy is None:
        return default
    try:
        method = getattr(proxy, name)
    except Exception:
        return default
    if not callable(method):
        return default
    try:
        value = method(*args)
        return default if value is None else value
    except Exception:
        return default


@dataclass
class TimelineAudioExportResult:
    success: bool
    path: str = ""
    job_id: str = ""
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    details: dict = field(default_factory=dict)


class TimelineAudioExportService:
    def __init__(self, context_service):
        self.context_service = context_service

    @staticmethod
    def _wav_format_and_codec(project):
        formats = dict(_call(project, "GetRenderFormats", {}) or {})
        candidates = []
        for key, extension in formats.items():
            text = ("%s %s" % (key, extension)).lower()
            if "wav" in text or "wave" in text:
                candidates.extend([str(key), str(extension)])
        candidates.extend(["wav", "Wave", "WAV"])

        tried = set()
        for render_format in candidates:
            if not render_format or render_format in tried:
                continue
            tried.add(render_format)
            codecs = dict(_call(project, "GetRenderCodecs", {}, render_format) or {})
            codec_candidates = []
            for description, codec in codecs.items():
                text = ("%s %s" % (description, codec)).lower()
                if "pcm" in text or "linear" in text:
                    codec_candidates.extend([str(codec), str(description)])
            codec_candidates.extend(["LinearPCM", "Linear PCM", "pcm_s16le"])
            for codec in codec_candidates:
                if not codec:
                    continue
                if _call(project, "SetCurrentRenderFormatAndCodec", False, render_format, codec):
                    return render_format, codec
        return "", ""

    @staticmethod
    def _find_output(folder, custom_name):
        folder = Path(folder)
        candidates = []
        for pattern in ("%s*.wav" % custom_name, "%s*.WAV" % custom_name):
            candidates.extend(folder.glob(pattern))
        if not candidates:
            return None
        return max(candidates, key=lambda path: path.stat().st_mtime_ns)

    def export_select_timeline_audio(
        self,
        timeline=None,
        output_dir=None,
        custom_name=None,
        sample_rate=16000,
        bit_depth=16,
        timeout_seconds=1800,
        require_select=True,
    ):
        context = self.context_service.refresh_context()
        project = context.project
        timeline = timeline or context.timeline
        if not project or not timeline:
            return TimelineAudioExportResult(
                False, errors=["Open a Resolve project and target Select timeline first."]
            )

        timeline_name = str(_call(timeline, "GetName", context.timeline_name) or "")
        if require_select and "SELECT" not in timeline_name.upper():
            return TimelineAudioExportResult(
                False, errors=["Target timeline is not a Select timeline: %s" % timeline_name]
            )

        output_root = Path(output_dir) if output_dir else Path(
            tempfile.mkdtemp(prefix="meher-select-audio-")
        )
        output_root.mkdir(parents=True, exist_ok=True)
        safe_name = custom_name or "speaker-analysis"
        safe_name = "".join(
            character if character.isalnum() or character in ("-", "_") else "_"
            for character in safe_name
        ).strip("_") or "speaker-analysis"

        previous_format = dict(
            _call(project, "GetCurrentRenderFormatAndCodec", {}) or {}
        )
        previous_mode = _call(project, "GetCurrentRenderMode", None)
        warnings = [
            "Resolve does not expose a complete current render-settings snapshot. "
            "The previous render format/codec and mode are restored, but temporary "
            "TargetDir/CustomName/ExportAudio settings may remain visible on Deliver."
        ]

        render_format, codec = self._wav_format_and_codec(project)
        if not render_format:
            return TimelineAudioExportResult(
                False,
                warnings=warnings,
                errors=["Resolve did not expose a usable WAV / Linear PCM render format."],
            )

        _call(project, "SetCurrentRenderMode", False, 1)
        settings = {
            "SelectAllFrames": True,
            "TargetDir": str(output_root),
            "CustomName": safe_name,
            "ExportVideo": False,
            "ExportAudio": True,
            "AudioCodec": codec,
            "AudioBitDepth": int(bit_depth),
            "AudioSampleRate": int(sample_rate),
        }
        if not _call(project, "SetRenderSettings", False, settings):
            # Some projects/Resolve builds may reject 16 kHz. Retry at project-like
            # production sample rate while retaining 16-bit temporary analysis audio.
            settings["AudioSampleRate"] = 48000
            if not _call(project, "SetRenderSettings", False, settings):
                self._restore(project, previous_format, previous_mode)
                return TimelineAudioExportResult(
                    False,
                    warnings=warnings,
                    errors=["Resolve rejected the temporary audio-only render settings."],
                )
            warnings.append("Resolve rejected 16 kHz; temporary analysis audio used 48 kHz.")

        job_id = str(_call(project, "AddRenderJob", "") or "")
        if not job_id:
            self._restore(project, previous_format, previous_mode)
            return TimelineAudioExportResult(
                False, warnings=warnings, errors=["Resolve could not create the audio render job."]
            )

        started = _call(project, "StartRendering", False, job_id)
        if not started:
            _call(project, "DeleteRenderJob", False, job_id)
            self._restore(project, previous_format, previous_mode)
            return TimelineAudioExportResult(
                False,
                job_id=job_id,
                warnings=warnings,
                errors=["Resolve did not start the temporary audio render."],
            )

        deadline = time.time() + max(1, float(timeout_seconds))
        while _call(project, "IsRenderingInProgress", False):
            if time.time() >= deadline:
                _call(project, "StopRendering", None)
                _call(project, "DeleteRenderJob", False, job_id)
                self._restore(project, previous_format, previous_mode)
                return TimelineAudioExportResult(
                    False,
                    job_id=job_id,
                    warnings=warnings,
                    errors=["Timed out waiting for the temporary Select audio render."],
                )
            time.sleep(0.25)

        status = dict(_call(project, "GetRenderJobStatus", {}, job_id) or {})
        output = self._find_output(output_root, safe_name)
        _call(project, "DeleteRenderJob", False, job_id)
        self._restore(project, previous_format, previous_mode)

        if output is None or not output.is_file() or output.stat().st_size <= 44:
            return TimelineAudioExportResult(
                False,
                job_id=job_id,
                warnings=warnings,
                errors=["Resolve finished but the temporary WAV could not be verified."],
                details={"status": status, "output_dir": str(output_root)},
            )

        return TimelineAudioExportResult(
            True,
            path=str(output),
            job_id=job_id,
            warnings=warnings,
            details={
                "timeline": timeline_name,
                "status": status,
                "sample_rate_requested": settings["AudioSampleRate"],
                "bit_depth": int(bit_depth),
                "format": render_format,
                "codec": codec,
                "temporary": output_dir is None,
            },
        )

    @staticmethod
    def _restore(project, previous_format, previous_mode):
        if previous_mode is not None:
            _call(project, "SetCurrentRenderMode", False, previous_mode)
        render_format = str(previous_format.get("format", "") or "")
        codec = str(previous_format.get("codec", "") or "")
        if render_format and codec:
            _call(project, "SetCurrentRenderFormatAndCodec", False, render_format, codec)
