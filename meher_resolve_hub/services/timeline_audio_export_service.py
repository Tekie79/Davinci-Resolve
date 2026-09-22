"""Select-timeline audio export for speaker analysis.

Yekermo Sew production defaults:
- primary Resolve render preset: Codex_Mp3
- primary directory: /Volumes/Harvest SSD/Select_ref_mp3_audios
- directory fallback: /Users/harvest/Documents/Ysew_Project/Ref audio
- filename stem: <Select timeline name>_mp3
- WAV / Linear PCM is a fallback when the MP3 preset/export is unavailable,
  invalid, or too large for the direct transcription upload path.

The final analysis file is persistent. Renders are staged in an isolated
subdirectory and published only after verification, so an older valid reference
is not destroyed by a failed render.

Resolve does not expose a complete render-settings snapshot. The service restores
render mode and current format/codec when those APIs are available, but preset
loading can still leave other Deliver-page settings changed.
"""

from dataclasses import dataclass, field
import os
from pathlib import Path
import shutil
import tempfile
import time
from uuid import uuid4


DEFAULT_RENDER_PRESET = "Codex_Mp3"
PRIMARY_EXPORT_DIRECTORY = Path("/Volumes/Harvest SSD/Select_ref_mp3_audios")
FALLBACK_EXPORT_DIRECTORY = Path("/Users/harvest/Documents/Ysew_Project/Ref audio")
DEFAULT_MAX_DIRECT_UPLOAD_BYTES = 24 * 1024 * 1024


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
    def _safe_stem(value):
        text = "".join(
            character if character.isalnum() or character in ("-", "_", " ")
            else "_"
            for character in str(value or "")
        )
        text = "_".join(part for part in text.strip().split())
        return text.strip("_") or "SELECT"

    @classmethod
    def _default_stem(cls, timeline_name):
        return cls._safe_stem(timeline_name) + "_mp3"

    @staticmethod
    def _prepare_directory(path):
        path = Path(path).expanduser()
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / (".meher-write-test-%s" % uuid4().hex)
            probe.write_bytes(b"ok")
            probe.unlink()
        except Exception as exc:
            return None, str(exc)
        return path, ""

    @classmethod
    def _resolve_output_directory(
        cls,
        output_dir=None,
        primary_output_dir=PRIMARY_EXPORT_DIRECTORY,
        fallback_output_dir=FALLBACK_EXPORT_DIRECTORY,
    ):
        if output_dir:
            directory, error = cls._prepare_directory(output_dir)
            if directory:
                return directory, "explicit", []
            return None, "", ["Requested export directory is unavailable: %s" % error]

        warnings = []
        primary, error = cls._prepare_directory(primary_output_dir)
        if primary:
            return primary, "primary", warnings
        warnings.append(
            "Primary Select reference-audio directory is unavailable (%s); using fallback."
            % error
        )

        fallback, fallback_error = cls._prepare_directory(fallback_output_dir)
        if fallback:
            return fallback, "fallback", warnings

        warnings.append(
            "Fallback Select reference-audio directory is unavailable: %s"
            % fallback_error
        )
        return None, "", warnings

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
                if _call(
                    project,
                    "SetCurrentRenderFormatAndCodec",
                    False,
                    render_format,
                    codec,
                ):
                    return render_format, codec
        return "", ""

    @staticmethod
    def _find_output(folder, custom_name, extension):
        folder = Path(folder)
        suffixes = {str(extension or "").lower(), str(extension or "").upper()}
        candidates = []
        for suffix in suffixes:
            if suffix:
                candidates.extend(folder.glob("%s*.%s" % (custom_name, suffix.lstrip("."))))
        if not candidates:
            return None
        candidates = [
            path for path in candidates
            if path.is_file() and path.stat().st_size > 0
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda path: path.stat().st_mtime_ns)

    @staticmethod
    def _wait_for_render(project, job_id, timeout_seconds):
        deadline = time.monotonic() + max(1.0, float(timeout_seconds))
        while _call(project, "IsRenderingInProgress", False):
            if time.monotonic() >= deadline:
                _call(project, "StopRendering", None)
                return False, "Timed out waiting for Select audio render."
            time.sleep(0.25)

        status = dict(_call(project, "GetRenderJobStatus", {}, job_id) or {})
        status_text = str(
            status.get("JobStatus", status.get("jobStatus", ""))
        ).casefold()
        if status_text and not any(
            token in status_text for token in ("complete", "completed", "success")
        ):
            return False, "Resolve render did not complete successfully: %s" % status
        return True, status

    @staticmethod
    def _publish(staged, destination):
        staged = Path(staged)
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp_destination = destination.with_name(
            ".%s.publish-%s" % (destination.name, uuid4().hex)
        )
        shutil.copy2(str(staged), str(temp_destination))
        if not temp_destination.is_file() or temp_destination.stat().st_size <= 0:
            try:
                temp_destination.unlink()
            except Exception:
                pass
            raise RuntimeError("Published analysis audio could not be verified.")
        os.replace(str(temp_destination), str(destination))
        return destination

    def _render_with_preset(
        self,
        project,
        output_root,
        safe_name,
        preset_name,
        timeout_seconds,
    ):
        if not _call(project, "LoadRenderPreset", False, str(preset_name)):
            return None, "", [
                "Resolve render preset '%s' is unavailable or could not be loaded."
                % preset_name
            ], {}

        staging = Path(tempfile.mkdtemp(prefix=".meher-mp3-", dir=str(output_root)))
        job_id = ""
        try:
            _call(project, "SetCurrentRenderMode", False, 0)
            settings = {
                "SelectAllFrames": True,
                "TargetDir": str(staging),
                "CustomName": safe_name,
                "ExportVideo": False,
                "ExportAudio": True,
            }
            if not _call(project, "SetRenderSettings", False, settings):
                return None, "", [
                    "Resolve rejected the Codex_Mp3 render settings override."
                ], {}

            job_id = str(_call(project, "AddRenderJob", "") or "")
            if not job_id:
                return None, "", ["Resolve could not create the Codex_Mp3 render job."], {}

            if not _call(project, "StartRendering", False, job_id):
                return None, job_id, ["Resolve did not start the Codex_Mp3 render."], {}

            ok, status = self._wait_for_render(project, job_id, timeout_seconds)
            if not ok:
                return None, job_id, [str(status)], {}

            output = self._find_output(staging, safe_name, "mp3")
            if not output or output.stat().st_size <= 0:
                return None, job_id, [
                    "Codex_Mp3 finished but no valid MP3 output was found."
                ], {"status": status}

            return output, job_id, [], {"status": status, "preset": preset_name}
        finally:
            if job_id:
                _call(project, "DeleteRenderJob", False, job_id)

    def _render_wav_fallback(
        self,
        project,
        output_root,
        safe_name,
        sample_rate,
        bit_depth,
        timeout_seconds,
    ):
        render_format, codec = self._wav_format_and_codec(project)
        if not render_format:
            return None, "", [
                "Resolve did not expose a usable WAV / Linear PCM fallback."
            ], {}

        staging = Path(tempfile.mkdtemp(prefix=".meher-wav-", dir=str(output_root)))
        job_id = ""
        try:
            _call(project, "SetCurrentRenderMode", False, 0)
            settings = {
                "SelectAllFrames": True,
                "TargetDir": str(staging),
                "CustomName": safe_name,
                "ExportVideo": False,
                "ExportAudio": True,
                "AudioCodec": codec,
                "AudioBitDepth": int(bit_depth),
                "AudioSampleRate": int(sample_rate),
            }
            if not _call(project, "SetRenderSettings", False, settings):
                settings["AudioSampleRate"] = 48000
                if not _call(project, "SetRenderSettings", False, settings):
                    return None, "", [
                        "Resolve rejected WAV fallback render settings."
                    ], {}
                warning = "Resolve rejected 16 kHz WAV; fallback used 48 kHz."
            else:
                warning = ""

            job_id = str(_call(project, "AddRenderJob", "") or "")
            if not job_id:
                return None, "", ["Resolve could not create WAV fallback render job."], {}

            if not _call(project, "StartRendering", False, job_id):
                return None, job_id, ["Resolve did not start WAV fallback render."], {}

            ok, status = self._wait_for_render(project, job_id, timeout_seconds)
            if not ok:
                return None, job_id, [str(status)], {}

            output = self._find_output(staging, safe_name, "wav")
            if not output or output.stat().st_size <= 44:
                return None, job_id, [
                    "Resolve finished but the WAV fallback could not be verified."
                ], {"status": status}

            warnings = [warning] if warning else []
            return output, job_id, warnings, {
                "status": status,
                "render_format": render_format,
                "render_codec": codec,
                "sample_rate": settings["AudioSampleRate"],
                "bit_depth": int(bit_depth),
            }
        finally:
            if job_id:
                _call(project, "DeleteRenderJob", False, job_id)

    def export_select_timeline_audio(
        self,
        timeline=None,
        output_dir=None,
        custom_name=None,
        sample_rate=16000,
        bit_depth=16,
        preferred_format="mp3",
        render_preset=DEFAULT_RENDER_PRESET,
        primary_output_dir=PRIMARY_EXPORT_DIRECTORY,
        fallback_output_dir=FALLBACK_EXPORT_DIRECTORY,
        max_direct_upload_bytes=DEFAULT_MAX_DIRECT_UPLOAD_BYTES,
        timeout_seconds=1800,
        require_select=True,
        **_legacy_kwargs
    ):
        context = self.context_service.refresh_context()
        project = context.project
        timeline = timeline or context.timeline
        if not project or not timeline:
            return TimelineAudioExportResult(
                False,
                errors=["Open a Resolve project and target Select timeline first."],
            )

        timeline_name = str(_call(timeline, "GetName", context.timeline_name) or "")
        if require_select and "SELECT" not in timeline_name.upper():
            return TimelineAudioExportResult(
                False,
                errors=["Target timeline is not a Select timeline: %s" % timeline_name],
            )

        output_root, directory_role, directory_warnings = self._resolve_output_directory(
            output_dir=output_dir,
            primary_output_dir=primary_output_dir,
            fallback_output_dir=fallback_output_dir,
        )
        if not output_root:
            return TimelineAudioExportResult(
                False,
                warnings=directory_warnings,
                errors=[
                    "Neither the primary nor fallback Select reference-audio directory is writable."
                ],
            )

        safe_name = self._safe_stem(custom_name) if custom_name else self._default_stem(timeline_name)
        previous_format = dict(
            _call(project, "GetCurrentRenderFormatAndCodec", {}) or {}
        )
        previous_mode = _call(project, "GetCurrentRenderMode", None)
        warnings = list(directory_warnings)
        warnings.append(
            "Resolve does not expose a complete render-settings snapshot. Render mode "
            "and format/codec are restored when possible, but loading Codex_Mp3 may "
            "leave other Deliver-page settings changed."
        )

        staged = None
        job_id = ""
        details = {
            "timeline": timeline_name,
            "directory_role": directory_role,
            "export_directory": str(output_root),
            "render_preset": str(render_preset),
            "filename_stem": safe_name,
            "persistent": True,
            "temporary": False,
        }

        try:
            if str(preferred_format or "mp3").casefold() == "mp3":
                staged, job_id, mp3_warnings, mp3_details = self._render_with_preset(
                    project,
                    output_root,
                    safe_name,
                    render_preset,
                    timeout_seconds,
                )
                warnings.extend(mp3_warnings)
                details.update(mp3_details)

                if staged and staged.stat().st_size <= int(max_direct_upload_bytes):
                    destination = output_root / ("%s.mp3" % safe_name)
                    published = self._publish(staged, destination)
                    details.update({
                        "analysis_format": "mp3",
                        "used_wav_fallback": False,
                        "bytes": published.stat().st_size,
                    })
                    return TimelineAudioExportResult(
                        True,
                        path=str(published),
                        job_id=job_id,
                        warnings=warnings,
                        details=details,
                    )

                if staged and staged.stat().st_size > int(max_direct_upload_bytes):
                    warnings.append(
                        "Codex_Mp3 output is larger than the direct analysis safety "
                        "limit; using chunkable WAV fallback."
                    )

            wav_staged, wav_job, wav_warnings, wav_details = self._render_wav_fallback(
                project,
                output_root,
                safe_name,
                sample_rate,
                bit_depth,
                timeout_seconds,
            )
            warnings.extend(wav_warnings)
            details.update(wav_details)
            if not wav_staged:
                return TimelineAudioExportResult(
                    False,
                    job_id=wav_job or job_id,
                    warnings=warnings,
                    errors=[
                        "Codex_Mp3 export was unavailable/invalid and WAV fallback also failed."
                    ],
                    details=details,
                )

            destination = output_root / ("%s.wav" % safe_name)
            published = self._publish(wav_staged, destination)
            details.update({
                "analysis_format": "wav",
                "used_wav_fallback": True,
                "bytes": published.stat().st_size,
            })
            return TimelineAudioExportResult(
                True,
                path=str(published),
                job_id=wav_job,
                warnings=warnings,
                details=details,
            )
        finally:
            self._restore(project, previous_format, previous_mode)
            try:
                for path in output_root.glob(".meher-mp3-*"):
                    if path.is_dir():
                        shutil.rmtree(str(path), ignore_errors=True)
                for path in output_root.glob(".meher-wav-*"):
                    if path.is_dir():
                        shutil.rmtree(str(path), ignore_errors=True)
            except Exception:
                pass

    @staticmethod
    def _restore(project, previous_format, previous_mode):
        if previous_mode is not None:
            _call(project, "SetCurrentRenderMode", False, previous_mode)
        render_format = str(previous_format.get("format", "") or "")
        codec = str(previous_format.get("codec", "") or "")
        if render_format and codec:
            _call(
                project,
                "SetCurrentRenderFormatAndCodec",
                False,
                render_format,
                codec,
            )
